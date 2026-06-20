"""
cluster.py (router) — assisted hub formation from the scan.

  GET  /api/cluster/{session_id}        propose clusters of unassigned repos
                                         (source=owned legacy behaviour, or
                                         source=mixed default which mixes
                                         owned + forks + stars in one space)
  POST /api/cluster/form/{session_id}   form a hub from a cluster (create/promote/
                                         add-to-existing) and absorb its members
  POST /api/cluster/refresh-forks/{sid} snapshot the user's owned forks so the
                                         mixed-source cluster can include them
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from routers.reconcile import reconcile
from services import cluster
from services.github import list_repos

log = logging.getLogger(__name__)
router = APIRouter()


async def _load_with_topics(sql: str) -> list[dict]:
    """Fetch rows and JSON-decode the `topics` column to a list."""
    async for db in get_db():
        rows = await db.execute_fetchall(sql)
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["topics"] = json.loads(d.get("topics") or "[]")
        except Exception:
            d["topics"] = []
        out.append(d)
    return out


def _own_member_dicts(orphans: list[dict]) -> list[dict]:
    """Normalise the reconcile `orphans` rows into the shape the cluster
    service expects (name, aim, topics, language, stars)."""
    out = []
    for r in orphans:
        topics = r.get("topics")
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except Exception:
                topics = []
        out.append({
            "name": r.get("name", ""),
            "aim": r.get("aim") or "",
            "topics": topics or [],
            "language": r.get("language") or "",
            "stars": r.get("stars") or 0,
        })
    return out


@router.get("/cluster/{session_id}")
async def propose(
    session_id: str,
    threshold: float = cluster.DEFAULT_THRESHOLD,
    source: str = "mixed",
):
    """Propose clusters.

    source=owned  legacy behaviour: only owned orphans (one embedding pass).
    source=mixed   default: owned + forks + stars in one embedding space.
                   Each cluster member is tagged with `source` so the UI can
                   render the [O]/[F]/[S] prefix symbol.
    """
    recon = await reconcile(session_id)
    orphans = recon["orphans"]                      # unassigned, live repos
    hubs = list(plan_store.get_plan().get("hubs", {}).keys())

    # owned is mixed-with-no-forks-no-stars; the `source` toggle only decides
    # whether forks/stars join the same embedding space.
    owned = _own_member_dicts(orphans)
    forks = [] if source == "owned" else await _load_with_topics(
        "SELECT * FROM fork ORDER BY pushed_at DESC")
    stars = [] if source == "owned" else await _load_with_topics(
        "SELECT * FROM starred_repo")

    groups = await cluster.build_clusters_mixed(owned, forks, stars, threshold)
    if groups is None:
        return {"available": False,
                "reason": "Embeddings not configured/reachable — set Setup → "
                          "Embeddings (Ollama nomic-embed-text) and ensure "
                          "Ollama is running.",
                "clusters": [], "hubs": hubs, "orphan_count": len(orphans),
                "source": source,
                "counts": {"owned": len(owned), "forks": len(forks), "stars": len(stars)}}
    return {"available": True, "threshold": threshold,
            "clusters": groups, "hubs": hubs, "orphan_count": len(orphans),
            "source": source,
            "counts": {"owned": len(owned), "forks": len(forks), "stars": len(stars)}}


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


@router.post("/cluster/refresh-forks/{session_id}")
async def refresh_forks(session_id: str):
    """Snapshot the user's owned forked repos into the `fork` table.

    Replacement strategy: DELETE then INSERT in one transaction. Forks are
    cheap to re-fetch; the alternative (incremental diff) saves no meaningful
    work and complicates the schema.
    """
    sess = await require_session(session_id)

    rows = []
    async for r in list_repos(sess["github_token"]):
        if not r.get("fork"):
            continue
        parent = r.get("parent") or {}
        rows.append((
            r.get("full_name", ""),
            r.get("name", ""),
            (r.get("owner") or {}).get("login", ""),
            r.get("description") or "",
            json.dumps(r.get("topics") or []),
            r.get("language") or "",
            parent.get("full_name") or "",
            r.get("pushed_at") or "",
            1 if r.get("archived") else 0,
            r.get("html_url") or "",
        ))

    async for db in get_db():
        await db.execute("DELETE FROM fork")
        await db.executemany(
            """INSERT OR REPLACE INTO fork
               (full_name, name, owner, description, topics, language,
                parent_full_name, pushed_at, archived, url)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        await db.commit()

    log.info("forks refresh: %d forks snapshotted for %s",
             len(rows), sess["github_user"])
    return {"count": len(rows)}
