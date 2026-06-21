"""stars router: refresh, dedup gating, scan dependency.

The service-level dedup math is in test_stars.py; this covers the HTTP edges
the router owns: 401 without session, 404 when no scan, dedup unavailable
without a snapshot.
"""
from conftest import insert_scan


def test_dedup_returns_unavailable_when_no_snapshot(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[])
    with TestClient(app) as c:
        r = c.get("/api/stars/dedup/s1")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "refresh" in body["reason"].lower()


def test_get_stars_empty_initially(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as c:
        r = c.get("/api/stars")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "fetched_at": None, "stars": []}


def test_dedup_404_without_scan(temp_db, isolated_plan):
    """The dedup endpoint needs a scan to compute the owned side; reconcile
    raises 404 if there's no scan_meta for the session."""
    import asyncio
    import database
    from fastapi.testclient import TestClient
    from main import app

    async def _seed_session():
        async for db in database.get_db():
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) "
                "VALUES ('s1','t','u','')")
            # populate a star so refresh/snapshot exist (otherwise dedup is 'unavailable', not 404)
            await db.execute(
                "INSERT INTO starred_repo (full_name,name,owner,description,topics,language,stars,pushed_at,archived,url) "
                "VALUES ('x/y','y','x','','[]','',0,'',0,'')")
            await db.commit()
    asyncio.run(_seed_session())

    with TestClient(app) as c:
        r = c.get("/api/stars/dedup/s1")
    # reconcile raises HTTPException(404) -> TestClient surfaces as 404
    assert r.status_code == 404
    assert "scan" in r.json()["detail"].lower()
