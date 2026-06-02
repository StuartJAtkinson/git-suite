"""Shared fixtures. Tests isolate plan.json and state.db into tmp dirs so they
never touch the real ~/.git-suite or the live state.db."""
import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def isolated_plan(tmp_path, monkeypatch):
    """plan_store backed by a throwaway plan.json, freshly seeded."""
    import plan_store
    monkeypatch.setattr(plan_store, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(plan_store, "_PLAN_FILE", tmp_path / "plan.json")
    plan_store.reset()
    return plan_store


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """database backed by a throwaway sqlite file with the schema applied."""
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "state.db")
    asyncio.run(database.init_db())
    return database


def insert_scan(database, session_id="s1", scan_id="sc1", repos=None):
    """Helper: write a session + scan + repo rows into the temp DB."""
    repos = repos or []

    async def _go():
        async for db in database.get_db():
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) VALUES (?,?,?,?)",
                (session_id, "tok", "tester", "/tmp"),
            )
            await db.execute(
                "INSERT INTO scan_meta (scan_id, session_id, repo_count) VALUES (?,?,?)",
                (scan_id, session_id, len(repos)),
            )
            for r in repos:
                await db.execute(
                    """INSERT INTO repos (scan_id, name, super_cat, mid_cat, fine_cat,
                       aim, url, visibility, language, stars, is_fork, pushed_at, topics, archived)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (scan_id, r["name"], "", "", "", r.get("aim", ""), "", "public",
                     r.get("language", ""), r.get("stars", 0), 0, "", "[]", 0),
                )
            await db.commit()

    asyncio.run(_go())
    return session_id, scan_id
