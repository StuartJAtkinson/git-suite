"""cluster: form action + the one-shot LLM theme grouping."""
import asyncio
import json

from routers.cluster import form, FormRequest, _pool_by_name, import_themes, ImportRequest


def test_form_creates_hub_and_absorbs(isolated_plan):
    isolated_plan.clear()
    res = asyncio.run(form("s1", FormRequest(
        hub_name="map-suite", description="maps", boundary="spatial",
        members=["tilemaker", "streets-gl"],
    )))
    plan = isolated_plan.get_plan()
    assert "map-suite" in plan["hubs"]
    assert set(plan["hubs"]["map-suite"]["absorbs"]) == {"tilemaker", "streets-gl"}
    assert res["absorbed"] == ["tilemaker", "streets-gl"]


def test_form_promote_keeps_member_as_hub(isolated_plan):
    isolated_plan.clear()
    asyncio.run(form("s1", FormRequest(
        hub_name="streets-gl", members=["tilemaker", "streets-gl"],
        promote="streets-gl",
    )))
    plan = isolated_plan.get_plan()
    # promoted repo is the hub, not absorbed into itself
    assert plan["hubs"]["streets-gl"]["absorbs"] == ["tilemaker"]


# -- one-shot LLM topic grouping ----------------------------------------------


def test_propose_returns_available_false_when_no_scan(temp_db):
    """No scan → no orphans → no themes. Page should ask the user to group."""
    res = asyncio.run(__import__("routers.cluster", fromlist=["propose"]).propose(
        "s1", saved_only=True))
    assert res["available"] is False
    assert "Group" in res["reason"]


# -- stars wired into the clustering pool -------------------------------------

def test_pool_by_name_merges_owned_and_stars(temp_db, isolated_plan):
    """Owned orphans (keyed by bare name) and starred repos (keyed by full
    owner/repo) both land in the same pool, correctly tagged by source."""
    from tests.conftest import insert_scan, insert_stars
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "my-owned-tool", "language": "Python"},
    ])
    insert_stars(temp_db, stars=[
        {"full_name": "someorg/cool-lib", "name": "cool-lib",
         "description": "a cool library", "stars": 42},
    ])

    orphans = [{"name": "my-owned-tool", "aim": "", "topics": "[]", "stars": 0}]
    pool, pool_by_name = asyncio.run(_pool_by_name(orphans))

    assert "my-owned-tool" in pool_by_name
    assert pool_by_name["my-owned-tool"]["source"] == "owned"
    assert "someorg/cool-lib" in pool_by_name
    assert pool_by_name["someorg/cool-lib"]["source"] == "star"
    assert pool_by_name["someorg/cool-lib"]["name"] == "cool-lib"
    assert pool_by_name["someorg/cool-lib"]["stars"] == 42
    # Bare short name is NOT a pool_by_name key for stars (only full_name is) —
    # that's the whole point of the disambiguation.
    assert "cool-lib" not in pool_by_name


def test_pool_by_name_disambiguates_same_named_stars(temp_db, isolated_plan):
    """Two different starred repos happen to share a bare name ('server') but
    come from different owners. Both must survive distinctly, keyed by their
    own full_name — a naive bare-name key would silently drop one."""
    from tests.conftest import insert_stars
    insert_stars(temp_db, stars=[
        {"full_name": "alice/server", "name": "server", "description": "alice's"},
        {"full_name": "bob/server", "name": "server", "description": "bob's"},
    ])

    pool, pool_by_name = asyncio.run(_pool_by_name([]))
    assert "alice/server" in pool_by_name
    assert "bob/server" in pool_by_name
    assert len(pool) == 2


def test_import_themes_resolves_star_by_full_name(temp_db, isolated_plan):
    """End-to-end: pasted-back JSON references a star by its disambiguated
    full_name (as the exported prompt instructs); the resulting cluster
    member carries source='star' and the right full_name."""
    from tests.conftest import insert_scan, insert_stars
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "owned-repo", "language": "Python"},
    ])
    insert_stars(temp_db, stars=[
        {"full_name": "someorg/starred-thing", "name": "starred-thing",
         "description": "a starred thing", "stars": 10},
    ])

    fake_reply = json.dumps({"themes": [
        {"name": "test theme", "slug": "test-theme",
         "repo_names": ["owned-repo", "someorg/starred-thing"]},
    ]})
    res = asyncio.run(import_themes("s1", ImportRequest(text=fake_reply)))

    assert res["available"] is True
    assert res["counts"] == {"owned": 1, "star": 1}
    members = {m["repo"]: m for m in res["clusters"][0]["members"]}
    assert members["owned-repo"]["source"] == "owned"
    assert members["starred-thing"]["source"] == "star"
    assert members["starred-thing"]["full_name"] == "someorg/starred-thing"
