import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent / "state.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS session (
                id          TEXT PRIMARY KEY,
                github_token TEXT NOT NULL,
                github_user  TEXT NOT NULL,
                repos_root   TEXT NOT NULL,
                created_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS repos (
                scan_id    TEXT NOT NULL,
                name       TEXT NOT NULL,
                super_cat  TEXT,
                mid_cat    TEXT,
                fine_cat   TEXT,
                aim        TEXT,
                url        TEXT,
                visibility TEXT,
                language   TEXT,
                PRIMARY KEY (scan_id, name)
            );

            CREATE TABLE IF NOT EXISTS scan_meta (
                scan_id    TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                repo_count INTEGER,
                started_at TEXT DEFAULT (datetime('now')),
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS commercial_refs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                hub        TEXT NOT NULL,
                url        TEXT NOT NULL,
                name       TEXT NOT NULL,
                features   TEXT NOT NULL,   -- JSON array of strings
                added_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS hub_actions (
                hub      TEXT NOT NULL,
                repo     TEXT NOT NULL,
                action   TEXT NOT NULL,    -- 'absorbed' | 'archived'
                done_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (hub, repo)
            );
        """)
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
