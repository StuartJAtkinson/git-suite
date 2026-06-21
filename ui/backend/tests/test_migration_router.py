"""migration router: status mapping, checklist caching, push flow.

The service-level checklist/scaffold/MD logic is covered in test_migration.py.
This file covers the HTTP edges the router owns: 404s, cache hits, and
no-session-on-push safety.
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

from conftest import insert_scan


def test_get_migration_status_unknown_hub_404(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[])
    with TestClient(app) as c:
        r = c.get("/api/migration/hub/no-such-hub/s1")
    assert r.status_code == 404


def test_get_migration_status_marks_live_and_done(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    # quivr is a real absorb of personal-ai-os; mark it absorbed
    insert_scan(temp_db, repos=[
        {"name": "quivr", "language": "Python", "stars": 5},
    ])
    asyncio.run(_mark_absorbed("personal-ai-os", "quivr"))
    with TestClient(app) as c:
        r = c.get("/api/migration/hub/personal-ai-os/s1")
    assert r.status_code == 200
    items = {it["repo"]: it for it in r.json()["absorbs"]}
    assert items["quivr"]["live"] is True
    assert items["quivr"]["done"] is True
    assert items["quivr"]["language"] == "Python"
    # every absorb gets a scaffold module/path
    for it in r.json()["absorbs"]:
        assert it["path"].startswith("modules/") and it["module"]


def test_gen_checklist_404_for_non_absorb_repo(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        r = c.post("/api/migration/checklist/s1", json={
            "hub": "personal-ai-os", "repo": "never-was-an-absorb", "regenerate": False,
        })
    assert r.status_code == 404


def test_gen_checklist_uses_cache_on_second_call(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[{"name": "quivr", "language": "Python"}])
    body = {"hub": "personal-ai-os", "repo": "quivr", "regenerate": False}
    with TestClient(app) as c:
        first = c.post("/api/migration/checklist/s1", json=body).json()
        second = c.post("/api/migration/checklist/s1", json=body).json()
    # second hit is served from the migration_checklist cache, not the LLM
    assert second.get("cached") is True
    assert first["steps"] == second["steps"]


def test_push_migration_404_unknown_hub(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[])
    with TestClient(app) as c:
        r = c.post("/api/migration/push/s1", json={"hub": "no-such-hub"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- helpers

async def _mark_absorbed(hub: str, repo: str) -> None:
    import database
    async for db in database.get_db():
        await db.execute(
            "INSERT OR REPLACE INTO hub_actions (hub, repo, action) VALUES (?, ?, 'absorbed')",
            (hub, repo),
        )
        await db.commit()
