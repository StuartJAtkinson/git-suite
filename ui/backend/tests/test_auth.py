"""auth: session purge-on-login (one live session per github user)."""
import asyncio

from routers.auth import _purge_other_sessions
from tests.conftest import insert_scan


def test_purge_other_sessions_cascades_scan_and_cluster_result(temp_db):
    # Two old sessions for the same user, each with their own scan + repos,
    # plus a cluster_result row. A third (the one we "keep") is untouched.
    insert_scan(temp_db, session_id="old1", scan_id="sc-old1",
                repos=[{"name": "repo-a"}])
    insert_scan(temp_db, session_id="old2", scan_id="sc-old2",
                repos=[{"name": "repo-b"}])

    async def _seed_extra():
        async for db in temp_db.get_db():
            # insert_scan already wrote "old1"/"old2" sessions with user "tester"
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) "
                "VALUES (?,?,?,?)", ("keep-me", "tok", "tester", ""),
            )
            await db.execute(
                "INSERT INTO cluster_result (session_id, threshold, source, result) "
                "VALUES (?,?,?,?)", ("old1", 1.0, "themes", "{}"),
            )
            await db.commit()

    asyncio.run(_seed_extra())

    async def _purge():
        async for db in temp_db.get_db():
            n = await _purge_other_sessions(db, "tester", keep="keep-me")
            await db.commit()
            return n

    purged = asyncio.run(_purge())
    assert purged == 2

    async def _check():
        async for db in temp_db.get_db():
            sessions = await db.execute_fetchall("SELECT id FROM session")
            repos = await db.execute_fetchall("SELECT name FROM repos")
            scans = await db.execute_fetchall("SELECT scan_id FROM scan_meta")
            clusters = await db.execute_fetchall("SELECT session_id FROM cluster_result")
            return (sorted(r["id"] for r in sessions),
                    sorted(r["name"] for r in repos),
                    sorted(r["scan_id"] for r in scans),
                    [r["session_id"] for r in clusters])

    sessions, repos, scans, clusters = asyncio.run(_check())
    assert sessions == ["keep-me"]
    assert repos == []
    assert scans == []
    assert clusters == []


def test_purge_other_sessions_ignores_other_users(temp_db):
    insert_scan(temp_db, session_id="s1", scan_id="sc1", repos=[{"name": "r1"}])

    async def _seed_other_user():
        async for db in temp_db.get_db():
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) "
                "VALUES (?,?,?,?)", ("other-user-sess", "tok", "someone-else", ""),
            )
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) "
                "VALUES (?,?,?,?)", ("keep-me", "tok", "tester", ""),
            )
            await db.commit()

    asyncio.run(_seed_other_user())

    async def _purge():
        async for db in temp_db.get_db():
            n = await _purge_other_sessions(db, "tester", keep="keep-me")
            await db.commit()
            return n

    purged = asyncio.run(_purge())
    assert purged == 1     # only "s1" (tester's stale session), not other-user-sess

    async def _check():
        async for db in temp_db.get_db():
            rows = await db.execute_fetchall("SELECT id FROM session")
            return sorted(r["id"] for r in rows)

    assert asyncio.run(_check()) == ["keep-me", "other-user-sess"]
