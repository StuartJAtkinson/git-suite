"""scan router: GET/POST /api/scan/notes/{session_id}.

The Notes endpoint is the user's override of the LLM's purpose/domain guess —
authored on the Scan page, persisted per (session, repo), scoped to the
session so multi-session cleanup behaviour stays predictable.
"""
import asyncio

from conftest import insert_scan


def test_get_notes_empty_when_none_set(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[
        {"name": "quivr", "language": "Python"},
    ])
    with TestClient(app) as c:
        r = c.get("/api/scan/notes/s1")
    assert r.status_code == 200
    assert r.json() == {}


def test_set_note_round_trips_and_overwrites(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[
        {"name": "quivr", "language": "Python"},
    ])
    with TestClient(app) as c:
        # first write
        r1 = c.post("/api/scan/notes/s1", json={"repo": "quivr", "note": "RAG memory"})
        assert r1.status_code == 200
        assert r1.json() == {"repo": "quivr", "note": "RAG memory"}

        # second write overwrites (upsert, not append)
        r2 = c.post("/api/scan/notes/s1", json={"repo": "quivr", "note": "personal RAG"})
        assert r2.status_code == 200

        # GET returns the latest value
        rg = c.get("/api/scan/notes/s1")
        assert rg.status_code == 200
        assert rg.json() == {"quivr": "personal RAG"}


def test_empty_note_deletes_row(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        c.post("/api/scan/notes/s1", json={"repo": "quivr", "note": "temp"})
        assert "quivr" in c.get("/api/scan/notes/s1").json()

        # empty string = delete (no zombie empty rows in the table)
        c.post("/api/scan/notes/s1", json={"repo": "quivr", "note": ""})
        assert c.get("/api/scan/notes/s1").json() == {}


def test_notes_are_session_scoped(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[{"name": "quivr"}])
    # second session in the same DB
    asyncio.run(_add_session("s2"))

    with TestClient(app) as c:
        c.post("/api/scan/notes/s1", json={"repo": "quivr", "note": "from s1"})
        c.post("/api/scan/notes/s2", json={"repo": "quivr", "note": "from s2"})

        n1 = c.get("/api/scan/notes/s1").json()
        n2 = c.get("/api/scan/notes/s2").json()
        assert n1 == {"quivr": "from s1"}
        assert n2 == {"quivr": "from s2"}


def test_set_note_requires_repo(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[])
    with TestClient(app) as c:
        r = c.post("/api/scan/notes/s1", json={"repo": "", "note": "x"})
    assert r.status_code == 400


async def _add_session(session_id: str) -> None:
    """Insert a second session row so cross-session isolation can be checked."""
    import database
    async for db in database.get_db():
        await db.execute(
            "INSERT INTO session (id, github_token, github_user, repos_root) VALUES (?,?,?,?)",
            (session_id, "tok", "tester2", "/tmp"),
        )
        await db.commit()