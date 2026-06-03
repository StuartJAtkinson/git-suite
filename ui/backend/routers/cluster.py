"""
cluster.py (router) — assisted hub formation from the scan.

  GET  /api/cluster/{session}        propose clusters of unassigned repos
  POST /api/cluster/form/{session}   form a hub from a cluster (create/promote/
                                     add-to-existing) and absorb its members
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from routers.reconcile import reconcile
from services import cluster

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/cluster/{session_id}")
async def propose(session_id: str, threshold: float = cluster.DEFAULT_THRESHOLD):
    recon = await reconcile(session_id)
    orphans = recon["orphans"]                      # unassigned, live repos
    hubs = list(plan_store.get_plan().get("hubs", {}).keys())

    groups = await cluster.build_clusters(orphans, threshold)
    if groups is None:
        return {"available": False,
                "reason": "Embeddings not configured/reachable — set Setup → Embeddings "
                          "(Ollama nomic-embed-text) and ensure Ollama is running.",
                "clusters": [], "hubs": hubs, "orphan_count": len(orphans)}

    out = []
    for members in groups:
        s = cluster.suggest_theme(members)
        out.append({
            "suggested_name": s["name"],
            "suggested_description": s["description"],
            "size": len(members),
            "members": [
                {"repo": m["name"], "language": m.get("language", ""),
                 "stars": m.get("stars", 0), "aim": m.get("aim", "")}
                for m in members
            ],
        })
    return {"available": True, "threshold": threshold,
            "clusters": out, "hubs": hubs, "orphan_count": len(orphans)}


class FormRequest(BaseModel):
    hub_name: str
    layer: int = 9
    priority: int = 3
    description: str = ""
    boundary: str = ""
    members: list[str]
    promote: str | None = None     # a member repo that becomes the hub itself


@router.post("/cluster/form/{session_id}")
async def form(session_id: str, body: FormRequest):
    name = body.hub_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="hub_name required")
    plan = plan_store.get_plan()

    # Create the hub unless we're adding to one that already exists.
    if name not in plan.get("hubs", {}):
        plan_store.upsert_hub(name, body.layer, body.priority,
                              body.description, body.boundary)

    absorbed = []
    for m in body.members:
        if m == name or m == body.promote:
            continue                       # the hub repo itself isn't absorbed
        plan_store.set_verdict(m, "absorb", name)
        absorbed.append(m)
    log.info("formed hub %s from cluster (%d absorbed)", name, len(absorbed))
    return {"hub": name, "absorbed": absorbed, "promoted": body.promote}
