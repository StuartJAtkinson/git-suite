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


@router.post("/plan/blank")
async def blank_plan():
    """Start from scratch — hub shells kept, all repo assignments cleared."""
    return plan_store.blank()


@router.post("/plan/clear")
async def clear_plan():
    """Truly empty plan — hubs removed too. Nothing assumed to be a hub."""
    return plan_store.clear()


class HubUpsert(BaseModel):
    name: str
    layer: int
    priority: int = 3
    description: str = ""
    boundary: str = ""


@router.post("/plan/hub")
async def upsert_hub(body: HubUpsert):
    try:
        return plan_store.upsert_hub(body.name, body.layer, body.priority,
                                     body.description, body.boundary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/plan/hub/{name}")
async def remove_hub(name: str):
    return plan_store.remove_hub(name)


class VerdictRequest(BaseModel):
    repo: str
    verdict: str           # absorb | archive | keep | orphan
    hub: str | None = None


class BoundaryRequest(BaseModel):
    hub: str
    boundary: str


class AlternativeRequest(BaseModel):
    hub: str
    name: str
    kind: str = "oss"        # oss | commercial
    remove: bool = False


@router.post("/plan/hub-alternative")
async def edit_hub_alternative(body: AlternativeRequest):
    """Accept a starred suggestion into (or remove it from) a hub's alternatives."""
    fn = plan_store.remove_hub_alternative if body.remove else plan_store.add_hub_alternative
    try:
        return fn(body.hub, body.name, body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/plan/hub-boundary")
async def set_hub_boundary(body: BoundaryRequest):
    try:
        return plan_store.set_hub_boundary(body.hub, body.boundary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/plan/verdict")
async def set_verdict(body: VerdictRequest):
    try:
        return plan_store.set_verdict(body.repo, body.verdict, body.hub)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
