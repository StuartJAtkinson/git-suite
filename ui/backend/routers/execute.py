"""
execute.py — turn plan decisions into real GitHub actions (philosophy #4 + #6).

Planning is cheap and reversible; execution is the deliberate, confirmed,
*outward* step. Three action groups, all preview-first and idempotent (they
check current GitHub state, so re-running is safe):

  archive       repos with an 'archive' verdict that are still live
  create-hubs   plan hubs that don't exist on GitHub yet
  push-readmes  hubs whose Integration Roadmap section is missing/stale

  GET  /api/execute/preview/{session}        DRY RUN of all three groups
  POST /api/execute/archive/{session}        batch archive
  POST /api/execute/create-hubs/{session}    batch create hubs
  POST /api/execute/push-readmes/{session}   batch push READMEs
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.reconcile import reconcile
from routers.readme import readme_status, push_hub_readme
from services.github import list_repos, archive_repo, create_repo

log = logging.getLogger(__name__)
router = APIRouter()


async def _session(session_id: str) -> tuple[str, str]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (session_id,)
        )
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid session")
    return rows[0]["github_token"], rows[0]["github_user"]


async def _github_state(token: str, user: str) -> dict[str, bool]:
    """name -> archived?  (authoritative current reality)."""
    state: dict[str, bool] = {}
    async for repo in list_repos(token, user):
        state[repo["name"]] = bool(repo.get("archived"))
    return state


def _archive_plan(recon: dict, plan: dict, gh: dict[str, bool]) -> dict:
    will, already, gone = [], [], []
    for r in recon["repos"]:
        if r["verdict"] != "archive":
            continue
        name = r["name"]
        item = {"repo": name, "hub": plan.get("archives", {}).get(name),
                "language": r["language"], "aim": r["aim"]}
        if name not in gh:
            gone.append(item)
        elif gh[name]:
            already.append(item)
        else:
            will.append(item)
    return {"will_archive": will, "already_archived": already, "gone": gone}


@router.get("/execute/preview/{session_id}")
async def preview(session_id: str):
    token, user = await _session(session_id)
    recon = await reconcile(session_id)
    plan = plan_store.get_plan()
    gh = await _github_state(token, user)
    hub_names = list(plan.get("hubs", {}).keys())

    archive = _archive_plan(recon, plan, gh)
    create_hubs = [h for h in hub_names if h not in gh]
    existing_hubs = [h for h in hub_names if h in gh]
    # README status for existing hubs, fetched in parallel
    readmes = await asyncio.gather(
        *[readme_status(token, user, h, plan) for h in existing_hubs]
    ) if existing_hubs else []

    return {
        "archive": archive,
        "create_hubs": create_hubs,
        "readmes": readmes,
        "counts": {
            "will_archive": len(archive["will_archive"]),
            "already_archived": len(archive["already_archived"]),
            "gone": len(archive["gone"]),
            "create_hubs": len(create_hubs),
            "readmes_stale": sum(1 for r in readmes if r["needs_update"]),
        },
    }


class RepoBatch(BaseModel):
    repos: list[str]


class HubBatch(BaseModel):
    hubs: list[str]


@router.post("/execute/archive/{session_id}")
async def execute_archive(session_id: str, body: RepoBatch):
    token, user = await _session(session_id)
    recon = await reconcile(session_id)
    plan = plan_store.get_plan()
    gh = await _github_state(token, user)
    archivable = {i["repo"] for i in _archive_plan(recon, plan, gh)["will_archive"]}
    archive_hub = plan.get("archives", {})

    results = []
    for repo in body.repos:
        if repo not in archivable:
            results.append({"repo": repo, "status": "skipped"})
            continue
        try:
            await archive_repo(token, user, repo)
        except Exception as exc:
            log.error("archive failed %s: %s", repo, exc)
            results.append({"repo": repo, "status": "error", "detail": str(exc)})
            continue
        async for db in get_db():
            await db.execute(
                "INSERT OR REPLACE INTO hub_actions (hub, repo, action) VALUES (?, ?, 'archived')",
                (archive_hub.get(repo) or "(none)", repo),
            )
            await db.commit()
        results.append({"repo": repo, "status": "archived"})

    return {"archived": sum(1 for r in results if r["status"] == "archived"), "results": results}


@router.post("/execute/create-hubs/{session_id}")
async def execute_create_hubs(session_id: str, body: HubBatch):
    token, user = await _session(session_id)
    plan = plan_store.get_plan()
    gh = await _github_state(token, user)

    results = []
    for hub in body.hubs:
        meta = plan.get("hubs", {}).get(hub)
        if not meta:
            results.append({"hub": hub, "status": "skipped", "detail": "not a plan hub"})
            continue
        if hub in gh:
            results.append({"hub": hub, "status": "exists"})  # idempotent
            continue
        try:
            await create_repo(token, hub, private=True, description=meta.get("description", ""))
        except Exception as exc:
            log.error("create hub failed %s: %s", hub, exc)
            results.append({"hub": hub, "status": "error", "detail": str(exc)})
            continue
        results.append({"hub": hub, "status": "created"})

    return {"created": sum(1 for r in results if r["status"] == "created"), "results": results}


@router.post("/execute/push-readmes/{session_id}")
async def execute_push_readmes(session_id: str, body: HubBatch):
    token, user = await _session(session_id)
    plan = plan_store.get_plan()

    results = []
    for hub in body.hubs:
        if hub not in plan.get("hubs", {}):
            results.append({"hub": hub, "status": "skipped", "detail": "not a plan hub"})
            continue
        try:
            await push_hub_readme(token, user, hub, plan)
        except Exception as exc:
            log.error("push readme failed %s: %s", hub, exc)
            results.append({"hub": hub, "status": "error", "detail": str(exc)})
            continue
        results.append({"hub": hub, "status": "pushed"})

    return {"pushed": sum(1 for r in results if r["status"] == "pushed"), "results": results}
