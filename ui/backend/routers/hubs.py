import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from services.github import archive_repo

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/hubs")
async def list_hubs():
    plan = plan_store.get_plan()
    hubs = []
    for name, meta in plan.get("hubs", {}).items():
        hubs.append({
            "name": name,
            "layer": meta["layer"],
            "priority": meta["priority"],
            "description": meta["description"],
            "absorbs": meta.get("absorbs", []),
            "alternatives": meta.get("alternatives", {}),
        })
    hubs.sort(key=lambda h: h["layer"])
    return hubs


@router.get("/hubs/{hub}/status")
async def hub_status(hub: str, scan_id: str | None = None):
    plan = plan_store.get_plan()
    if hub not in plan.get("hubs", {}):
        raise HTTPException(status_code=404, detail="Unknown hub")

    absorb_targets = plan["hubs"][hub].get("absorbs", [])
    archive_targets = [r for r, h in plan.get("archives", {}).items() if h == hub]

    async for db in get_db():
        absorbed_rows = await db.execute_fetchall(
            "SELECT repo FROM hub_actions WHERE hub = ? AND action = 'absorbed'", (hub,)
        )
        archived_rows = await db.execute_fetchall(
            "SELECT repo FROM hub_actions WHERE hub = ? AND action = 'archived'", (hub,)
        )
        refs_rows = await db.execute_fetchall(
            "SELECT id, url, name, features FROM commercial_refs WHERE hub = ?", (hub,)
        )

    absorbed = {r["repo"] for r in absorbed_rows}
    archived = {r["repo"] for r in archived_rows}

    import json
    refs = [
        {"id": r["id"], "url": r["url"], "name": r["name"], "features": json.loads(r["features"])}
        for r in refs_rows
    ]

    return {
        "hub": hub,
        "scan_id": scan_id,
        "absorbs": [
            {"repo": r, "done": r in absorbed} for r in absorb_targets
        ],
        "archives": [
            {"repo": r, "done": r in archived} for r in archive_targets
        ],
        "commercial_refs": refs,
    }


class ArchiveRequest(BaseModel):
    session_id: str
    hub: str
    repo: str


@router.post("/hubs/archive")
async def do_archive(body: ArchiveRequest):
    token, owner = await require_session(body.session_id)

    log.info("archiving %s/%s for hub=%s", owner, body.repo, body.hub)
    try:
        await archive_repo(token, owner, body.repo)
    except Exception as exc:
        log.error("archive failed %s: %s", body.repo, exc)
        raise HTTPException(status_code=502, detail=str(exc))

    async for db in get_db():
        await db.execute(
            "INSERT OR REPLACE INTO hub_actions (hub, repo, action) VALUES (?, ?, 'archived')",
            (body.hub, body.repo),
        )
        await db.commit()

    return {"archived": body.repo}


class AbsorbRequest(BaseModel):
    hub: str
    repo: str


@router.post("/hubs/absorb")
async def mark_absorbed(body: AbsorbRequest):
    async for db in get_db():
        await db.execute(
            "INSERT OR REPLACE INTO hub_actions (hub, repo, action) VALUES (?, ?, 'absorbed')",
            (body.hub, body.repo),
        )
        await db.commit()
    return {"absorbed": body.repo}
