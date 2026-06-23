import aiosqlite
import os
from pathlib import Path

# All persistent state (this file + config.json + plan.json) lives under one
# directory so a single host mount in docker-compose.yml covers everything.
# Defaults to ~/.git-suite for non-Docker runs; docker sets GIT_SUITE_HOME=/app/data.
_HOME = Path(os.environ.get("GIT_SUITE_HOME", str(Path.home() / ".git-suite")))
DB_PATH = _HOME / "state.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS session (
                id          TEXT PRIMARY KEY,
                github_token TEXT NOT NULL,
                github_user  TEXT NOT NULL,
                repos_root   TEXT NOT NULL,  -- dead: app is remote-only, always ""; kept because existing DBs enforce NOT NULL
                created_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS repos (
                scan_id    TEXT NOT NULL,
                name       TEXT NOT NULL,
                full_name  TEXT,
                super_cat  TEXT,
                mid_cat    TEXT,
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

            -- Snapshot of the user's starred repos (refreshed on demand).
            -- Stars are a first-class dedup input: "a project you starred
            -- already does this" signals in the Stars page.
            CREATE TABLE IF NOT EXISTS starred_repo (
                full_name  TEXT PRIMARY KEY,   -- owner/name
                name       TEXT NOT NULL,
                owner      TEXT NOT NULL,
                description TEXT,
                topics     TEXT,               -- JSON array of strings
                language   TEXT,
                stars      INTEGER,
                pushed_at  TEXT,
                archived   INTEGER,            -- 0/1
                url        TEXT,
                fetched_at TEXT DEFAULT (datetime('now'))
            );

            -- Per-repo distilled SEMANTIC RECORD, populated by the LLM distillation
            -- loop on the Scan page. `summary` is the legacy column (the one-line
            -- domain used by older cluster runs); `record` is the structured
            -- form produced by the new prompt: {purpose, entities[], domain}.
            -- `src_hash` invalidates the row when the input text (description +
            -- topics + README url) changes; regen on the next distill pass.
            -- See services/distill.py + routers/scan.py (head/distill/revalidate).
            CREATE TABLE IF NOT EXISTS repo_domain (
                repo       TEXT PRIMARY KEY,   -- full_name or short name
                summary    TEXT,               -- legacy: one-line domain
                record     TEXT,               -- JSON: {purpose, entities[], domain}
                src_hash   TEXT NOT NULL,      -- sha256 of source text
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Per-repo cluster-fit verdict from the revalidate LLM pass.
            -- `cluster_hash` ties the verdict to the cluster snapshot it was
            -- judged against; saved verdicts stay valid until the clustering
            -- (or the repo's purpose) changes.
            CREATE TABLE IF NOT EXISTS repo_verdict (
                repo         TEXT NOT NULL,
                cluster_hash TEXT NOT NULL,
                verdict      TEXT,             -- 'fit' | 'drift' | 'mis-clustered' | ''
                reason       TEXT,
                created_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (repo, cluster_hash)
            );

            -- Last computed clustering per session (the full propose() payload
            -- as JSON). Lets /cluster return the saved result instead of
            -- re-embedding on every tab load, and lets Scan show each repo's
            -- cluster assignment. Recompute overwrites the row.
            CREATE TABLE IF NOT EXISTS cluster_result (
                session_id TEXT PRIMARY KEY,
                threshold  REAL,
                source     TEXT,
                result     TEXT NOT NULL,   -- JSON: full propose() payload
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Cached embedding vectors, keyed by model+text hash.
            CREATE TABLE IF NOT EXISTS embedding (
                key        TEXT PRIMARY KEY,   -- sha256(model + text)
                model      TEXT NOT NULL,
                vector     TEXT NOT NULL,      -- JSON array of floats
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Snapshot of the user's owned FORKED repos (refreshed on demand).
            -- Forks are a first-class cluster input: they cluster alongside
            -- owned repos and stars in services/cluster.build_clusters_mixed.
            CREATE TABLE IF NOT EXISTS fork (
                full_name  TEXT PRIMARY KEY,   -- owner/name
                name       TEXT NOT NULL,
                owner      TEXT NOT NULL,
                description TEXT,
                topics     TEXT,               -- JSON array of strings
                language   TEXT,
                parent_full_name TEXT,         -- what it was forked from
                pushed_at  TEXT,
                archived   INTEGER,            -- 0/1
                url        TEXT,
                fetched_at TEXT DEFAULT (datetime('now'))
            );

            -- Per-hub order + column classification + compat tags + annotations.
            -- One row per (hub, repo). The Order page reads/writes through
            -- routers/order.py. plan.json is NOT touched — this is the only
            -- state-bearing piece of the Order feature.
            --
            -- position: 0-based global ToK rank within the hub (lower = earlier).
            -- is_gather / is_analyse / is_display: 0/1 column flags (a repo can
            --   be in more than one — the checkboxes are classification only).
            -- compat_tags: JSON array of strings (user-named per hub).
            -- feature_annotations: JSON array of strings (populated manually
            --   or by the per-repo LLM Suggest endpoint).
            CREATE TABLE IF NOT EXISTS hub_order (
                hub         TEXT NOT NULL,
                repo        TEXT NOT NULL,
                position    INTEGER NOT NULL,
                is_gather   INTEGER DEFAULT 0,
                is_analyse  INTEGER DEFAULT 0,
                is_display  INTEGER DEFAULT 0,
                compat_tags TEXT,            -- JSON array of strings
                feature_annotations TEXT,   -- JSON array of strings
                updated_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (hub, repo)
            );

            -- Per-hub override of the global compat-tag vocabulary. If a hub
            -- has no row here it inherits services/columns.default_compat_tags().
            CREATE TABLE IF NOT EXISTS hub_compat_tags (
                hub     TEXT PRIMARY KEY,
                tags    TEXT NOT NULL,   -- JSON array of strings
                updated_at TEXT DEFAULT (datetime('now'))
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
    "size": "INTEGER",      # repo size in KB (stub-assessment signal)
    "full_name": "TEXT",    # owner/name — needed for heads/distill/cluster keying
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
