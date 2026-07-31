"""
drift.py — read-only view of the periodic reconcile snapshots.

The work (compute + persist + schedule) lives in services/drift.py. This
router exposes the latest snapshot, a history tail, and a way to trigger a
fresh snapshot on demand.
"""
from fastapi import APIRouter

from services import drift

router = APIRouter()


@router.get("/drift/status")
async def drift_status():
    """Latest snapshot + the interval the scheduler is using."""
    latest = await drift.latest_snapshot()
    import json
    from pathlib import Path
    p = Path.home() / ".git-suite" / "config.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        cfg = {}
    interval = int(cfg.get("drift", {}).get("interval_seconds") or drift.DEFAULT_INTERVAL_SECONDS)
    return {"latest": latest, "interval_seconds": interval}


@router.get("/drift/history")
async def drift_history(limit: int = 50):
    return {"snapshots": await drift.history(limit=limit)}


@router.post("/drift/snapshot")
async def drift_snapshot_now():
    """Force a snapshot now (manual trigger)."""
    sid = await drift.snapshot_now(source="manual")
    return {"id": sid}
