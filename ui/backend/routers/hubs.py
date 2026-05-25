from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db
from plan import HUB_META, HUB_ABSORBS, HUB_ALTERNATIVES, ARCHIVE_HUB, KEEP_AS_IS
from services.github import archive_repo

router = APIRouter()


@router.get("/hubs")
async def list_hubs():
    hubs = []
    for name, meta in HUB_META.items():
        hubs.append({
            "name": name,
            "layer": meta["layer"],
            "priority": meta["priority"],
            "description": meta["description"],
            "absorbs": HUB_ABSORBS.get(name, []),
            "alternatives": HUB_ALTERNATIVES.get(name, {}),
        })
    hubs.sort(key=lambda h: h["layer"])
    return hubs


@router.get("/hubs/{hub}/status")
async def hub_status(hub: str, scan_id: str):
    if hub not in HUB_META:
        raise HTTPException(status_code=404, detail="Unknown hub")

    absorb_targets = HUB_ABSORBS.get(hub, [])
    archive_targets = [r for r, h in ARCHIVE_HUB.items() if h == hub]

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
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (body.session_id,)
        )
        if not row:
            raise HTTPException(status_code=401, detail="Invalid session")
        token = row[0]["github_token"]
        owner = row[0]["github_user"]

    try:
        await archive_repo(token, owner, body.repo)
    except Exception as exc:
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
