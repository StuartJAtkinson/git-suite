"""stars router: the snapshot endpoint edges the router owns."""


def test_get_stars_empty_initially(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as c:
        r = c.get("/api/stars")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "fetched_at": None, "stars": []}
