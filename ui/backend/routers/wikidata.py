"""
wikidata.py (router) — Step 7 (Wikidata-backed install DAG).

  GET  /api/wikidata/dag/{session_id}/{hub}    the DAG for one hub
  POST /api/wikidata/hub/{session_id}          set/unset a hub's wikidata_id

The DAG is built by services/wikidata.fetch_subgraph against Wikidata
SPARQL, cached in the wikidata_subgraph table keyed by the sorted
Q-id set. On SPARQL failure the router returns the local fallback
({source: "local", ...}) so the Install page can render a one-line note
instead of an empty SVG.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from services.wikidata import WdError, fetch_subgraph

log = logging.getLogger(__name__)
router = APIRouter()


def _cache_key(root_qid: str, member_qids: list[str]) -> str:
    """Lexicographically sorted Q-id set — same set, same answer, cache hit."""
    return ":".join(sorted({root_qid} | {m for m in member_qids if m}))


async def _load_cached(key: str) -> dict | None:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT payload FROM wikidata_subgraph WHERE cache_key = ?",
            (key,))
    if not rows:
        return None
    try:
        return json.loads(rows[0]["payload"])
    except Exception:
        return None


async def _persist(key: str, root_qid: str, payload: dict) -> None:
    payload = {**payload, "generated_at": datetime.now(timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z")}
    blob = json.dumps(payload)
    async for db in get_db():
        await db.execute(
            "INSERT OR REPLACE INTO wikidata_subgraph "
            "(cache_key, root_qid, payload) VALUES (?, ?, ?)",
            (key, root_qid, blob))
        await db.commit()


async def _build_hub_dag(hub_name: str, hub: dict) -> dict:
    """The hybrid: local fallback if no Q-id, SPARQL-with-cache if we have one."""
    root_qid = hub.get("wikidata_id")
    if not root_qid:
        return {"source": "local", "nodes": [], "edges": [],
                "note": "no Wikidata id — annotate this hub to enable the DAG"}

    # Member Q-ids come from the absorbs list — for the prototype we treat
    # the absorbs names as identifiers (the user maps them when they set
    # wikidata_id). The cursor is: if a member name already looks like a
    # Q-id, include it; otherwise treat it as a repo leaf.
    # Wires up to a future "annotate member with Q-id" feature without
    # breaking the present walkthrough.
    member_qids = [r for r in hub.get("absorbs", []) if r.startswith("Q")]

    key = _cache_key(root_qid, member_qids)
    cached = await _load_cached(key)
    if cached is not None:
        return {"source": "wikidata", **cached, "cache": "hit"}

    # SPARQL — happy path.
    try:
        async with httpx.AsyncClient() as client:
            subgraph = await fetch_subgraph(client, root_qid, member_qids)
    except WdError as exc:
        log.warning("wikidata: SPARQL failed for hub %s (%s) — local fallback",
                    hub_name, exc)
        return {"source": "local", "nodes": [], "edges": [],
                "note": f"SPARQL unreachable: {exc}",
                "root": root_qid}

    await _persist(key, root_qid, subgraph)
    return {"source": "wikidata", **subgraph, "cache": "miss"}


@router.get("/wikidata/dag/{session_id}/{hub}")
async def get_dag_for_hub(session_id: str, hub: str):
    """The DAG for one hub. Read-only; uses the same cache as the install
    manifest so the two views agree."""
    await require_session(session_id)
    plan = plan_store.get_plan()
    if hub not in plan.get("hubs", {}):
        raise HTTPException(status_code=404, detail=f"unknown hub {hub!r}")
    return await _build_hub_dag(hub, plan["hubs"][hub])


class HubWikidataRequest(BaseModel):
    hub: str
    wikidata_id: str | None = None   # "" or None — clear; "Q12345" — set


@router.post("/wikidata/hub/{session_id}")
async def set_hub_wikidata(session_id: str, body: HubWikidataRequest):
    """Set or clear a hub's Wikidata Q-id. Does not re-fetch the DAG —
    the next GET will (lazy refresh)."""
    await require_session(session_id)
    try:
        return plan_store.set_hub_wikidata_id(body.hub, body.wikidata_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
