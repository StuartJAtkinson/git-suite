"""
cluster.py (router) — one-shot LLM topic grouping across the whole scan.

  GET  /api/cluster/{session_id}?recompute=true    group every orphan into
                                                    themes via a single LLM
                                                    call (bundle → fit →
                                                    discover_themes). Returns
                                                    the same cluster-card
                                                    shape the page renders.

The page does one thing: build the themes bundle, fire one LLM call, render
the result. K-means / anchor / orphan-snap / refresh-forks are gone.
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.reconcile import reconcile

log = logging.getLogger(__name__)
router = APIRouter()


def _own_member_dicts(orphans: list[dict]) -> list[dict]:
    """Normalise the reconcile `orphans` rows into the bundle's per-repo shape
    (name, aim, topics, stars)."""
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
            "stars": r.get("stars") or 0,
        })
    return out


async def _save_result(session_id: str, payload: dict) -> None:
    async for db in get_db():
        await db.execute(
            # `threshold` column is legacy; we store the cluster count k in it.
            "INSERT OR REPLACE INTO cluster_result (session_id, threshold, source, result) "
            "VALUES (?,?,?,?)",
            (session_id, payload.get("k"), payload.get("source"),
             json.dumps(payload)),
        )
        await db.commit()


async def _invalidate(session_id: str) -> None:
    """Drop the cached cluster_result for this session — the next GET re-runs
    the LLM one-shot."""
    async for db in get_db():
        await db.execute(
            "DELETE FROM cluster_result WHERE session_id = ?", (session_id,)
        )
        await db.commit()


async def _propose_themes(session_id: str, orphans: list[dict],
                          hubs: list[str]) -> dict:
    """One-shot LLM topic discovery.

    Bundler flow: build the full scan+README bundle, trim iteratively to the
    active model's 70% token budget (summarising top-25% largest READMEs each
    pass), then ask the LLM to organise the trimmed bundle into themes.
    Falls back to the light `records()` path if the bundler raises.
    """
    from services import distill, topic_llm, themes_bundle

    pool = _own_member_dicts(orphans)
    pool_by_name: dict[str, dict] = {}
    for p in pool:
        nm = p.get("name", "")
        pool_by_name[nm] = {
            "name": nm, "full_name": nm, "source": "owned",
            "stars": p.get("stars", 0),
            "aim": p.get("aim", ""),
        }

    bundle_meta = None
    try:
        bundle_meta = await themes_bundle.build_and_persist(session_id)
        records_in = themes_bundle.to_prompt_records(json.loads(
            themes_bundle._BUNDLE_PATH.read_text(encoding="utf-8")))
    except Exception as exc:
        # Bundler can fail (token not loaded, readmes 404, etc.) — fall back
        # to the lightweight records-only path so the user still gets themes.
        log.warning("themes bundler failed, falling back: %s", str(exc)[:200])
        records_in: list[dict] = []
        for nm in pool_by_name:
            records_in.append({"name": nm, "purpose": "",
                                "entities": [], "domain": ""})
        record_map, _ = await distill.records(pool, stop_on_error=False)
        for r in records_in:
            rec = record_map.get(r["name"]) or {}
            r["purpose"] = rec.get("purpose", "")
            r["entities"] = rec.get("entities", [])
            r["domain"] = rec.get("domain", "")

    themes = await topic_llm.discover_themes(records_in)
    if not themes:
        return {
            "available": False,
            "saved": False,
            "reason": ("LLM topic discovery returned no themes — check Setup → "
                       "LLM Providers and ensure at least one model is reachable."),
            "clusters": [], "hubs": hubs, "orphans_returned": [],
            "mode": "themes",
            "counts": {"owned": len(pool)},
            "bundle": bundle_meta,
        }
    clusters, orphans_returned = topic_llm.themes_to_clusters(themes, pool_by_name)

    payload = {
        "available": True,
        "mode": "themes",
        "k": len(clusters),
        "clusters": clusters,
        "hubs": hubs,
        "orphan_count": len(orphans_returned),
        "orphans_returned": orphans_returned,
        "counts": {"owned": len(pool)},
        "bundle": bundle_meta,
    }
    await _save_result(session_id, payload)
    return payload


async def _load_result(session_id: str) -> dict | None:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT result FROM cluster_result WHERE session_id = ?", (session_id,)
        )
    if not rows:
        return None
    try:
        result = json.loads(rows[0]["result"])
    except Exception:
        return None
    # Stale payloads from before the dedupe guard may have the same repo in
    # two clusters (or in a cluster AND in orphans_returned) — re-run the
    # dedupe so the frontend doesn't choke on each_key_duplicate.
    if isinstance(result, dict) and result.get("clusters"):
        def _key(m: dict) -> str:
            return m.get("full_name") or m.get("repo") or m.get("name") or ""
        seen: set[str] = set()
        kept_clusters = []
        for g in result["clusters"]:
            kept = []
            for m in g.get("members", []):
                k = _key(m)
                if not k or k in seen:
                    continue
                seen.add(k)
                kept.append(m)
            if kept:
                g["members"] = kept
                g["size"] = len(kept)
                kept_clusters.append(g)
        result["clusters"] = kept_clusters
        if result.get("orphans_returned"):
            result["orphans_returned"] = [
                o for o in result["orphans_returned"] if _key(o) not in seen
            ]
    return result


@router.get("/cluster/{session_id}")
async def propose(
    session_id: str,
    recompute: bool = False,
    saved_only: bool = False,
):
    """One-shot LLM topic grouping.

    recompute=true  fresh bundle + LLM call (the page calls this on click)
    saved_only=true return cached result or {available:false} WITHOUT calling
                   the LLM (so the page can rehydrate without burning tokens)
    """
    if not recompute:
        saved = await _load_result(session_id)
        if saved is not None:
            saved["saved"] = True
            return saved
        if saved_only:
            return {"available": False, "saved": False,
                    "reason": "Press ✨ Group by themes (single-shot LLM) "
                              "to organise the scan.",
                    "clusters": []}

    recon = await reconcile(session_id)
    orphans = recon["orphans"]
    plan = plan_store.get_plan()
    hubs = list(plan.get("hubs", {}).keys())
    return await _propose_themes(session_id, orphans, hubs=hubs)


@router.delete("/cluster/{session_id}")
async def reset(session_id: str):
    """Forget the saved grouping so the next visit re-runs the LLM call."""
    async for db in get_db():
        await db.execute(
            "DELETE FROM cluster_result WHERE session_id = ?", (session_id,)
        )
        await db.commit()
    return {"reset": True}


class FormRequest(BaseModel):
    # priority is emergent — left unset at form time; hub order derives from
    # size until someone sets a manual override (promote/order).
    hub_name: str
    priority: int | None = None
    description: str = ""
    boundary: str = ""
    members: list[str]
    promote: str | None = None     # a member repo that becomes the hub itself


@router.post("/cluster/form/{session_id}")
async def form(session_id: str, body: FormRequest):
    """Form a hub from a theme's members. Used by Promote/Hub pages that need
    to commit a cluster to plan_store. The cluster page itself is read-only."""
    name = body.hub_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="hub_name required")
    plan = plan_store.get_plan()

    if name not in plan.get("hubs", {}):
        plan_store.upsert_hub(name, body.priority,
                              body.description, body.boundary)

    absorbed = []
    for m in body.members:
        if m == name or m == body.promote:
            continue                       # the hub repo itself isn't absorbed
        plan_store.set_verdict(m, "absorb", name)
        absorbed.append(m)
    log.info("formed hub %s from cluster (%d absorbed)", name, len(absorbed))
    await _invalidate(session_id)
    return {"hub": name, "absorbed": absorbed, "promoted": body.promote}
