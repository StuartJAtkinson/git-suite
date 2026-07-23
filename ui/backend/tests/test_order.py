"""order: per-hub ordering, column classification, compat tags, LLM suggest."""
import asyncio
import json

from services import llm
from routers.order import (
    get_order, save_order, suggest_order, suggest_column, suggest_features,
    set_compat_tags, annotate,
    OrderSaveRequest, OrderRow,
    SuggestColumnRequest, SuggestFeaturesRequest, CompatTagsRequest, AnnotateRequest,
)


def _session_and_scan(temp_db, repos):
    """Insert a session + a single scan with the given repos. Returns (sid,)."""
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=repos)
    return "s1",


def test_get_order_uses_plan_hub_absorbs(temp_db, isolated_plan):
    """get_order reads the hub's absorbs from plan.json; repos that have no
    hub_order row yet appear at the tail with position=-1 and no flags."""
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "map-hub", "language": "Python", "aim": "main hub"},
        {"name": "tilemaker", "language": "Python", "aim": "build maps"},
        {"name": "streets-gl", "language": "JS", "aim": "webgl maps"},
    ])
    isolated_plan.upsert_hub("map-hub", description="maps")
    isolated_plan.set_verdict("tilemaker", "absorb", "map-hub")
    isolated_plan.set_verdict("streets-gl", "absorb", "map-hub")

    res = asyncio.run(get_order("s1", "map-hub"))
    assert res["hub"] == "map-hub"
    assert res["columns"] == ["Gather", "Analyse", "Display"]
    assert "Inspiration" in res["compat_tags_vocab"]
    repos = [r["repo"] for r in res["rows"]]
    assert repos[0] == "map-hub"            # hub repo pinned to position 0
    assert set(repos[1:]) == {"tilemaker", "streets-gl"}
    # No flags set yet, no annotations.
    for r in res["rows"]:
        assert r["is_gather"] is False
        assert r["is_analyse"] is False
        assert r["is_display"] is False
        assert r["compat_tags"] == []
        assert r["feature_annotations"] == []


def test_save_order_round_trip(temp_db, isolated_plan):
    """POST save then GET returns the saved positions, flags, tags, and
    annotations. The hub repo is always preserved at position 0."""
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "map-hub", "language": "Python"},
        {"name": "a", "language": "Python"},
        {"name": "b", "language": "JS"},
    ])
    isolated_plan.upsert_hub("map-hub")
    isolated_plan.set_verdict("a", "absorb", "map-hub")
    isolated_plan.set_verdict("b", "absorb", "map-hub")

    asyncio.run(save_order("s1", "map-hub", OrderSaveRequest(rows=[
        OrderRow(repo="map-hub", position=0, is_gather=False, is_analyse=False, is_display=False),
        OrderRow(repo="a", position=1, is_gather=True, is_analyse=False, is_display=False,
                 compat_tags=["Inspiration"], feature_annotations=["reads OSM"]),
        OrderRow(repo="b", position=2, is_gather=False, is_analyse=True, is_display=True,
                 compat_tags=["Imports From", "Exports To"]),
    ])))
    res = asyncio.run(get_order("s1", "map-hub"))
    by_repo = {r["repo"]: r for r in res["rows"]}
    # hub repo stays at 0 even though we passed position=0 explicitly
    assert by_repo["map-hub"]["position"] == 0
    assert by_repo["a"]["is_gather"] is True
    assert by_repo["a"]["compat_tags"] == ["Inspiration"]
    assert by_repo["a"]["feature_annotations"] == ["reads OSM"]
    assert by_repo["b"]["is_analyse"] is True
    assert by_repo["b"]["is_display"] is True
    assert by_repo["b"]["compat_tags"] == ["Imports From", "Exports To"]


def test_save_order_rejects_non_absorb_repo(temp_db, isolated_plan):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1",
                repos=[{"name": "map-hub", "language": "Python"},
                       {"name": "outsider", "language": "Python"}])
    isolated_plan.upsert_hub("map-hub")
    # `outsider` is NOT absorbed into map-hub
    import pytest
    with pytest.raises(Exception) as ei:
        asyncio.run(save_order("s1", "map-hub", OrderSaveRequest(rows=[
            OrderRow(repo="map-hub", position=0),
            OrderRow(repo="outsider", position=1),
        ])))
    assert "outsider" in str(ei.value)


def test_save_order_drops_stale_rows(temp_db, isolated_plan):
    """If an absorb is removed from the plan, its hub_order row goes too."""
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "map-hub", "language": "Python"},
        {"name": "a", "language": "Python"},
        {"name": "b", "language": "JS"},
    ])
    isolated_plan.upsert_hub("map-hub")
    isolated_plan.set_verdict("a", "absorb", "map-hub")
    isolated_plan.set_verdict("b", "absorb", "map-hub")

    # First save orders both.
    asyncio.run(save_order("s1", "map-hub", OrderSaveRequest(rows=[
        OrderRow(repo="map-hub", position=0),
        OrderRow(repo="a", position=1),
        OrderRow(repo="b", position=2),
    ])))
    # Now drop b from the plan and save again without it.
    plan = isolated_plan.get_plan()
    plan["hubs"]["map-hub"]["absorbs"] = ["a"]
    isolated_plan.save_plan(plan)

    asyncio.run(save_order("s1", "map-hub", OrderSaveRequest(rows=[
        OrderRow(repo="map-hub", position=0),
        OrderRow(repo="a", position=1),
    ])))
    res = asyncio.run(get_order("s1", "map-hub"))
    assert {r["repo"] for r in res["rows"]} == {"map-hub", "a"}


def test_set_compat_tags_override(temp_db, isolated_plan):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1",
                repos=[{"name": "h", "language": "Python"}])
    isolated_plan.upsert_hub("h")

    res = asyncio.run(set_compat_tags("s1", "h",
                                      CompatTagsRequest(tags=["fork-of", "inspired-by"])))
    assert res["tags"] == ["fork-of", "inspired-by"]
    # GET order returns the override as compat_tags_vocab
    res2 = asyncio.run(get_order("s1", "h"))
    assert res2["compat_tags_vocab"] == ["fork-of", "inspired-by"]


def test_set_compat_tags_empty_resets_to_default(temp_db, isolated_plan):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1",
                repos=[{"name": "h", "language": "Python"}])
    isolated_plan.upsert_hub("h")
    asyncio.run(set_compat_tags("s1", "h", CompatTagsRequest(tags=[])))
    res = asyncio.run(get_order("s1", "h"))
    # Empty override falls back to the global default
    assert "Inspiration" in res["compat_tags_vocab"]


def test_annotate_sets_feature_annotations(temp_db, isolated_plan):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python"},
        {"name": "x", "language": "Python"},
    ])
    isolated_plan.upsert_hub("h")
    isolated_plan.set_verdict("x", "absorb", "h")
    res = asyncio.run(annotate("s1", "h", AnnotateRequest(
        repo="x", annotations=["reads OSM pbf", "emits vector tiles"],
    )))
    assert res["annotations"] == ["reads OSM pbf", "emits vector tiles"]
    out = asyncio.run(get_order("s1", "h"))
    by_repo = {r["repo"]: r for r in out["rows"]}
    assert by_repo["x"]["feature_annotations"] == ["reads OSM pbf", "emits vector tiles"]


# --- LLM Suggest endpoints -------------------------------------------------

def test_suggest_order_parses_llm_json(temp_db, isolated_plan, monkeypatch):
    """The hub-order Suggest endpoint asks the LLM for a reorder; we mock
    llm.complete to return valid JSON and verify the parsed response."""
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python", "aim": "hub"},
        {"name": "scraper", "language": "Python", "aim": "scrapes data"},
        {"name": "ui", "language": "JS", "aim": "visualises data"},
    ])
    isolated_plan.upsert_hub("h", description="data tools")
    isolated_plan.set_verdict("scraper", "absorb", "h")
    isolated_plan.set_verdict("ui", "absorb", "h")

    fake = {
        "proposed": [
            {"repo": "h", "position": 0},
            {"repo": "scraper", "position": 1},
            {"repo": "ui", "position": 2},
        ],
        "moves": [
            {"repo": "scraper", "from": 2, "to": 1, "rationale": "Gather first"},
            {"repo": "ui", "from": 1, "to": 2, "rationale": "Display last"},
        ],
        "rationale_overall": "scraper collects, ui shows",
    }

    async def fake_complete(prompt, system="", max_tokens=1024):
        return json.dumps(fake)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = asyncio.run(suggest_order("s1", "h"))
    assert res["proposed"][0]["repo"] == "h"
    assert res["proposed"][1]["repo"] == "scraper"
    assert res["proposed"][2]["repo"] == "ui"
    assert any(m["repo"] == "scraper" and m["to"] == 1 for m in res["moves"])


def test_suggest_order_strips_json_fences(temp_db, isolated_plan, monkeypatch):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python"},
    ])
    isolated_plan.upsert_hub("h")

    fenced = '```json\n{"proposed": [], "moves": [], "rationale_overall": "ok"}\n```'

    async def fake_complete(prompt, system="", max_tokens=1024):
        return fenced
    monkeypatch.setattr(llm, "complete", fake_complete)
    res = asyncio.run(suggest_order("s1", "h"))
    assert res["rationale_overall"] == "ok"


def test_suggest_column_parses_llm_json(temp_db, isolated_plan, monkeypatch):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python"},
        {"name": "scraper", "language": "Python", "aim": "scrapes things"},
    ])
    isolated_plan.upsert_hub("h", description="data tools")
    isolated_plan.set_verdict("scraper", "absorb", "h")

    fake = {
        "is_gather": True,
        "is_analyse": False,
        "is_display": False,
        "rationale": "it scrapes data, so it's Gather",
    }

    async def fake_complete(prompt, system="", max_tokens=1024):
        return json.dumps(fake)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = asyncio.run(suggest_column("s1", "h", SuggestColumnRequest(repo="scraper")))
    assert res["repo"] == "scraper"
    assert res["is_gather"] is True
    assert res["is_analyse"] is False
    assert res["is_display"] is False
    assert "scrapes" in res["rationale"]


def test_suggest_column_supports_multi_column(temp_db, isolated_plan, monkeypatch):
    """A repo that scrapes AND has a UI should come back with both flags."""
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python"},
        {"name": "scrapey-ui", "language": "Python", "aim": "scraper with web UI"},
    ])
    isolated_plan.upsert_hub("h")
    isolated_plan.set_verdict("scrapey-ui", "absorb", "h")

    fake = {
        "is_gather": True, "is_analyse": False, "is_display": True,
        "rationale": "scrapes data and renders a dashboard",
    }

    async def fake_complete(prompt, system="", max_tokens=1024):
        return json.dumps(fake)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = asyncio.run(suggest_column("s1", "h", SuggestColumnRequest(repo="scrapey-ui")))
    assert res["is_gather"] is True
    assert res["is_display"] is True
    assert res["is_analyse"] is False


def test_suggest_features_parses_llm_json_and_persists(temp_db, isolated_plan, monkeypatch):
    """Step 5 — suggest-features asks the LLM for a repo's concrete feature
    list, then persists it into hub_order.feature_annotations (same column
    the manual /annotate endpoint writes)."""
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python"},
        {"name": "scraper", "language": "Python", "aim": "scrapes data"},
    ])
    isolated_plan.upsert_hub("h", description="data tools")
    isolated_plan.set_verdict("scraper", "absorb", "h")
    # Mark scraper as Gather so the prompt's column context is non-empty.
    asyncio.run(save_order("s1", "h", OrderSaveRequest(rows=[
        OrderRow(repo="h", position=0),
        OrderRow(repo="scraper", position=1, is_gather=True),
    ])))

    fake = {
        "features": ["rate-limited HTTP client", "CSV export", "retry with backoff"],
        "rationale": "gathers and exports data, fits the Gather role",
    }

    async def fake_complete(prompt, system="", max_tokens=1024):
        return json.dumps(fake)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = asyncio.run(suggest_features("s1", "h", SuggestFeaturesRequest(repo="scraper")))
    assert res["repo"] == "scraper"
    assert res["features"] == ["rate-limited HTTP client", "CSV export", "retry with backoff"]
    assert "Gather" in res["rationale"]

    # Persisted: a fresh GET reflects the same features.
    out = asyncio.run(get_order("s1", "h"))
    by_repo = {r["repo"]: r for r in out["rows"]}
    assert by_repo["scraper"]["feature_annotations"] == res["features"]


def test_suggest_features_caps_at_eight_and_strips_blanks(temp_db, isolated_plan, monkeypatch):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python"},
        {"name": "x", "language": "Python"},
    ])
    isolated_plan.upsert_hub("h")
    isolated_plan.set_verdict("x", "absorb", "h")

    fake = {"features": [f"feature {i}" for i in range(12)] + ["", "  "],
            "rationale": "lots of features"}

    async def fake_complete(prompt, system="", max_tokens=1024):
        return json.dumps(fake)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = asyncio.run(suggest_features("s1", "h", SuggestFeaturesRequest(repo="x")))
    assert len(res["features"]) == 8
    assert all(f.strip() for f in res["features"])


def test_suggest_features_rejects_non_absorb_repo(temp_db, isolated_plan):
    from tests.conftest import insert_scan
    import pytest
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "h", "language": "Python"},
        {"name": "outsider", "language": "Python"},
    ])
    isolated_plan.upsert_hub("h")
    with pytest.raises(Exception) as ei:
        asyncio.run(suggest_features("s1", "h", SuggestFeaturesRequest(repo="outsider")))
    assert "outsider" in str(ei.value)
