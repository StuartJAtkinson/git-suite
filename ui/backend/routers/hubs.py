from fastapi import APIRouter
from pydantic import BaseModel

import plan_store
from database import get_db

router = APIRouter()


@router.get("/hubs")
async def list_hubs():
    plan = plan_store.get_plan()
    hubs = []
    for name, meta in plan.get("hubs", {}).items():
        hubs.append({
            "name": name,
            "priority": meta.get("priority"),
            "description": meta.get("description", ""),
            "boundary": meta.get("boundary", ""),
            "absorbs": meta.get("absorbs", []),
            "alternatives": meta.get("alternatives", {}),
        })
    hubs.sort(key=lambda h: plan_store.hub_sort_key(
        h["priority"], len(h["absorbs"]), h["name"]))
    return hubs


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
