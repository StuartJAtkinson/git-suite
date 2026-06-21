"""reconcile: intent (plan) vs reality (scan) diffing."""
import asyncio

from conftest import insert_scan


def test_reconcile_classifies_every_repo(temp_db, isolated_plan):
    from routers.reconcile import reconcile
    insert_scan(temp_db, repos=[
        {"name": "quivr"},        # absorb target (personal-ai-os)
        {"name": "git-suite"},    # keep
        {"name": "MarvelGraph"},  # archive target (no hub)
        {"name": "random-xyz"},   # unplanned -> orphan
        {"name": "game-hub"},     # a hub -> implicitly keep
    ])
    r = asyncio.run(reconcile("s1"))
    by = {x["name"]: x["verdict"] for x in r["repos"]}
    assert by["quivr"] == "absorb"
    assert by["git-suite"] == "keep"
    assert by["MarvelGraph"] == "archive"
    assert by["random-xyz"] == "orphan"
    assert by["game-hub"] == "keep"
    assert r["stats"]["undecided"] == 1
    assert [o["name"] for o in r["orphans"]] == ["random-xyz"]


def test_reconcile_reports_ghosts(temp_db, isolated_plan):
    from routers.reconcile import reconcile
    # tiny scan: most planned repos are absent -> ghosts
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    r = asyncio.run(reconcile("s1"))
    assert r["stats"]["ghost"] > 0
    ghost_names = {g["name"] for g in r["ghosts"]}
    assert "MarvelGraph" in ghost_names  # planned archive, not in scan


def test_reconcile_splits_deleted_vs_external_ghosts(temp_db, isolated_plan):
    """A ghost seen in a prior scan = real deletion (prunable); one never seen
    = external absorb target (must survive prune). Issue #5."""
    from routers.reconcile import reconcile

    async def _seed():
        async for db in temp_db.get_db():
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) VALUES ('s1','t','u','/')")
            await db.execute(
                "INSERT INTO scan_meta (scan_id, session_id, started_at) VALUES ('old','s1','2000-01-01')")
            await db.execute(
                "INSERT INTO scan_meta (scan_id, session_id, started_at) VALUES ('new','s1','2030-01-01')")
            for sc, name in [("old", "MarvelGraph"), ("old", "quivr"), ("new", "quivr")]:
                await db.execute(
                    """INSERT INTO repos (scan_id,name,super_cat,mid_cat,aim,url,
                       visibility,language,stars,is_fork,pushed_at,topics,archived)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (sc, name, "", "", "", "", "public", "", 0, 0, "", "[]", 0))
            await db.commit()

    asyncio.run(_seed())
    r = asyncio.run(reconcile("s1"))
    was_live = {g["name"]: g["was_live"] for g in r["ghosts"]}
    assert was_live["MarvelGraph"] is True       # in old scan, gone from new
    assert was_live.get("autoEdit_2") is False   # external absorb, never scanned
    assert r["stats"]["ghost_deletable"] >= 1
    assert r["stats"]["ghost_external"] >= 1
