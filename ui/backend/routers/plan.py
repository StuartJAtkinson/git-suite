"""
plan.py (router) — read and edit the canonical plan (design philosophy #1).

Planning is cheap and local: setting a verdict just edits plan.json. It does
NOT touch GitHub — execution (archive / push README) stays a separate,
deliberate step in the hubs router. This keeps planning fast and reversible.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/plan")
async def get_plan():
    return plan_store.get_plan()


@router.post("/plan/reset")
async def reset_plan():
    """Discard all edits and re-seed from the plan.py defaults."""
    return plan_store.reset()


class VerdictRequest(BaseModel):
    repo: str
    verdict: str           # absorb | archive | keep | orphan
    hub: str | None = None


@router.post("/plan/verdict")
async def set_verdict(body: VerdictRequest):
    try:
        return plan_store.set_verdict(body.repo, body.verdict, body.hub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
