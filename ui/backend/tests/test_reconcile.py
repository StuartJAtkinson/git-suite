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
