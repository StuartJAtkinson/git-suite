"""installer: hub DAG build, install-order topo sort, validate endpoint."""
from fastapi.testclient import TestClient

import database
from routers import installer
from routers.installer import _build_dag


def _session_in_db(db_path, sid="s1", user="tester"):
    """Write a session row directly to the temp DB so require_session() passes.
    repos_root is NOT NULL in the schema (legacy column, kept for back-compat
    with existing DBs) — even though the app is remote-only, every INSERT
    must provide one.
    """
    import aiosqlite, asyncio
    async def _seed():
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO session "
                "(id, github_token, github_user, repos_root) "
                "VALUES (?, 'tok', ?, '')",
                (sid, user))
            await db.commit()
    asyncio.run(_seed())


def _client(temp_db, isolated_plan):
    from main import app
    return TestClient(app)


def _seed_hub_with_absorbs(isolated_plan, hub, absorbs):
    isolated_plan.upsert_hub(hub)
    for r in absorbs:
        isolated_plan.set_verdict(r, "absorb", hub)


# -- pure-DAG tests (no router, no auth) -----------------------------------


def test_build_dag_orders_hubs_deterministically(isolated_plan):
    isolated_plan.clear()
    _seed_hub_with_absorbs(isolated_plan, "map-suite", ["tilemaker", "streets-gl"])
    _seed_hub_with_absorbs(isolated_plan, "game-hub",  ["FinalBoss", "DiggFrag"])

    dag = _build_dag()
    names = [n["name"] for n in dag["nodes"]]
    assert names == sorted(names)
    assert "map-suite" in names and "game-hub" in names

    by_name = {n["name"]: n for n in dag["nodes"]}
    assert set(by_name["map-suite"]["absorbs"]) == {"tilemaker", "streets-gl"}


def test_build_dag_handles_empty_plan(isolated_plan):
    isolated_plan.clear()
    dag = _build_dag()
    assert dag["nodes"] == []
    assert dag["edges"] == []
    assert dag["install_order"] == []


def test_build_dag_emits_edges_and_toposort_when_hub_is_absorbed_by_another(isolated_plan):
    isolated_plan.clear()
    _seed_hub_with_absorbs(isolated_plan, "sub-hub",  ["child-a"])
    _seed_hub_with_absorbs(isolated_plan, "top-hub",  ["sub-hub"])

    dag = _build_dag()
    edge_pairs = {(e["from"], e["to"]) for e in dag["edges"]}
    assert ("sub-hub", "top-hub") in edge_pairs

    # Install order: 'sub-hub' first (no prereqs), 'top-hub' last (depends on sub-hub).
    assert dag["install_order"][0] == "sub-hub"
    assert dag["install_order"][-1] == "top-hub"


# -- route tests via TestClient (auth flows through session DB) ------------


def test_installer_endpoint_emits_manifest(temp_db, isolated_plan):
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    _seed_hub_with_absorbs(isolated_plan, "map-suite", ["tilemaker"])

    with _client(temp_db, isolated_plan) as c:
        r = c.get("/api/install/s1")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["version"] == 1
        assert any(n["name"] == "map-suite" for n in body["nodes"])
        assert "map-suite" in body["install_order"]


def test_installer_text_is_human_readable(temp_db, isolated_plan):
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    _seed_hub_with_absorbs(isolated_plan, "map-suite", ["tilemaker", "streets-gl"])

    with _client(temp_db, isolated_plan) as c:
        r = c.get("/api/install/s1/text")
        assert r.status_code == 200, r.text
        body = r.text
        assert "# git-suite install plan" in body
        assert "1. map-suite" in body
        assert "tilemaker" in body
        assert "# git-suite emits this" in body  # explicit hand-off note


def test_installer_compose_emits_yaml_hand_off(temp_db, isolated_plan):
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    _seed_hub_with_absorbs(isolated_plan, "map-suite", ["tilemaker"])

    with _client(temp_db, isolated_plan) as c:
        r = c.get("/api/install/s1/compose")
        assert r.status_code == 200, r.text
        body = r.text
        assert "services:" in body
        assert "# hub: map-suite" in body
        assert "# Hand-off only" in body
        assert "git-suite did not write this file to disk" in body


def test_installer_validate_flags_drift(temp_db, isolated_plan):
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    _seed_hub_with_absorbs(isolated_plan, "map-suite", ["tilemaker"])
    _seed_hub_with_absorbs(isolated_plan, "game-hub",  ["DiggFrag"])

    manifest = {"nodes": [{"name": "map-suite", "absorbs": ["tilemaker"]},
                          {"name": "old-hub",   "absorbs": []}]}
    with _client(temp_db, isolated_plan) as c:
        r = c.post("/api/install/s1/validate", json={"manifest": manifest})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["missing_from_manifest"] == ["game-hub"]
        assert body["added_in_manifest"]     == ["old-hub"]
        assert body["in_sync"]               is False


def test_installer_validate_in_sync(temp_db, isolated_plan):
    db_path = database.DB_PATH
    _session_in_db(db_path)
    isolated_plan.clear()
    _seed_hub_with_absorbs(isolated_plan, "map-suite", ["tilemaker"])

    manifest = {"nodes": [{"name": "map-suite", "absorbs": ["tilemaker"]}]}
    with _client(temp_db, isolated_plan) as c:
        r = c.post("/api/install/s1/validate", json={"manifest": manifest})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["in_sync"] is True
        assert body["missing_from_manifest"] == []
