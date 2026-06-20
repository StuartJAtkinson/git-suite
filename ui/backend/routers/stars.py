"""
stars.py — starred-repo snapshot + dedup endpoints.

POST /stars/refresh/{session_id}  — pull all starred repos into starred_repo
GET  /stars                       — snapshot status + rows
GET  /stars/dedup/{session_id}    — owned-vs-starred duplicates + per-hub
                                    starred suggestions (semantic or keyword)
"""
import json
import logging

from fastapi import APIRouter

import plan_store
from database import get_db
from routers.auth import require_session
from routers.reconcile import reconcile
from services import stars as stars_svc
from services.github import list_starred

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stars/refresh/{session_id}")
async def refresh_stars(session_id: str):
    """Snapshot the user's starred repos (replaces the previous snapshot)."""
    sess = await require_session(session_id)
    me = sess["github_user"]

    rows = []
    async for s in list_starred(sess["github_token"]):
        owner = (s.get("owner") or {}).get("login", "")
        if owner == me:
            continue  # starring your own repo is not an external alternative
        rows.append((
            s.get("full_name", ""),
            s.get("name", ""),
            owner,
            s.get("description") or "",
            json.dumps(s.get("topics") or []),
            s.get("language") or "",
            s.get("stargazers_count") or 0,
            s.get("pushed_at") or "",
            1 if s.get("archived") else 0,
            s.get("html_url") or "",
        ))

    async for db in get_db():
        await db.execute("DELETE FROM starred_repo")
        await db.executemany(
            """INSERT OR REPLACE INTO starred_repo
               (full_name, name, owner, description, topics, language,
                stars, pushed_at, archived, url)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        await db.commit()

    log.info("stars refresh: %d starred repos snapshotted for %s", len(rows), me)
    return {"count": len(rows)}


async def _load_stars() -> list[dict]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT * FROM starred_repo ORDER BY stars DESC"
        )
    out = []
    for r in rows:
        d = dict(r)
        d["topics"] = json.loads(d.get("topics") or "[]")
        out.append(d)
    return out


@router.get("/stars")
async def get_stars():
    stars = await _load_stars()
    fetched_at = max((s.get("fetched_at") or "" for s in stars), default=None)
    return {"count": len(stars), "fetched_at": fetched_at, "stars": stars}


@router.get("/stars/dedup/{session_id}")
async def stars_dedup(session_id: str):
    """Match the latest scan + hubs against the starred snapshot."""
    stars = await _load_stars()
    if not stars:
        return {"available": False, "reason": "No starred snapshot — refresh first.",
                "method": None, "duplicates": [], "hub_suggestions": {}}

    recon = await reconcile(session_id)
    plan = plan_store.get_plan()
    result = await stars_svc.dedup(recon["repos"], stars, plan.get("hubs", {}))
    result["available"] = True
    result["star_count"] = len(stars)
    return result
