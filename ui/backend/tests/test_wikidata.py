"""wikidata: SPARQL subgraph fetch + cache + Router hybrid flow.

All tests use the project fixtures (isolated_plan, temp_db, autouse
_isolate_llm). httpx calls are patched via monkeypatch so no test
hits the real Wikidata endpoint.
"""
import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

# A canned SPARQL JSON response for one-hop: child Q of root Q.
# wd_get is patched to return this; the router then iterates no further.
SPARQL_ONE_HOP = {
    "results": {
        "bindings": [
            {"qid":   {"value": "http://www.wikidata.org/entity/Q1"},
             "oQid":  {"value": "http://www.wikidata.org/entity/Q2"},
             "oLabel": {"value": "parent-of-Q1"}},
        ]
    }
}

# A multi-hop chain: Q1 -> Q2 -> Q3 -> Q4 (each iteration returns one new edge).
# The first iteration returns Q1->Q2; the second returns Q2->Q3; the third
# returns Q3->Q4; the fourth returns nothing (so the loop terminates).
SPARQL_MULTI_HOP_CALLS = [
    {"results": {"bindings": [
        {"qid": {"value": "http://www.wikidata.org/entity/Q1"},
         "oQid": {"value": "http://www.wikidata.org/entity/Q2"},
         "oLabel": {"value": "level-1"}},
    ]}},
    {"results": {"bindings": [
        {"qid": {"value": "http://www.wikidata.org/entity/Q2"},
         "oQid": {"value": "http://www.wikidata.org/entity/Q3"},
         "oLabel": {"value": "level-2"}},
    ]}},
    {"results": {"bindings": [
        {"qid": {"value": "http://www.wikidata.org/entity/Q3"},
         "oQid": {"value": "http://www.wikidata.org/entity/Q4"},
         "oLabel": {"value": "level-3"}},
    ]}},
    {"results": {"bindings": []}},   # terminates
]

# An edge that points INTO the stop set — the FILTER clause should drop it.
SPARQL_INTO_STOP = {
    "results": {"bindings": [
        {"qid": {"value": "http://www.wikidata.org/entity/Q1"},
         "oQid": {"value": "http://www.wikidata.org/entity/Q35120"},   # 'entity' — stop
         "oLabel": {"value": "entity"}},
    ]}
}


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


def _session_in_db(db_path, sid="s1", user="tester"):
    import aiosqlite
    async def _seed():
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO session "
                "(id, github_token, github_user, repos_root) "
                "VALUES (?, 'tok', ?, '')",
                (sid, user))
            await db.commit()
    asyncio.run(_seed())


def _patch_wd_get(monkeypatch, response_or_iter, *, raise_exc=None, call_log=None):
    """Patch services.wikidata.wd_get for the duration of the test.

    response_or_iter:
      - a single dict → wd_get returns the same response every call
      - a list of dicts → each call pops the next one (multi-hop test)
    raise_exc: if set, wd_get raises this exception instead of returning
    """
    from services import wikidata as wd
    responses = (response_or_iter if isinstance(response_or_iter, list)
                 else [response_or_iter])
    if call_log is not None:
        call_log.append("init")

    async def fake_get(client, url, params=None):
        if call_log is not None:
            call_log.append("call")
        if raise_exc is not None:
            raise raise_exc
        if not responses:
            return _FakeResponse(200, {"results": {"bindings": []}})
        return _FakeResponse(200, responses.pop(0))

    monkeypatch.setattr(wd, "wd_get", fake_get)


# -- pure-service tests (no router, no auth) -------------------------------


def test_fetch_subgraph_happy_path(monkeypatch):
    """One-hop: Q1's parent is Q2. Result has 2 nodes + 1 edge."""
    from services.wikidata import fetch_subgraph

    async def fake_get(client, url, params=None):
        return _FakeResponse(200, SPARQL_ONE_HOP)
    monkeypatch.setattr("services.wikidata.wd_get", fake_get)

    async def _go():
        async with httpx.AsyncClient() as client:
            return await fetch_subgraph(client, "Q1", [])
    out = asyncio.run(_go())
    qids = sorted(n["qid"] for n in out["nodes"])
    assert qids == ["Q1", "Q2"]
    assert out["edges"] == [{"from": "Q1", "to": "Q2", "prop": "P279/P361"}]
    assert out["root"] == "Q1"


def test_fetch_subgraph_iterates_to_depth(monkeypatch):
    """Multi-hop: 3 distinct parents are discovered across 3 iterations."""
    from services.wikidata import fetch_subgraph

    responses = list(SPARQL_MULTI_HOP_CALLS)
    async def fake_get(client, url, params=None):
        if not responses:
            return _FakeResponse(200, {"results": {"bindings": []}})
        return _FakeResponse(200, responses.pop(0))
    monkeypatch.setattr("services.wikidata.wd_get", fake_get)

    async def _go():
        async with httpx.AsyncClient() as client:
            return await fetch_subgraph(client, "Q1", [])
    out = asyncio.run(_go())
    qids = sorted(n["qid"] for n in out["nodes"])
    assert qids == ["Q1", "Q2", "Q3", "Q4"]
    # Three edges: 1->2, 2->3, 3->4
    assert len(out["edges"]) == 3


def test_fetch_subgraph_prunes_stop_set(monkeypatch):
    """An edge that points into Q35120 (entity) is filtered out."""
    from services.wikidata import fetch_subgraph

    responses = [SPARQL_INTO_STOP, {"results": {"bindings": []}}]
    async def fake_get(client, url, params=None):
        if not responses:
            return _FakeResponse(200, {"results": {"bindings": []}})
        return _FakeResponse(200, responses.pop(0))
    monkeypatch.setattr("services.wikidata.wd_get", fake_get)

    async def _go():
        async with httpx.AsyncClient() as client:
            return await fetch_subgraph(client, "Q1", [])
    out = asyncio.run(_go())
    # Only Q1 should be in the result — the stop-Q35120 is filtered
    assert [n["qid"] for n in out["nodes"]] == ["Q1"]
    assert out["edges"] == []


def test_fetch_subgraph_invalid_root_raises(monkeypatch):
    """Empty or non-Q root ids raise WdError before any network call."""
    from services.wikidata import WdError, fetch_subgraph
    called = []

    async def fake_get(client, url, params=None):
        called.append(True)
        return _FakeResponse(200, {"results": {"bindings": []}})
    monkeypatch.setattr("services.wikidata.wd_get", fake_get)

    for bad in ("", "junk", None):
        async def _go():
            async with httpx.AsyncClient() as client:
                return await fetch_subgraph(client, bad, [])
        with pytest.raises(WdError):
            asyncio.run(_go())
    assert called == []


def test_fetch_subgraph_member_qids_added_as_leaves(monkeypatch):
    """Member Q-ids passed in are merged into the nodes regardless of SPARQL."""
    from services.wikidata import fetch_subgraph

    async def fake_get(client, url, params=None):
        return _FakeResponse(200, {"results": {"bindings": []}})
    monkeypatch.setattr("services.wikidata.wd_get", fake_get)

    async def _go():
        async with httpx.AsyncClient() as client:
            return await fetch_subgraph(client, "Q1", ["Q99", "Q100"])
    out = asyncio.run(_go())
    qids = sorted(n["qid"] for n in out["nodes"])
    # Q1 (root) + Q99 + Q100 (members)
    assert qids == ["Q1", "Q100", "Q99"]
    # Members carry kind=repo, root does not
    kinds = {n["qid"]: n.get("kind") for n in out["nodes"]}
    assert kinds["Q99"] == "repo"
    assert kinds["Q1"] is None


# -- router tests (TestClient + DB) ---------------------------------------


def test_router_dag_no_wikidata_id_returns_local(temp_db, isolated_plan, monkeypatch):
    """Hub with no wikidata_id → local fallback (no SPARQL call)."""
    import database
    from services import wikidata as wd
    from services.wikidata import WdError

    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    isolated_plan.upsert_hub("map-suite")

    calls = []
    async def fake_get(client, url, params=None):
        calls.append("called")
        return _FakeResponse(200, {"results": {"bindings": []}})
    monkeypatch.setattr(wd, "wd_get", fake_get)

    from main import app
    with TestClient(app) as c:
        r = c.get("/api/wikidata/dag/s1/map-suite")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "local"
        assert "no Wikidata id" in body["note"]
        assert calls == []   # SPARQL was NOT hit


def test_router_dag_cache_miss_then_hit(temp_db, isolated_plan, monkeypatch):
    """First call: SPARQL hit (multi-hop iterates), persisted. Second
    call: cache hit, no SPARQL."""
    import database
    from services import wikidata as wd

    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    isolated_plan.upsert_hub("map-suite", wikidata_id="Q1")

    calls = []
    responses = [SPARQL_ONE_HOP, {"results": {"bindings": []}}]
    async def fake_get(client, url, params=None):
        calls.append("network")
        return _FakeResponse(200, responses.pop(0) if responses
                            else {"results": {"bindings": []}})
    monkeypatch.setattr(wd, "wd_get", fake_get)

    from main import app
    with TestClient(app) as c:
        r1 = c.get("/api/wikidata/dag/s1/map-suite")
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["source"] == "wikidata"
        assert body1["cache"] == "miss"
        # SPARQL was hit at least once (cache miss path); max_depth=4 loops
        # until the frontier stops growing, so the mock returns 2 results.
        assert len(calls) >= 1
        calls_after_r1 = len(calls)

        # Second call — same cache key, should hit the cache.
        r2 = c.get("/api/wikidata/dag/s1/map-suite")
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["source"] == "wikidata"
        assert body2["cache"] == "hit"
        # The strong contract: the cache hit added exactly ZERO new calls.
        assert len(calls) == calls_after_r1


def test_router_dag_sparql_failure_returns_local(temp_db, isolated_plan, monkeypatch):
    """SPARQL raises WdError → endpoint returns local fallback with a note."""
    import database
    from services import wikidata as wd
    from services.wikidata import WdError

    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    isolated_plan.upsert_hub("map-suite", wikidata_id="Q1")

    async def fake_get(client, url, params=None):
        raise WdError("synthetic outage")
    monkeypatch.setattr(wd, "wd_get", fake_get)

    from main import app
    with TestClient(app) as c:
        r = c.get("/api/wikidata/dag/s1/map-suite")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "local"
        assert "synthetic outage" in body["note"]
        assert body["root"] == "Q1"


def test_router_dag_unknown_hub_returns_404(temp_db, isolated_plan, monkeypatch):
    """GET /dag/{hub} for a hub that doesn't exist → 404."""
    import database
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()

    from main import app
    with TestClient(app) as c:
        r = c.get("/api/wikidata/dag/s1/nonexistent-hub")
        assert r.status_code == 404


def test_router_set_hub_wikidata_round_trips(temp_db, isolated_plan, monkeypatch):
    """POST /hub sets wikidata_id; GET /dag then sees it."""
    import database
    from services import wikidata as wd

    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    isolated_plan.upsert_hub("map-suite")

    async def fake_get(client, url, params=None):
        return _FakeResponse(200, SPARQL_ONE_HOP)
    monkeypatch.setattr(wd, "wd_get", fake_get)

    from main import app
    with TestClient(app) as c:
        r = c.post("/api/wikidata/hub/s1", json={"hub": "map-suite",
                                                  "wikidata_id": "Q12345"})
        assert r.status_code == 200, r.text
        assert r.json() == {"hub": "map-suite", "wikidata_id": "Q12345"}

        # Now fetch the DAG — the hub already has a wikidata_id
        r2 = c.get("/api/wikidata/dag/s1/map-suite")
        assert r2.status_code == 200, r2.text
        assert r2.json()["source"] == "wikidata"


def test_router_set_hub_wikidata_clear_with_empty_string(temp_db, isolated_plan):
    """POST with wikidata_id="" clears the field (None)."""
    import database
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    isolated_plan.upsert_hub("map-suite", wikidata_id="Q1")

    from main import app
    with TestClient(app) as c:
        r = c.post("/api/wikidata/hub/s1", json={"hub": "map-suite",
                                                  "wikidata_id": ""})
        assert r.status_code == 200, r.text
        assert r.json()["wikidata_id"] is None


# -- plan_store + plan_router integration --------------------------------


def test_plan_upsert_hub_persists_wikidata_id(temp_db, isolated_plan):
    """upsert_hub(wikidata_id="Q12345") persists; heal preserves it."""
    isolated_plan.clear()
    isolated_plan.upsert_hub("map-suite", wikidata_id="Q12345")
    hub = isolated_plan.get_plan()["hubs"]["map-suite"]
    assert hub["wikidata_id"] == "Q12345"

    # None re-upsert preserves existing value
    isolated_plan.upsert_hub("map-suite")
    hub = isolated_plan.get_plan()["hubs"]["map-suite"]
    assert hub["wikidata_id"] == "Q12345"

    # Empty string clears
    isolated_plan.upsert_hub("map-suite", wikidata_id="")
    hub = isolated_plan.get_plan()["hubs"]["map-suite"]
    assert hub["wikidata_id"] is None


def test_plan_router_upsert_hub_forwards_wikidata_id(temp_db, isolated_plan):
    """POST /api/plan/hub with wikidata_id → field round-trips."""
    import database
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()

    from main import app
    with TestClient(app) as c:
        r = c.post("/api/plan/hub",
                   json={"name": "map-suite", "wikidata_id": "Q9"})
        assert r.status_code == 200, r.text
        assert r.json()["wikidata_id"] == "Q9"
        assert isolated_plan.get_plan()["hubs"]["map-suite"]["wikidata_id"] == "Q9"
