"""Step 3 'Own': promote service (detach checklist) + router (decide/list)."""
import asyncio

from conftest import insert_scan


def _insert_fork(database, name, full_name, language="Python", scan_id="sc1"):
    async def _go():
        async for db in database.get_db():
            await db.execute(
                """INSERT INTO repos (scan_id, name, full_name, super_cat, mid_cat,
                   aim, url, visibility, language, stars, is_fork, pushed_at, topics, archived)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (scan_id, name, full_name, "", "", "", "", "public", language,
                 0, 1, "", "[]", 0),
            )
            await db.commit()
    asyncio.run(_go())


# --- service ---------------------------------------------------------------

def test_rule_checklist_shapes():
    from services import promote
    base = promote._rule_checklist({"name": "winutil"}, None, "x/winutil")
    assert any("mirror" in s for s in base)
    assert "Archive or delete" in base[-1]
    assert not any("baseline" in s for s in base)        # no hub -> no standardise step
    hubbed = promote._rule_checklist({"name": "winutil"}, "homelab-core", "x/y")
    assert any("homelab-core" in s and "baseline" in s for s in hubbed)


def test_checklist_for_falls_back_to_rule_without_llm(monkeypatch):
    from services import promote, llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)
    res = asyncio.run(promote.checklist_for({"name": "winutil"}, None, "x/y", None))
    assert res["source"] == "rule"
    assert res["steps"]


# --- router: decide maps onto plan verdicts (one source of truth) ----------

def test_decide_maps_to_verdicts(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        assert c.post("/api/promote/decide", json={
            "repo": "winutil", "decision": "promote", "hub": "homelab-core"}).status_code == 200
        c.post("/api/promote/decide", json={"repo": "loose-fork", "decision": "promote"})
        c.post("/api/promote/decide", json={"repo": "junk-fork", "decision": "drop"})
        assert c.post("/api/promote/decide", json={
            "repo": "x", "decision": "bogus"}).status_code == 400

    plan = isolated_plan.get_plan()
    assert "winutil" in plan["hubs"]["homelab-core"]["absorbs"]   # promote+hub -> absorb
    assert "loose-fork" in plan["keeps"]                          # promote no hub -> keep
    assert "junk-fork" in plan["archives"]                        # drop -> archive


# --- router: list forks (heads stubbed to stay offline) --------------------

def test_list_forks_shape(temp_db, isolated_plan, monkeypatch):
    from fastapi.testclient import TestClient
    insert_scan(temp_db)                      # session + (empty) scan sc1
    _insert_fork(temp_db, "winutil", "tester/winutil")

    async def fake_head(token, full_name):
        return {"name": full_name.split("/")[-1],
                "parent_full_name": "ChrisTitusTech/winutil",
                "parent_private": False, "issue": None, "message": ""}
    monkeypatch.setattr("routers.promote._head_one", fake_head)

    from main import app
    with TestClient(app) as c:
        r = c.get("/api/promote/s1")
    assert r.status_code == 200
    body = r.json()
    assert len(body["forks"]) == 1
    f = body["forks"][0]
    assert f["name"] == "winutil"
    assert f["parent_full_name"] == "ChrisTitusTech/winutil"
    assert "homelab-core" in body["hubs"]


def test_checklist_endpoint_rule(temp_db, isolated_plan, monkeypatch):
    from fastapi.testclient import TestClient
    insert_scan(temp_db)
    _insert_fork(temp_db, "winutil", "tester/winutil")

    async def no_readme(*a, **k):
        return None
    monkeypatch.setattr("routers.promote.get_readme", no_readme)
    from services import llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)

    from main import app
    with TestClient(app) as c:
        ok = c.post("/api/promote/checklist/s1",
                    json={"repo": "winutil", "hub": "homelab-core", "parent": "x/y"})
        missing = c.post("/api/promote/checklist/s1", json={"repo": "nope"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["source"] == "rule"
    assert any("homelab-core" in s for s in body["steps"])
    assert missing.status_code == 404          # not an owned fork in the scan
