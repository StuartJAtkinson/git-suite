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

            -- One iteration of the re-planning loop.
            CREATE TABLE IF NOT EXISTS replan_pass (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL,
                phase       TEXT NOT NULL,   -- 'incremental' | 'replan'
                n_proposals INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            -- A single proposed plan change awaiting human review.
            CREATE TABLE IF NOT EXISTS proposal (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                pass_id      TEXT NOT NULL,
                kind         TEXT NOT NULL,   -- verdict|reassign|ghost-prune|split|new-hub
                target       TEXT NOT NULL,   -- repo name (or hub for structural)
                proposed     TEXT NOT NULL,   -- JSON: {verdict, hub, ...}
                source       TEXT NOT NULL,   -- 'rule' | 'llm'
                confidence   REAL DEFAULT 0,
                rationale    TEXT,
                status       TEXT DEFAULT 'pending',  -- pending|accepted|rejected
                created_at   TEXT DEFAULT (datetime('now')),
                decided_at   TEXT
            );

            -- Generated migration checklists (one per repo→hub), cached.
            CREATE TABLE IF NOT EXISTS migration_checklist (
                hub        TEXT NOT NULL,
                repo       TEXT NOT NULL,
                steps      TEXT NOT NULL,   -- JSON array of strings
                source     TEXT,            -- 'llm' | 'rule'
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (hub, repo)
            );

            -- Append-only log of applied plan changes (how the plan evolved).
            CREATE TABLE IF NOT EXISTS plan_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                target      TEXT NOT NULL,
                kind        TEXT NOT NULL,
                change      TEXT NOT NULL,   -- JSON: {from, to}
                source      TEXT,            -- 'rule' | 'llm' | 'manual'
                rationale   TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        await _migrate(db)
        await db.commit()


# Columns added after the initial schema — applied to existing DBs on startup.
_REPOS_ADDED_COLUMNS = {
    "stars": "INTEGER",
    "is_fork": "INTEGER",
    "pushed_at": "TEXT",
    "topics": "TEXT",       # JSON array of strings
    "archived": "INTEGER",  # 0/1 — repo archived on GitHub at scan time
}


async def _migrate(db) -> None:
    """Idempotently add new columns to existing tables (SQLite has no IF NOT EXISTS for columns)."""
    cur = await db.execute("PRAGMA table_info(repos)")
    existing = {row[1] for row in await cur.fetchall()}
    for col, decl in _REPOS_ADDED_COLUMNS.items():
        if col not in existing:
            await db.execute(f"ALTER TABLE repos ADD COLUMN {col} {decl}")


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
