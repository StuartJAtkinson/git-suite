"""
migration.py (router) — assist absorbing repos into hubs.

  GET  /api/migration/hub/{hub}/{session}        scaffold + per-absorb status
  POST /api/migration/checklist/{session}        generate + cache one checklist
  POST /api/migration/push/{session}             push MIGRATION.md to the hub repo
"""
import base64
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from services import migration
from services.github import get_readme, get_file_sha, push_file

log = logging.getLogger(__name__)
router = APIRouter()


async def _scan_repo_map(session_id: str) -> dict[str, dict]:
    """Latest scan's repos keyed by name (enriched rows)."""
    async for db in get_db():
        meta = await db.execute_fetchall(
            "SELECT scan_id FROM scan_meta WHERE session_id = ? ORDER BY started_at DESC LIMIT 1",
            (session_id,),
        )
        if not meta:
            return {}
        rows = await db.execute_fetchall(
            "SELECT * FROM repos WHERE scan_id = ?", (meta[0]["scan_id"],)
        )
    return {r["name"]: dict(r) for r in rows}


async def _absorbed_set(hub: str) -> set[str]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT repo FROM hub_actions WHERE hub = ? AND action = 'absorbed'", (hub,)
        )
    return {r["repo"] for r in rows}


async def _cached(hub: str) -> dict[str, dict]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT repo, steps, source FROM migration_checklist WHERE hub = ?", (hub,)
        )
    return {r["repo"]: {"steps": json.loads(r["steps"]), "source": r["source"]} for r in rows}


def _enrich_topics(row: dict) -> dict:
    try:
        row["topics"] = json.loads(row.get("topics") or "[]")
    except (TypeError, ValueError):
        row["topics"] = []
    return row


@router.get("/migration/hub/{hub}/{session_id}")
async def hub_migration(hub: str, session_id: str):
    plan = plan_store.get_plan()
    meta = plan.get("hubs", {}).get(hub)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown hub")
    absorbs = meta.get("absorbs", [])
    scan = await _scan_repo_map(session_id)
    done = await _absorbed_set(hub)
    cached = await _cached(hub)
    scaffold = migration.scaffold_for(hub, absorbs)
    by_repo = {s["repo"]: s for s in scaffold}

    items = []
    for repo in absorbs:
        items.append({
            "repo": repo,
            "module": by_repo[repo]["module"],
            "path": by_repo[repo]["path"],
            "live": repo in scan,
            "done": repo in done,
            "language": (scan.get(repo) or {}).get("language") or "",
            "stars": (scan.get(repo) or {}).get("stars") or 0,
            "has_checklist": repo in cached,
            "steps": cached.get(repo, {}).get("steps", []),
            "source": cached.get(repo, {}).get("source"),
        })
    return {
        "hub": hub,
        "layer": meta.get("layer"),
        "description": meta.get("description", ""),
        "absorbs": items,
    }


class ChecklistRequest(BaseModel):
    hub: str
    repo: str
    regenerate: bool = False


@router.post("/migration/checklist/{session_id}")
async def gen_checklist(session_id: str, body: ChecklistRequest):
    plan = plan_store.get_plan()
    meta = plan.get("hubs", {}).get(body.hub)
    if not meta or body.repo not in meta.get("absorbs", []):
        raise HTTPException(status_code=404, detail="Repo is not an absorb target of this hub")

    if not body.regenerate:
        cached = await _cached(body.hub)
        if body.repo in cached:
            return {"hub": body.hub, "repo": body.repo, **cached[body.repo], "cached": True}

    token, owner = await require_session(session_id)
    scan = await _scan_repo_map(session_id)
    repo_row = _enrich_topics(scan.get(body.repo, {"name": body.repo}))
    repo_row.setdefault("name", body.repo)

    readme = None
    if body.repo in scan:                       # only fetch README for live repos
        try:
            readme = await get_readme(token, owner, body.repo)
        except Exception as exc:
            log.warning("readme fetch failed for %s: %s", body.repo, exc)

    hub_meta = {**meta, "name": body.hub}
    result = await migration.checklist_for(repo_row, hub_meta, readme)

    async for db in get_db():
        await db.execute(
            """INSERT OR REPLACE INTO migration_checklist (hub, repo, steps, source)
               VALUES (?, ?, ?, ?)""",
            (body.hub, body.repo, json.dumps(result["steps"]), result["source"]),
        )
        await db.commit()
    log.info("checklist %s→%s (%s, %d steps)", body.repo, body.hub, result["source"], len(result["steps"]))
    return {"hub": body.hub, "repo": body.repo, **result, "cached": False}


class PushRequest(BaseModel):
    hub: str


@router.post("/migration/push/{session_id}")
async def push_migration_md(session_id: str, body: PushRequest):
    plan = plan_store.get_plan()
    meta = plan.get("hubs", {}).get(body.hub)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown hub")
    token, owner = await require_session(session_id)

    data = await hub_migration(body.hub, session_id)   # reuse the assembled items
    content = migration.build_migration_md(body.hub, {**meta, "name": body.hub}, data["absorbs"])

    sha = await get_file_sha(token, owner, body.hub, "MIGRATION.md")
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    try:
        await push_file(token=token, owner=owner, repo=body.hub, path="MIGRATION.md",
                        content_b64=b64, message=f"docs: migration plan [{body.hub}]", sha=sha)
    except Exception as exc:
        log.error("push MIGRATION.md failed for %s: %s", body.hub, exc)
        raise HTTPException(status_code=502, detail=str(exc))
    return {"pushed": True, "hub": body.hub, "bytes": len(content)}
