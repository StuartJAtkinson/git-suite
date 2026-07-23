"""
reconcile.py — the reconciliation engine (design philosophy #2).

The whole value of git-suite is the diff between *intent* (the plan) and
*reality* (live GitHub). This router answers one question for every screen:
"where does reality disagree with the plan, and what's the next action?"

It never trusts the verdict stored at scan time — the plan can change after a
scan — so it recomputes every repo's fate from plan_store at request time,
using the scan only for the live repo SET and its metadata.
"""
import json
import logging

from fastapi import APIRouter, HTTPException

import plan_store
from database import get_db

log = logging.getLogger(__name__)
router = APIRouter()


def _stub_reason(r: dict) -> str | None:
    """Flag low-signal 'stub' repos that probably shouldn't survive as their own
    project unless they're function-distinct and integratable. Transparent
    heuristic over enriched scan signal (needs a fresh scan to be meaningful)."""
    size = r.get("size") or 0          # KB
    stars = r.get("stars") or 0
    has_desc = bool((r.get("aim") or "").strip())
    has_topics = bool(r.get("topics"))
    if has_desc or stars > 0 or has_topics:
        return None                    # any real signal -> not a stub
    why = []
    if size < 100:
        why.append(f"{size}KB")
    why.append("no description")
    why.append("no stars/topics")
    if r.get("is_fork"):
        why.append("fork")
    return "likely stub: " + ", ".join(why)


async def _latest_scan_repos(session_id: str) -> tuple[str, list[dict]]:
    """Return (scan_id, repo rows) for the session's most recent scan."""
    async for db in get_db():
        meta = await db.execute_fetchall(
            """SELECT scan_id FROM scan_meta
               WHERE session_id = ? ORDER BY started_at DESC LIMIT 1""",
            (session_id,),
        )
        if not meta:
            raise HTTPException(status_code=404, detail="No scan found — run a scan first")
        scan_id = meta[0]["scan_id"]
        rows = await db.execute_fetchall(
            "SELECT * FROM repos WHERE scan_id = ?", (scan_id,)
        )
    return scan_id, [dict(r) for r in rows]


async def _ever_seen(session_id: str) -> set[str]:
    """Every repo name that has appeared in ANY of this session's scans.

    A planned repo missing from the *latest* scan is a ghost. But there are two
    kinds: one that was scanned before and is now gone (a real deletion — safe
    to prune) versus one that has never been a live owned repo at all (an
    external 'absorb the functionality of' target — must NOT be pruned). Scan
    history is the only honest signal that tells them apart."""
    async for db in get_db():
        rows = await db.execute_fetchall(
            """SELECT DISTINCT r.name FROM repos r
               JOIN scan_meta m ON r.scan_id = m.scan_id
               WHERE m.session_id = ?""",
            (session_id,),
        )
    return {r["name"] for r in rows}


async def _done_actions() -> dict[str, str]:
    """Map repo -> action ('absorbed'|'archived') for executed hub_actions."""
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT repo, action FROM hub_actions"
        )
    return {r["repo"]: r["action"] for r in rows}


@router.get("/reconcile/{session_id}")
async def reconcile(session_id: str):
    scan_id, repos = await _latest_scan_repos(session_id)
    plan = plan_store.get_plan()
    placement = plan_store.repo_placement(plan)
    done = await _done_actions()
    ever_seen = await _ever_seen(session_id)

    live_names = {r["name"] for r in repos}

    # --- per-repo reconciled view ---------------------------------------
    reconciled: list[dict] = []
    counts = {"absorb": 0, "archive": 0, "keep": 0, "orphan": 0}
    for r in repos:
        name = r["name"]
        place = placement.get(name)
        verdict = place["verdict"] if place else "orphan"
        hub = place["hub"] if place else None
        counts[verdict] = counts.get(verdict, 0) + 1
        try:
            topics = json.loads(r["topics"]) if r.get("topics") else []
        except (TypeError, ValueError):
            topics = []
        reconciled.append({
            "name": name,
            "verdict": verdict,
            "hub": hub,
            "aim": r.get("aim") or "",
            "url": r.get("url") or "",
            "visibility": r.get("visibility") or "",
            "done": done.get(name),  # 'absorbed' | 'archived' | None
            # enriched signal (NULL on scans taken before enrichment)
            "stars": r.get("stars") or 0,
            "is_fork": bool(r.get("is_fork")),
            "pushed_at": r.get("pushed_at") or "",
            "topics": topics,
            "archived": bool(r.get("archived")),
            "size": r.get("size") or 0,
            "stub_reason": _stub_reason(r),
        })

    # --- ghosts: planned repos that don't exist live --------------------
    # was_live=True  -> seen in a past scan, now gone = real deletion (prunable)
    # was_live=False -> never an owned repo = external absorb target (keep)
    ghosts = [
        {"name": name, "was_live": name in ever_seen, **place}
        for name, place in placement.items()
        if name not in live_names
    ]

    # --- hub rollup -----------------------------------------------------
    hubs_roll = []
    for hub, meta in plan.get("hubs", {}).items():
        absorbs = meta.get("absorbs", [])
        live_absorbs = [a for a in absorbs if a in live_names]
        absorbed_done = [a for a in absorbs if done.get(a) == "absorbed"]
        archives = [r for r, h in plan.get("archives", {}).items() if h == hub]
        archived_done = [a for a in archives if done.get(a) == "archived"]
        hubs_roll.append({
            "name": hub,
            "priority": meta.get("priority"),
            "description": meta.get("description", ""),
            "boundary": meta.get("boundary", ""),
            "absorb_total": len(absorbs),
            "absorb_live": len(live_absorbs),
            "absorb_done": len(absorbed_done),
            "absorb_pct": round(100 * len(absorbed_done) / len(absorbs)) if absorbs else 0,
            "archive_total": len(archives),
            "archive_done": len(archived_done),
            "ghosts": [a for a in absorbs if a not in live_names],
            "repos": sorted(r["name"] for r in reconciled if r["hub"] == hub),
        })
    # Emergent ordering — manual priority then hub size; no layer taxonomy.
    hubs_roll.sort(key=lambda h: plan_store.hub_sort_key(
        h["priority"], h["absorb_total"], h["name"]))

    orphans = [r for r in reconciled if r["verdict"] == "orphan"]
    stubs = [r for r in reconciled if r["stub_reason"]]
    ghost_deletable = sum(1 for g in ghosts if g["was_live"])

    return {
        "scan_id": scan_id,
        "stats": {
            "live": len(repos),
            **counts,
            "ghost": len(ghosts),
            "ghost_deletable": ghost_deletable,             # real deletions
            "ghost_external": len(ghosts) - ghost_deletable, # external absorbs
            "undecided": len(orphans),
            "stub": len(stubs),
        },
        "repos": reconciled,
        "orphans": orphans,
        "ghosts": ghosts,
        "stubs": stubs,
        "hubs": hubs_roll,
    }
