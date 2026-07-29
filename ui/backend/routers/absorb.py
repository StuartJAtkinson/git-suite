"""
absorb.py (router) — the Absorb flow: produce + cache the git runbook that
moves a repo's content into a hub with history preserved.

  POST /api/absorb/plan/{session_id}        generate + cache plan
  GET  /api/absorb/plan/{hub}/{repo}/{sid}  retrieve cached plan
  POST /api/absorb/mark-absorbed/{sid}      book-keeping (kept here so the
                                            new surface owns its lifecycle)
"""
import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from services import absorb

log = logging.getLogger(__name__)
router = APIRouter()


# --- validation helpers --------------------------------------------------

def _validate(hub: str, repo: str) -> dict:
    plan = plan_store.get_plan()
    meta = plan.get("hubs", {}).get(hub)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown hub")
    if repo not in meta.get("absorbs", []):
        raise HTTPException(status_code=404, detail="Repo is not an absorb target of this hub")
    return meta


async def _repo_meta(session_id: str, repo: str) -> dict:
    """Pull the enriched scan row for `repo` if present; {} otherwise.

    The absorb plan only ever *reads* this — a missing row means we have no
    language/topics to feed the optional LLM pass, which is fine."""
    async for db in get_db():
        row = await db.execute_fetchall(
            """SELECT r.language, r.aim, r.topics
                 FROM repos r
                 JOIN scan_meta sm ON sm.scan_id = r.scan_id
                WHERE sm.session_id = ?
                  AND r.name = ?
                ORDER BY sm.started_at DESC
                LIMIT 1""",
            (session_id, repo),
        )
    if not row:
        return {}
    try:
        topics = json.loads(row[0]["topics"] or "[]")
    except (TypeError, ValueError):
        topics = []
    return {"language": row[0]["language"], "aim": row[0]["aim"], "topics": topics}


# --- cache key -----------------------------------------------------------

def _cache_key(hub: str, repo: str, payload: dict[str, Any]) -> str:
    """Hash the inputs that actually change the plan so we regenerate when
    `repo_meta`/branch hints move, but not on every retry."""
    blob = json.dumps(
        {k: payload[k] for k in ("source_url", "target_branch", "source_branch",
                                  "module", "strategy") if k in payload},
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


async def _cached(hub: str, repo: str) -> dict | None:
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT plan, notes, strategy, source_branch, target_branch, module, "
            "       source, created_at FROM absorb_plan WHERE hub = ? AND repo = ?",
            (hub, repo),
        )
    if not row:
        return None
    r = row[0]
    return {
        "hub": hub,
        "repo": repo,
        "commands": json.loads(r["plan"]),
        "notes": json.loads(r["notes"]),
        "strategy": r["strategy"],
        "source_branch": r["source_branch"],
        "target_branch": r["target_branch"],
        "module": r["module"],
        "source": r["source"],
        "created_at": r["created_at"],
        "cached": True,
    }


# --- endpoints -----------------------------------------------------------

class PlanRequest(BaseModel):
    hub: str
    repo: str
    source_url: str
    target_branch: str = "main"
    source_branch: str | None = None
    module: str | None = None
    strategy: str | None = None       # "subtree" (default) or "join"
    regenerate: bool = False


@router.post("/absorb/plan/{session_id}")
async def gen_plan(session_id: str, body: PlanRequest):
    if body.strategy and body.strategy not in ("subtree", "join"):
        raise HTTPException(status_code=400, detail="strategy must be 'subtree' or 'join'")
    _validate(body.hub, body.repo)
    if not body.source_url:
        raise HTTPException(status_code=400, detail="source_url is required")

    meta = await _repo_meta(session_id, body.repo)
    cached = None if body.regenerate else await _cached(body.hub, body.repo)
    if cached:
        return cached

    plan = await absorb.plan_for(
        body.hub, body.source_url,
        repo=body.repo, module=body.module, target_branch=body.target_branch,
        source_branch=body.source_branch, strategy=body.strategy,
        repo_meta=meta,
    )
    key = _cache_key(body.hub, body.repo, plan)
    async for db in get_db():
        await db.execute(
            """INSERT OR REPLACE INTO absorb_plan
               (hub, repo, cache_key, plan, notes, strategy, source_branch,
                target_branch, module, source, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (body.hub, body.repo, key,
             json.dumps(plan["commands"]),
             json.dumps(plan["notes"]),
             plan["strategy"], plan["source_branch"], plan["target_branch"],
             plan["module"], plan["source"]),
        )
        await db.commit()
    log.info("absorb plan %s→%s (%s, %d commands, %d notes)",
             body.repo, body.hub, plan["source"],
             len(plan["commands"]), len(plan["notes"]))
    return {
        "hub": body.hub,
        "repo": body.repo,
        "commands": plan["commands"],
        "notes": plan["notes"],
        "checklist": plan["checklist"],
        "strategy": plan["strategy"],
        "source_branch": plan["source_branch"],
        "target_branch": plan["target_branch"],
        "module": plan["module"],
        "remote": plan.get("remote"),
        "source": plan["source"],
        "cached": False,
    }


@router.get("/absorb/plan/{hub}/{repo}/{session_id}")
async def get_plan(hub: str, repo: str, session_id: str):
    _validate(hub, repo)
    cached = await _cached(hub, repo)
    if not cached:
        raise HTTPException(status_code=404, detail="No cached absorb plan — POST to generate one.")
    return cached