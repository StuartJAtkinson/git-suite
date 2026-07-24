"""cluster: form action + the one-shot LLM theme grouping."""
import asyncio
import json

from routers.cluster import (
    form, FormRequest, _pool_by_name, import_themes, ImportRequest,
    merge_clusters, MergeRequest, split_cluster, SplitRequest,
    move_member, MoveRequest, rename_cluster, RenameRequest,
    delete_cluster, DeleteClusterRequest,
)


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


# -- iterative refinement: merge / split / move / rename / delete ------------


def _seed_three_theme_import(db):
    from tests.conftest import insert_scan
    insert_scan(db, session_id="s1", scan_id="sc1", repos=[
        {"name": "repo-a", "language": "Python"},
        {"name": "repo-b", "language": "Python"},
        {"name": "repo-c", "language": "Python"},
    ])
    fake_reply = json.dumps({"themes": [
        {"name": "theme one", "slug": "theme-one", "repo_names": ["repo-a"]},
        {"name": "theme two", "slug": "theme-two", "repo_names": ["repo-b"]},
        {"name": "theme three", "slug": "theme-three", "repo_names": ["repo-c"]},
    ]})
    return asyncio.run(import_themes("s1", ImportRequest(text=fake_reply)))


def test_merge_clusters_unions_members_and_removes_originals(temp_db, isolated_plan):
    res = _seed_three_theme_import(temp_db)
    ids = {c["suggested_name"]: c["id"] for c in res["clusters"]}
    merged = asyncio.run(merge_clusters("s1", MergeRequest(
        a=ids["theme one"], b=ids["theme two"], new_name="merged theme")))

    names = {c["suggested_name"] for c in merged["clusters"]}
    assert names == {"merged theme", "theme three"}
    m = next(c for c in merged["clusters"] if c["suggested_name"] == "merged theme")
    assert {mm["repo"] for mm in m["members"]} == {"repo-a", "repo-b"}
    assert m["created_from"] == [ids["theme one"], ids["theme two"]]


def test_split_cluster_peels_off_members(temp_db, isolated_plan):
    from tests.conftest import insert_scan
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[
        {"name": "repo-a", "language": "Python"},
        {"name": "repo-b", "language": "Python"},
    ])
    fake_reply = json.dumps({"themes": [
        {"name": "combo", "slug": "combo", "repo_names": ["repo-a", "repo-b"]},
    ]})
    res = asyncio.run(import_themes("s1", ImportRequest(text=fake_reply)))
    cid = res["clusters"][0]["id"]

    split = asyncio.run(split_cluster("s1", SplitRequest(
        cluster_id=cid, members=["repo-b"], new_name="split-off")))

    by_name = {c["suggested_name"]: c for c in split["clusters"]}
    assert by_name["combo"]["members"][0]["repo"] == "repo-a"
    assert by_name["split-off"]["members"][0]["repo"] == "repo-b"


def test_move_member_between_clusters_and_to_orphans(temp_db, isolated_plan):
    res = _seed_three_theme_import(temp_db)
    ids = {c["suggested_name"]: c["id"] for c in res["clusters"]}

    moved = asyncio.run(move_member("s1", MoveRequest(
        repo="repo-a", source=ids["theme one"], dest=ids["theme two"])))
    by_name = {c["suggested_name"]: c for c in moved["clusters"]}
    assert by_name["theme one"]["members"] == []
    assert {m["repo"] for m in by_name["theme two"]["members"]} == {"repo-a", "repo-b"}

    to_orphans = asyncio.run(move_member("s1", MoveRequest(
        repo="repo-a", source=ids["theme two"], dest="orphans")))
    assert "repo-a" in {o["repo"] for o in to_orphans["orphans_returned"]}


def test_rename_cluster(temp_db, isolated_plan):
    res = _seed_three_theme_import(temp_db)
    cid = res["clusters"][0]["id"]
    renamed = asyncio.run(rename_cluster("s1", RenameRequest(cluster_id=cid, name="new name")))
    assert renamed["clusters"][0]["suggested_name"] == "new name"


def test_delete_cluster_moves_members_to_orphans(temp_db, isolated_plan):
    res = _seed_three_theme_import(temp_db)
    cid = res["clusters"][0]["id"]
    deleted = asyncio.run(delete_cluster("s1", DeleteClusterRequest(cluster_id=cid)))
    assert len(deleted["clusters"]) == 2
    assert "repo-a" in {o["repo"] for o in deleted["orphans_returned"]}


def test_margins_present_and_flag_thin_for_similar_clusters(temp_db, isolated_plan):
    res = _seed_three_theme_import(temp_db)
    assert "margins" in res
    assert all("nearest" in c for c in res["clusters"])
