"""
replan.py (router) — drive the iterative re-planning loop.

  POST /api/replan/pass/{session_id}     run one pass, store proposals
  GET  /api/replan/state/{session_id}    phase + counts (for the UI banner)
  GET  /api/replan/proposals             pending proposals (latest first)
  POST /api/replan/proposal/{id}/accept  apply to plan_store + log history
  POST /api/replan/proposal/{id}/reject  dismiss
  GET  /api/replan/history               applied changes over time

Running a pass is read-only (proposes). Accepting is the deliberate write —
planning stays cheap, application stays auditable (philosophy #4 + #6).
"""
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException

import plan_store
from database import get_db
from routers.reconcile import reconcile
from services.replan import generate_proposals

log = logging.getLogger(__name__)
router = APIRouter()

# Accepting these kinds mutates the plan; the rest are advisory.
_APPLICABLE = {"verdict", "ghost-prune", "reassign"}


@router.get("/replan/state/{session_id}")
async def state(session_id: str):
    recon = await reconcile(session_id)
    undecided = recon["stats"]["undecided"]
    async for db in get_db():
        pending = await db.execute_fetchall(
            "SELECT COUNT(*) AS n FROM proposal WHERE status = 'pending'"
        )
    return {
        "phase": "incremental" if undecided > 0 else "replan",
        "undecided": undecided,
        "ghosts": recon["stats"]["ghost"],
        "pending_proposals": pending[0]["n"],
        "stats": recon["stats"],
    }


@router.post("/replan/pass/{session_id}")
async def run_pass(session_id: str):
    recon = await reconcile(session_id)
    phase, proposals = await generate_proposals(recon)

    pass_id = str(uuid.uuid4())
    async for db in get_db():
        await db.execute(
            "INSERT INTO replan_pass (id, session_id, phase, n_proposals) VALUES (?, ?, ?, ?)",
            (pass_id, session_id, phase, len(proposals)),
        )
        # Supersede any still-pending proposals from older passes to avoid dupes.
        await db.execute("UPDATE proposal SET status = 'superseded' WHERE status = 'pending'")
        for p in proposals:
            await db.execute(
                """INSERT INTO proposal
                   (pass_id, kind, target, proposed, source, confidence, rationale)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pass_id, p["kind"], p["target"], json.dumps(p["proposed"]),
                 p["source"], p["confidence"], p["rationale"]),
            )
        await db.commit()

    log.info("replan pass %s (%s) — %d proposals", pass_id, phase, len(proposals))
    return {"pass_id": pass_id, "phase": phase, "count": len(proposals),
            "proposals": await _pending()}


async def _pending() -> list[dict]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            """SELECT * FROM proposal WHERE status = 'pending'
               ORDER BY (kind='verdict') DESC, confidence DESC, id"""
        )
    out = []
    for r in rows:
        d = dict(r)
        d["proposed"] = json.loads(d["proposed"])
        out.append(d)
    return out


@router.get("/replan/proposals")
async def proposals():
    return await _pending()


@router.post("/replan/proposal/{proposal_id}/accept")
async def accept(proposal_id: int):
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT * FROM proposal WHERE id = ?", (proposal_id,)
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Unknown proposal")
    p = dict(rows[0])
    proposed = json.loads(p["proposed"])

    applied = False
    if p["kind"] in _APPLICABLE:
        before = plan_store.repo_placement().get(p["target"])
        try:
            plan_store.set_verdict(p["target"], proposed["verdict"], proposed.get("hub"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        applied = True
        async for db in get_db():
            await db.execute(
                """INSERT INTO plan_history (target, kind, change, source, rationale)
                   VALUES (?, ?, ?, ?, ?)""",
                (p["target"], p["kind"],
                 json.dumps({"from": before, "to": proposed}),
                 p["source"], p["rationale"]),
            )
            await db.commit()
    else:
        # advisory (split / new-hub): record acknowledgement only
        async for db in get_db():
            await db.execute(
                """INSERT INTO plan_history (target, kind, change, source, rationale)
                   VALUES (?, ?, ?, ?, ?)""",
                (p["target"], p["kind"], json.dumps({"advisory": proposed}),
                 p["source"], p["rationale"]),
            )
            await db.commit()

    async for db in get_db():
        await db.execute(
            "UPDATE proposal SET status = 'accepted', decided_at = datetime('now') WHERE id = ?",
            (proposal_id,),
        )
        await db.commit()
    return {"accepted": proposal_id, "applied": applied}


@router.post("/replan/proposal/{proposal_id}/reject")
async def reject(proposal_id: int):
    async for db in get_db():
        await db.execute(
            "UPDATE proposal SET status = 'rejected', decided_at = datetime('now') WHERE id = ?",
            (proposal_id,),
        )
        await db.commit()
    return {"rejected": proposal_id}


@router.post("/replan/prune-ghosts/{session_id}")
async def prune_ghosts(session_id: str):
    """Drop every planned repo that no longer exists on GitHub — a repo that's
    gone is a conscious deletion, so it should leave the plan entirely."""
    recon = await reconcile(session_id)
    pruned = []
    for ghost in recon["ghosts"]:
        name = ghost["name"]
        before = plan_store.repo_placement().get(name)
        plan_store.set_verdict(name, "orphan")   # unassign = remove from plan
        async for db in get_db():
            await db.execute(
                """INSERT INTO plan_history (target, kind, change, source, rationale)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, "ghost-prune", json.dumps({"from": before, "to": None}),
                 "manual", "repo no longer on GitHub — pruned from plan"),
            )
            await db.commit()
        pruned.append(name)
    log.info("pruned %d ghosts", len(pruned))
    return {"pruned": len(pruned), "repos": pruned}


@router.get("/replan/history")
async def history(limit: int = 100):
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT * FROM plan_history ORDER BY id DESC LIMIT ?", (limit,)
        )
    out = []
    for r in rows:
        d = dict(r)
        d["change"] = json.loads(d["change"])
        out.append(d)
    return out
