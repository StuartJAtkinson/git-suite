"""execute: dry-run preview + idempotent batch archive (GitHub mocked)."""
import asyncio

from conftest import insert_scan


def _mock_github(monkeypatch, state):
    """Patch execute's GitHub calls. `state` maps repo name -> archived bool."""
    import routers.execute as ex

    async def fake_list(token, user):
        for name, archived in state.items():
            yield {"name": name, "archived": archived}

    async def fake_archive(token, owner, repo):
        state[repo] = True  # reflect the mutation back into "reality"

    async def fake_unarchive(token, owner, repo):
        state[repo] = False

    async def fake_delete(token, owner, repo):
        state.pop(repo, None)

    monkeypatch.setattr(ex, "list_repos", fake_list)
    monkeypatch.setattr(ex, "archive_repo", fake_archive)
    monkeypatch.setattr(ex, "unarchive_repo", fake_unarchive)
    monkeypatch.setattr(ex, "delete_repo", fake_delete)
    return ex


def test_preview_lists_will_archive(temp_db, isolated_plan, monkeypatch):
    ex = _mock_github(monkeypatch, {"MarvelGraph": False})
    insert_scan(temp_db, repos=[{"name": "MarvelGraph"}])
    out = asyncio.run(ex.preview("s1"))
    assert out["counts"]["will_archive"] == 1
    assert out["archive"]["will_archive"][0]["repo"] == "MarvelGraph"


def test_archive_is_idempotent(temp_db, isolated_plan, monkeypatch):
    state = {"MarvelGraph": False}
    ex = _mock_github(monkeypatch, state)
    insert_scan(temp_db, repos=[{"name": "MarvelGraph"}])

    first = asyncio.run(ex.execute_archive("s1", ex.RepoBatch(repos=["MarvelGraph"])))
    assert first["archived"] == 1
    assert state["MarvelGraph"] is True

    # second run: repo already archived in "reality" -> skipped, no double action
    second = asyncio.run(ex.execute_archive("s1", ex.RepoBatch(repos=["MarvelGraph"])))
    assert second["archived"] == 0
    assert second["results"][0]["status"] == "skipped"


def test_archive_skips_non_targets(temp_db, isolated_plan, monkeypatch):
    ex = _mock_github(monkeypatch, {"git-suite": False})
    insert_scan(temp_db, repos=[{"name": "git-suite"}])  # keep, not an archive target
    out = asyncio.run(ex.execute_archive("s1", ex.RepoBatch(repos=["git-suite"])))
    assert out["archived"] == 0
    assert out["results"][0]["status"] == "skipped"


def test_create_hubs_creates_missing_only(temp_db, isolated_plan, monkeypatch):
    ex = _mock_github(monkeypatch, {"media-hub": False})  # only media-hub exists
    insert_scan(temp_db, repos=[])
    created = []

    async def fake_create(token, name, private=True, description=""):
        created.append(name)
        return {"name": name}

    monkeypatch.setattr(ex, "create_repo", fake_create)
    out = asyncio.run(ex.execute_create_hubs("s1", ex.HubBatch(hubs=["map-suite", "media-hub"])))
    assert out["created"] == 1
    assert created == ["map-suite"]                       # media-hub skipped (exists)
    statuses = {r["hub"]: r["status"] for r in out["results"]}
    assert statuses == {"map-suite": "created", "media-hub": "exists"}


def test_push_readmes_pushes_per_hub(temp_db, isolated_plan, monkeypatch):
    ex = _mock_github(monkeypatch, {"media-hub": False})
    insert_scan(temp_db, repos=[])
    import routers.readme as rm
    pushed = {}

    async def fake_get_file(token, owner, repo, path):
        return None  # no existing README

    async def fake_push_file(*, token, owner, repo, path, content_b64, message, sha=None):
        import base64
        pushed[repo] = base64.b64decode(content_b64).decode("utf-8")

    monkeypatch.setattr(rm, "get_file", fake_get_file)
    monkeypatch.setattr(rm, "push_file", fake_push_file)
    out = asyncio.run(ex.execute_push_readmes("s1", ex.HubBatch(hubs=["media-hub"])))
    assert out["pushed"] == 1
    assert "Integration Roadmap" in pushed["media-hub"]
    assert "comictagger" in pushed["media-hub"]           # a media-hub absorb


def test_archive_hubs_idempotent(temp_db, isolated_plan, monkeypatch):
    state = {"media-hub": False, "game-hub": True}  # one active, one archived
    ex = _mock_github(monkeypatch, state)
    insert_scan(temp_db, repos=[])
    out = asyncio.run(ex.execute_archive_hubs("s1", ex.HubBatch(hubs=["media-hub", "game-hub", "map-suite"])))
    st = {r["hub"]: r["status"] for r in out["results"]}
    assert st == {"media-hub": "archived", "game-hub": "already-archived", "map-suite": "absent"}
    assert state["media-hub"] is True


def test_unarchive_hub_returns_it(temp_db, isolated_plan, monkeypatch):
    state = {"media-hub": True}
    ex = _mock_github(monkeypatch, state)
    insert_scan(temp_db, repos=[])
    out = asyncio.run(ex.execute_unarchive_hubs("s1", ex.HubBatch(hubs=["media-hub"])))
    assert out["returned"] == 1
    assert state["media-hub"] is False


def test_delete_hub_requires_archived_first(temp_db, isolated_plan, monkeypatch):
    state = {"media-hub": False, "game-hub": True}  # active vs archived
    ex = _mock_github(monkeypatch, state)
    insert_scan(temp_db, repos=[])
    out = asyncio.run(ex.execute_delete_hubs("s1", ex.HubBatch(hubs=["media-hub", "game-hub"])))
    st = {r["hub"]: r["status"] for r in out["results"]}
    assert st["media-hub"] == "skipped"      # active hub never deleted
    assert st["game-hub"] == "deleted"       # archived hub can be deleted
    assert "media-hub" in state and "game-hub" not in state
