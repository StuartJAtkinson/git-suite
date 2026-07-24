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
import itertools
import json
import logging
import re
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.reconcile import reconcile

log = logging.getLogger(__name__)
router = APIRouter()

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your",
    "using", "based", "via", "over", "across", "their", "such", "each",
    "also", "than", "then", "have", "has", "are", "was", "were",
}


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "theme"


def _member_key(m: dict) -> str:
    return m.get("full_name") or m.get("repo") or m.get("name") or ""


def _cluster_tokens(cluster: dict) -> set[str]:
    text = " ".join([
        cluster.get("suggested_name", ""),
        cluster.get("suggested_description", ""),
        *[m.get("domain", "") for m in cluster.get("members", [])],
        *[m.get("aim", "") for m in cluster.get("members", [])],
        *[" ".join(m.get("entities", []) or []) for m in cluster.get("members", [])],
    ])
    tokens = {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}
    return tokens - _STOPWORDS


def _margin_flag(score: float) -> str:
    if score < 0.75:
        return "thin"
    if score < 0.90:
        return "ok"
    return "wide"


async def _ensure_ids(session_id: str, payload: dict) -> dict:
    """Assign a stable id (and slug) to every cluster, once. Persisted
    immediately so merge/split/move/rename calls that reference an id from a
    prior GET keep resolving after this."""
    clusters = payload.get("clusters") or []
    changed = False
    for c in clusters:
        if not c.get("id"):
            c["id"] = uuid.uuid4().hex[:12]
            changed = True
        if not c.get("slug"):
            c["slug"] = _slugify(c.get("suggested_name", ""))
    if changed:
        await _save_result(session_id, payload)
    return payload


def _with_margins(payload: dict) -> dict:
    """Attach pairwise + nearest-neighbour margins (transient — recomputed on
    every read, never persisted). Margin score = 1 - Jaccard(token sets); a
    low score means two clusters read as near-duplicates and should probably
    merge."""
    clusters = payload.get("clusters") or []
    token_sets = {c["id"]: _cluster_tokens(c) for c in clusters}
    pairs = []
    nearest: dict[str, dict] = {}
    for a, b in itertools.combinations(clusters, 2):
        ta, tb = token_sets[a["id"]], token_sets[b["id"]]
        union = ta | tb
        jaccard = len(ta & tb) / len(union) if union else 0.0
        score = round(1 - jaccard, 4)
        flag = _margin_flag(score)
        pairs.append({"a": a["id"], "b": b["id"], "score": score, "flag": flag})
        for x, y in ((a, b), (b, a)):
            cur = nearest.get(x["id"])
            if cur is None or score < cur["score"]:
                nearest[x["id"]] = {"id": y["id"], "name": y.get("suggested_name", ""),
                                     "score": score, "flag": flag}
    pairs.sort(key=lambda p: p["score"])
    payload["margins"] = pairs[:150]
    for c in clusters:
        c["nearest"] = nearest.get(c["id"])
    return payload


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


async def _star_member_dicts() -> list[dict]:
    """Every starred repo, same per-repo shape as _own_member_dicts. Stars
    are a first-class dedup input (a starred project may already cover what
    an owned repo would do), so they ride the same cluster/bundle pipeline —
    not a separate, second-class path."""
    from routers.stars import _load_stars
    stars = await _load_stars()
    out = []
    for s in stars:
        out.append({
            "name": s.get("name", ""),
            "full_name": s.get("full_name", ""),
            "aim": s.get("description") or "",
            "topics": s.get("topics") or [],
            "stars": s.get("stars") or 0,
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


async def _pool_by_name(orphans: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """Owned orphans + every starred repo, merged into one pool. Owned entries
    are keyed by their bare name (unique within one GitHub account); starred
    entries are keyed by full `owner/repo` (bare names collide freely across
    different starred orgs — two different "server" repos is a real thing).
    `pool` (the flat list) is what `distill.records()` consumes; `pool_by_name`
    (keyed dict) is what `topic_llm.themes_to_clusters()` resolves LLM-returned
    repo_names against."""
    pool: list[dict] = []
    pool_by_name: dict[str, dict] = {}

    for p in _own_member_dicts(orphans):
        nm = p.get("name", "")
        if not nm:
            continue
        entry = {
            "name": nm, "full_name": nm, "source": "owned",
            "stars": p.get("stars", 0), "aim": p.get("aim", ""),
        }
        pool.append(entry)
        pool_by_name[nm] = entry

    for s in await _star_member_dicts():
        fn = s.get("full_name", "")
        if not fn:
            continue
        entry = {
            "name": s.get("name", ""), "full_name": fn, "source": "star",
            "stars": s.get("stars", 0), "aim": s.get("aim", ""),
        }
        pool.append(entry)
        pool_by_name[fn] = entry

    return pool, pool_by_name


def _pool_counts(pool: list[dict]) -> dict[str, int]:
    out = {"owned": 0, "star": 0}
    for p in pool:
        out[p.get("source", "owned")] = out.get(p.get("source", "owned"), 0) + 1
    return out


async def _propose_themes(session_id: str, orphans: list[dict],
                          hubs: list[str]) -> dict:
    """One-shot LLM topic discovery.

    Bundler flow: build the full scan+README bundle, trim iteratively to the
    active model's 70% token budget (summarising top-25% largest READMEs each
    pass), then ask the LLM to organise the trimmed bundle into themes.
    Falls back to the light `records()` path if the bundler raises.
    """
    from services import distill, topic_llm, themes_bundle

    pool, pool_by_name = await _pool_by_name(orphans)

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
            "counts": _pool_counts(pool),
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
        "counts": _pool_counts(pool),
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
            if saved.get("available") and saved.get("clusters"):
                saved = await _ensure_ids(session_id, saved)
                saved = _with_margins(saved)
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
    payload = await _propose_themes(session_id, orphans, hubs=hubs)
    if payload.get("available") and payload.get("clusters"):
        payload = await _ensure_ids(session_id, payload)
        payload = _with_margins(payload)
    return payload


@router.delete("/cluster/{session_id}")
async def reset(session_id: str):
    """Forget the saved grouping so the next visit re-runs the LLM call."""
    async for db in get_db():
        await db.execute(
            "DELETE FROM cluster_result WHERE session_id = ?", (session_id,)
        )
        await db.commit()
    return {"reset": True}


@router.get("/cluster/{session_id}/prompt")
async def export_prompt(session_id: str):
    """Build (if missing) + return the full external-LLM prompt as text/plain.
    The internal LLM call gets the same system+user pair; this endpoint just
    inlines the persisted bundle so the user can paste it into any chat LLM
    (Claude.ai, ChatGPT, etc.) without further prep."""
    from fastapi.responses import PlainTextResponse
    from services import themes_bundle

    path = themes_bundle._BUNDLE_PATH
    artefact = None
    try:
        artefact = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Stale or missing — re-run the bundler, then re-read from disk.
    if not artefact or artefact.get("session_id") != session_id:
        await themes_bundle.build_and_persist(session_id)
        artefact = json.loads(path.read_text(encoding="utf-8"))

    prompt = themes_bundle.render_external_prompt(artefact)
    return PlainTextResponse(prompt, media_type="text/plain; charset=utf-8")


class ImportRequest(BaseModel):
    text: str    # the raw text pasted back from the external LLM


@router.post("/cluster/{session_id}/import")
async def import_themes(session_id: str, body: ImportRequest):
    """Take the JSON an external LLM produced (per render_external_prompt's
    EXPECTED RESPONSE contract) and turn it into the same cluster-card shape
    the internal one-shot LLM call produces. Saved + rendered identically."""
    from services import topic_llm

    recon = await reconcile(session_id)
    orphans = recon["orphans"]
    pool, pool_by_name = await _pool_by_name(orphans)
    # Keyed off pool_by_name (not pool[].name) — for stars that key is the
    # disambiguated full_name, which is what the exported prompt told the
    # external LLM to echo back in repo_names. pool[].name for a star entry
    # is the bare short name, which would silently reject every star match.
    known = set(pool_by_name.keys())

    try:
        themes = topic_llm.parse_external_response(body.text, known)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400,
                            detail=f"couldn't parse themes JSON: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=400,
                            detail=f"invalid JSON: {str(exc)[:200]}")
    if not themes:
        raise HTTPException(status_code=400,
                            detail="parsed but no valid themes survived "
                                   "validation (check repo names match "
                                   "exactly)")

    clusters, orphans_returned = topic_llm.themes_to_clusters(themes, pool_by_name)
    plan = plan_store.get_plan()
    payload = {
        "available": True,
        "mode": "themes",
        "source": "external-import",
        "k": len(clusters),
        "clusters": clusters,
        "hubs": list(plan.get("hubs", {}).keys()),
        "orphan_count": len(orphans_returned),
        "orphans_returned": orphans_returned,
        "counts": _pool_counts(pool),
        "bundle": None,
    }
    await _save_result(session_id, payload)
    payload = await _ensure_ids(session_id, payload)
    return _with_margins(payload)


# -- iterative refinement: merge / split / move / rename / delete -----------
# All operate on the saved cluster_result in place. Each loads the saved
# payload, mutates clusters/orphans_returned, re-saves, and returns the same
# augmented (ids + margins) shape the GET endpoint returns, so the frontend
# can just replace its local state with the response.


async def _load_saved_or_404(session_id: str) -> dict:
    saved = await _load_result(session_id)
    if saved is None or not saved.get("available") or not saved.get("clusters"):
        raise HTTPException(status_code=404,
                            detail="no saved clustering to edit — group or import one first")
    return await _ensure_ids(session_id, saved)


def _find_cluster(payload: dict, cluster_id: str) -> dict:
    for c in payload.get("clusters", []):
        if c["id"] == cluster_id:
            return c
    raise HTTPException(status_code=404, detail=f"unknown cluster id {cluster_id!r}")


class MergeRequest(BaseModel):
    a: str
    b: str
    new_name: str | None = None


@router.post("/cluster/{session_id}/merge")
async def merge_clusters(session_id: str, body: MergeRequest):
    payload = await _load_saved_or_404(session_id)
    ca = _find_cluster(payload, body.a)
    cb = _find_cluster(payload, body.b)
    if ca["id"] == cb["id"]:
        raise HTTPException(status_code=400, detail="can't merge a cluster with itself")

    seen = {_member_key(m) for m in ca["members"]}
    members = list(ca["members"])
    for m in cb["members"]:
        k = _member_key(m)
        if k and k not in seen:
            seen.add(k)
            members.append(m)

    merged = {
        "id": uuid.uuid4().hex[:12],
        "suggested_name": body.new_name or f"{ca['suggested_name']} + {cb['suggested_name']}",
        "suggested_description": ca.get("suggested_description") or cb.get("suggested_description") or "",
        "members": members,
        "size": len(members),
        "created_from": [ca["id"], cb["id"]],
    }
    merged["slug"] = _slugify(merged["suggested_name"])
    payload["clusters"] = [c for c in payload["clusters"] if c["id"] not in (ca["id"], cb["id"])]
    payload["clusters"].append(merged)
    payload["k"] = len(payload["clusters"])
    await _save_result(session_id, payload)
    return _with_margins(payload)


class SplitRequest(BaseModel):
    cluster_id: str
    members: list[str]     # repo/full_name keys to peel off into a new cluster
    new_name: str | None = None


@router.post("/cluster/{session_id}/split")
async def split_cluster(session_id: str, body: SplitRequest):
    payload = await _load_saved_or_404(session_id)
    src = _find_cluster(payload, body.cluster_id)
    take = set(body.members)
    if not take:
        raise HTTPException(status_code=400, detail="members required")

    kept, moved = [], []
    for m in src["members"]:
        (moved if _member_key(m) in take else kept).append(m)
    if not moved:
        raise HTTPException(status_code=400, detail="none of the given members are in that cluster")
    if not kept:
        raise HTTPException(status_code=400, detail="split would empty the source cluster — delete it instead")

    src["members"] = kept
    src["size"] = len(kept)
    new_cluster = {
        "id": uuid.uuid4().hex[:12],
        "suggested_name": body.new_name or f"{src['suggested_name']} (split)",
        "suggested_description": "",
        "members": moved,
        "size": len(moved),
        "created_from": [src["id"]],
    }
    new_cluster["slug"] = _slugify(new_cluster["suggested_name"])
    payload["clusters"].append(new_cluster)
    payload["k"] = len(payload["clusters"])
    await _save_result(session_id, payload)
    return _with_margins(payload)


class MoveRequest(BaseModel):
    repo: str                 # member key (full_name or repo/name)
    source: str                 # cluster id, or "orphans"
    dest: str                   # cluster id, or "orphans"


@router.post("/cluster/{session_id}/move")
async def move_member(session_id: str, body: MoveRequest):
    payload = await _load_saved_or_404(session_id)
    if body.source == body.dest:
        return _with_margins(payload)

    def _take_from(loc: str) -> dict | None:
        if loc == "orphans":
            pool = payload.get("orphans_returned", [])
            for i, m in enumerate(pool):
                if _member_key(m) == body.repo:
                    return pool.pop(i)
            return None
        c = _find_cluster(payload, loc)
        for i, m in enumerate(c["members"]):
            if _member_key(m) == body.repo:
                m = c["members"].pop(i)
                c["size"] = len(c["members"])
                return m
        return None

    member = _take_from(body.source)
    if member is None:
        raise HTTPException(status_code=404,
                            detail=f"{body.repo!r} not found in {body.source!r}")

    if body.dest == "orphans":
        payload.setdefault("orphans_returned", []).append(member)
    else:
        c = _find_cluster(payload, body.dest)
        c["members"].append(member)
        c["size"] = len(c["members"])
    payload["orphan_count"] = len(payload.get("orphans_returned", []))
    await _save_result(session_id, payload)
    return _with_margins(payload)


class RenameRequest(BaseModel):
    cluster_id: str
    name: str


@router.post("/cluster/{session_id}/rename")
async def rename_cluster(session_id: str, body: RenameRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    payload = await _load_saved_or_404(session_id)
    c = _find_cluster(payload, body.cluster_id)
    c["suggested_name"] = name
    c["slug"] = _slugify(name)
    await _save_result(session_id, payload)
    return _with_margins(payload)


class DeleteClusterRequest(BaseModel):
    cluster_id: str


@router.post("/cluster/{session_id}/delete")
async def delete_cluster(session_id: str, body: DeleteClusterRequest):
    payload = await _load_saved_or_404(session_id)
    c = _find_cluster(payload, body.cluster_id)
    payload["clusters"] = [x for x in payload["clusters"] if x["id"] != c["id"]]
    payload.setdefault("orphans_returned", []).extend(c["members"])
    payload["k"] = len(payload["clusters"])
    payload["orphan_count"] = len(payload["orphans_returned"])
    await _save_result(session_id, payload)
    return _with_margins(payload)


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
