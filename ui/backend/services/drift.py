"""
drift.py — periodic reconcile snapshots ("portfolio drift").

The reconcile router produces a fresh intent-vs-reality view on every request.
This module persists those snapshots as a time series so the UI can show
how the portfolio has moved since the last manual scan. A background
asyncio task runs on a configurable interval; the router exposes the latest
snapshot plus history.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiosqlite

from database import DB_PATH, get_db

log = logging.getLogger(__name__)

# ponytail: simple service-owned constants — no config layer for one tunable.
DEFAULT_INTERVAL_SECONDS = 3600   # 1 hour
MIN_INTERVAL_SECONDS = 60         # sanity floor so a misconfig can't busy-loop


async def snapshot_now(session_id: str | None = None, source: str = "scheduled") -> int:
    """Compute a fresh reconcile() view and persist it. Returns new row id.

    Lazy-imports the reconcile router to avoid a circular import at module load
    (routers/reconcile.py imports from plan_store; nothing circular here, but
    importing the router from a service module is the wrong layering — we
    inline the bits we need instead)."""
    import plan_store
    from routers.reconcile import _latest_scan_repos, _done_actions, _ever_seen, _stub_reason

    if not session_id:
        # Pick the most recent session that has a scan. Cheap best-effort.
        async for db in get_db():
            row = await db.execute_fetchall(
                """SELECT s.id AS session_id FROM session s
                   JOIN scan_meta m ON s.id = m.session_id
                   ORDER BY m.started_at DESC LIMIT 1"""
            )
        if not row:
            return -1   # nothing to snapshot yet
        session_id = row[0]["session_id"]

    try:
        scan_id, repos = await _latest_scan_repos(session_id)
    except Exception as e:
        log.warning("drift snapshot: no scan for session %s (%s)", session_id, e)
        return -1

    plan = plan_store.get_plan()
    placement = plan_store.repo_placement(plan)
    done = await _done_actions()
    ever_seen = await _ever_seen(session_id)
    live_names = {r["name"] for r in repos}

    counts = {"absorb": 0, "archive": 0, "keep": 0, "orphan": 0}
    stubs = 0
    for r in repos:
        name = r["name"]
        verdict = placement.get(name, {}).get("verdict", "orphan")
        counts[verdict] = counts.get(verdict, 0) + 1
        if _stub_reason(r):
            stubs += 1

    ghosts = sum(1 for name in placement if name not in live_names)
    ghost_deletable = sum(1 for name in placement
                           if name not in live_names and name in ever_seen)

    stats = {
        "live": len(repos),
        **counts,
        "ghost": ghosts,
        "ghost_deletable": ghost_deletable,
        "ghost_external": ghosts - ghost_deletable,
        "undecided": counts["orphan"],
        "stub": stubs,
    }

    hubs: list[dict] = []
    for hub, meta in plan.get("hubs", {}).items():
        absorbs = meta.get("absorbs", [])
        live_absorbs = [a for a in absorbs if a in live_names]
        absorbed_done = [a for a in absorbs if done.get(a) == "absorbed"]
        hubs.append({
            "name": hub,
            "absorb_total": len(absorbs),
            "absorb_live": len(live_absorbs),
            "absorb_done": len(absorbed_done),
            "absorb_pct": round(100 * len(absorbed_done) / len(absorbs)) if absorbs else 0,
        })

    async for db in get_db():
        cur = await db.execute(
            """INSERT INTO drift_snapshot (session_id, stats, hubs, source)
               VALUES (?, ?, ?, ?)""",
            (session_id, json.dumps(stats), json.dumps(hubs), source),
        )
        await db.commit()
        return cur.lastrowid or -1


async def latest_snapshot() -> dict | None:
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT * FROM drift_snapshot ORDER BY taken_at DESC LIMIT 1"
        )
    if not row:
        return None
    return _row_to_dict(row[0])


async def history(limit: int = 50) -> list[dict]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT * FROM drift_snapshot ORDER BY taken_at DESC LIMIT ?",
            (limit,),
        )
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(r: Any) -> dict:
    d = dict(r)
    try:
        d["stats"] = json.loads(d["stats"])
    except (TypeError, ValueError):
        d["stats"] = {}
    try:
        d["hubs"] = json.loads(d["hubs"])
    except (TypeError, ValueError):
        d["hubs"] = []
    return d


class DriftScheduler:
    """Owns the background task that periodically snapshots reconcile state.

    Boot once during FastAPI lifespan; cancel during shutdown. The interval
    is read from `config.json` under `drift.interval_seconds` when the loop
    ticks (so edits in the UI take effect on the next cycle, no restart)."""
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="drift-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _interval(self) -> int:
        """Read the current interval from config.json. Default + floor enforced."""
        import json
        from pathlib import Path
        p = Path.home() / ".git-suite" / "config.json"
        try:
            cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except (OSError, ValueError):
            cfg = {}
        secs = int(cfg.get("drift", {}).get("interval_seconds") or DEFAULT_INTERVAL_SECONDS)
        return max(secs, MIN_INTERVAL_SECONDS)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await snapshot_now(source="scheduled")
            except Exception:
                log.exception("drift snapshot failed")
            secs = await self._interval()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=secs)
            except asyncio.TimeoutError:
                pass


# Module-level singleton — wired by main.py's lifespan.
scheduler = DriftScheduler()
