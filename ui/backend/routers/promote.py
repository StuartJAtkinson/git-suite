"""
promote.py (router) — Step 3 "Own": review owned forks, decide promote/drop,
generate a detach checklist.

  GET  /api/promote/{session_id}      owned forks + upstream status + current
                                      verdict + cluster assignment
  POST /api/promote/decide            set a fork's fate via the plan
                                      (promote->absorb-into-hub/keep, drop->archive)
  POST /api/promote/checklist/{sid}   detach checklist for one fork (LLM or rule)

The decision is an ordinary plan verdict — one source of truth — so the Promote
stage, Triage, and Replan all agree. Only the checklist is promote-specific.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from routers.reconcile import reconcile
from routers.scan import latest_scan, _head_one
from services import promote as promote_svc
from services.github import get_readme

log = logging.getLogger(__name__)
router = APIRouter()


async def _cluster_map(session_id: str) -> dict[str, str]:
    """{repo -> cluster label} from the saved clustering (best-effort)."""
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT result FROM cluster_result WHERE session_id = ?", (session_id,))
    if not rows:
        return {}
    try:
        payload = json.loads(rows[0]["result"])
    except Exception:
        return {}
    out: dict[str, str] = {}
    for cl in payload.get("clusters", []):
        for m in cl.get("members", []):
            out[m.get("repo") or ""] = cl.get("suggested_name", "")
    return out


@router.get("/promote/{session_id}")
async def list_forks(session_id: str):
    """Owned forks from the latest scan, enriched with upstream status (parent,
    private-upstream flag), current plan verdict, and cluster assignment."""
    sess = await require_session(session_id)
    latest = await latest_scan(session_id)
    forks = [r for r in latest["repos"] if r.get("is_fork")]
    hubs = list(plan_store.get_plan().get("hubs", {}).keys())
    if not forks:
        return {"forks": [], "hubs": hubs}

    recon = await reconcile(session_id)
    verdicts = {r["name"]: r for r in recon["repos"]}
    clusters = await _cluster_map(session_id)

    sem = asyncio.Semaphore(8)

    async def head(full_name: str) -> dict:
        async with sem:
            return await _head_one(sess["github_token"], full_name)

    heads = await asyncio.gather(*[
        head(f.get("full_name") or f"{sess['github_user']}/{f['name']}")
        for f in forks])
    head_by_name = {h.get("name") or "": h for h in heads}

    out = []
    for f in forks:
        name = f["name"]
        v = verdicts.get(name, {})
        h = head_by_name.get(name, {})
        out.append({
            "name": name,
            "full_name": f.get("full_name"),
            "aim": f.get("aim") or "",
            "language": f.get("language") or "",
            "pushed_at": f.get("pushed_at") or "",
            "verdict": v.get("verdict", "orphan"),
            "hub": v.get("hub"),
            "cluster": clusters.get(name) or clusters.get(f.get("full_name") or "") or "",
            "parent_full_name": h.get("parent_full_name"),
            "parent_private": h.get("parent_private"),
            "issue": h.get("issue"),
            "message": h.get("message") or "",
        })
    out.sort(key=lambda r: r["name"].lower())
    return {"forks": out, "hubs": hubs}


class DecideRequest(BaseModel):
    repo: str
    decision: str           # promote | drop
    hub: str | None = None  # for promote: absorb into this hub (else keep)


@router.post("/promote/decide")
async def decide(body: DecideRequest):
    """Map a promote/drop decision onto a plan verdict:
      promote + hub -> absorb into hub      promote (no hub) -> keep
      drop          -> archive
    """
    if body.decision == "promote":
        verdict, hub = ("absorb", body.hub) if body.hub else ("keep", None)
    elif body.decision == "drop":
        verdict, hub = "archive", None
    else:
        raise HTTPException(status_code=400, detail="decision must be promote|drop")
    try:
        return plan_store.set_verdict(body.repo, verdict, hub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class ChecklistRequest(BaseModel):
    repo: str
    hub: str | None = None
    parent: str | None = None


@router.post("/promote/checklist/{session_id}")
async def gen_checklist(session_id: str, body: ChecklistRequest):
    """Generate a detach checklist for one fork (LLM-tailored or rule template)."""
    sess = await require_session(session_id)
    latest = await latest_scan(session_id)
    fork = next((r for r in latest["repos"]
                 if r["name"] == body.repo and r.get("is_fork")), None)
    if fork is None:
        raise HTTPException(status_code=404,
                            detail="not an owned fork in the latest scan")
    full_name = fork.get("full_name") or f"{sess['github_user']}/{body.repo}"
    owner, _, repo = full_name.partition("/")
    readme = None
    try:
        readme = await get_readme(sess["github_token"], owner, repo)
    except Exception:
        pass
    return await promote_svc.checklist_for(
        {"name": body.repo, "language": fork.get("language"), "aim": fork.get("aim")},
        body.hub, body.parent, readme)
