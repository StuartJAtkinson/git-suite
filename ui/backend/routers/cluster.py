"""
cluster.py (router) — assisted hub formation from the scan.

  GET  /api/cluster/{session_id}        propose clusters of unassigned repos
                                         (source=owned legacy behaviour, or
                                         source=mixed default which mixes
                                         owned + forks + stars in one space)
  POST /api/cluster/form/{session_id}   form a hub from a cluster (create/promote/
                                         add-to-existing) and absorb its members
  POST /api/cluster/refresh-forks/{sid} snapshot the user's owned forks so the
                                         mixed-source cluster can include them
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from routers.reconcile import reconcile
from services import cluster
from services.github import list_repos

log = logging.getLogger(__name__)
router = APIRouter()


async def _load_with_topics(sql: str) -> list[dict]:
    """Fetch rows and JSON-decode the `topics` column to a list."""
    async for db in get_db():
        rows = await db.execute_fetchall(sql)
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["topics"] = json.loads(d.get("topics") or "[]")
        except Exception:
            d["topics"] = []
        out.append(d)
    return out


def _own_member_dicts(orphans: list[dict]) -> list[dict]:
    """Normalise the reconcile `orphans` rows into the shape the cluster
    service expects (name, aim, topics, language, stars)."""
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
            "language": r.get("language") or "",
            "stars": r.get("stars") or 0,
        })
    return out


def _apply_forbids(clusters: list[dict], forbid_map: dict[str, list[str]]) -> list[dict]:
    """Drop any cluster member whose stuck `forbid` list mentions either the
    cluster's anchored hub or its suggested name. Returns the dropped members
    so the caller can roll them back into the orphan count.

    In-place: clusters are mutated; empties are removed.
    """
    if not forbid_map:
        return []
    dropped: list[dict] = []
    keep: list[dict] = []
    for c in clusters:
        labels = {c.get("suggested_name") or "", c.get("anchored_to") or ""}
        labels.discard("")
        kept_members = []
        for m in c.get("members", []):
            forbids = forbid_map.get(m.get("repo") or m.get("name") or "", [])
            if any(f in labels for f in forbids):
                dropped.append(m)
            else:
                kept_members.append(m)
        if kept_members:
            c["members"] = kept_members
            c["size"] = len(kept_members)
            keep.append(c)
    clusters[:] = keep
    return dropped


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


async def _load_result(session_id: str) -> dict | None:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT result FROM cluster_result WHERE session_id = ?", (session_id,)
        )
    if not rows:
        return None
    try:
        return json.loads(rows[0]["result"])
    except Exception:
        return None


@router.get("/cluster/{session_id}")
async def propose(
    session_id: str,
    k: int | None = None,
    source: str = "mixed",
    recompute: bool = False,
    saved_only: bool = False,
    anchors: bool = False,
    anchor_threshold: float = 0.7,
    min_cluster_size: int = 1,
):
    """Propose clusters.

    k             target number of clusters (spherical k-means). Omit to let the
                  server pick ~√(n/2).
    source=owned  legacy behaviour: only owned orphans.
    source=mixed  default: owned + forks + stars in one embedding space, each
                  member tagged with `source` so the UI can render its glyph.
    saved_only    return the saved result or {available:false} WITHOUT computing.
                  Clustering spends embedding tokens, so backfill callers (the
                  Scan page) pass this — only the explicit Cluster action
                  (recompute=true) ever triggers a fresh pass.
    anchors       when true, treat every promoted hub as a pinned centroid and
                  re-cluster only the FREE pool (orphans minus hub members).
                  Each resulting cluster is labelled anchored_to=<hub> if its
                  centroid cosine to that hub is >= anchor_threshold. Off by
                  default — the user opts in to anchor-driven re-clustering.
    min_cluster_size
                  drop clusters smaller than this into the unassigned pool
                  instead of forcing tiny singletons into a "cluster".

    The result is persisted per session; without ?recompute=true a saved result
    is returned as-is (no re-embedding/re-distilling).
    """
    if not recompute:
        saved = await _load_result(session_id)
        if saved is not None:
            saved["saved"] = True
            return saved
        if saved_only:
            return {"available": False, "saved": False,
                    "reason": "Not clustered yet — run the Cluster step.",
                    "clusters": []}

    recon = await reconcile(session_id)
    orphans = recon["orphans"]                      # unassigned, live repos
    plan = plan_store.get_plan()
    hubs = list(plan.get("hubs", {}).keys())
    placement = plan_store.repo_placement(plan)
    forbid_map = plan_store.forbids_map(plan)

    # ── anchor-driven mode: drop hub members from the free pool, then snap ─
    if anchors and hubs:
        anchored_names = {
            name for name, place in placement.items()
            if place.get("verdict") in ("absorb", "keep")
        }
        free_orphans = [r for r in orphans if r["name"] not in anchored_names]
        # Hydrate anchored members from the same scan rows so we can re-embed.
        anchored_repos = [r for r in recon["repos"] if r["name"] in anchored_names]
        # Group anchored_repos by hub for snap_to_anchors.
        hub_to_members: dict[str, list[dict]] = {}
        for r in anchored_repos:
            place = placement.get(r["name"]) or {}
            hub = place.get("hub") or r["name"]  # keep-verdict hubs land on themselves
            hub_to_members.setdefault(hub, []).append(_own_member_dicts([r])[0])
    else:
        free_orphans = orphans
        hub_to_members = {}
        anchored_names = set()

    # owned is mixed-with-no-forks-no-stars; the `source` toggle only decides
    # whether forks/stars join the same embedding space. In anchor mode we keep
    # forks/stars out of the free pool — they're external references, not
    # cluster-candidates for *my* portfolio.
    owned = _own_member_dicts(free_orphans)
    forks = [] if source == "owned" or anchors else await _load_with_topics(
        "SELECT * FROM fork ORDER BY pushed_at DESC")
    stars = [] if source == "owned" or anchors else await _load_with_topics(
        "SELECT * FROM starred_repo")

    n = len(owned) + len(forks) + len(stars)
    eff_k = k if k is not None else cluster.default_k(n)
    built = await cluster.build_clusters_mixed(owned, forks, stars, eff_k,
                                               min_cluster_size=max(1, min_cluster_size))
    if built is None:
        return {"available": False,
                "reason": "Embeddings not configured/reachable — set Setup → "
                          "Embeddings (Ollama nomic-embed-text) and ensure "
                          "Ollama is running.",
                "clusters": [], "hubs": hubs, "orphan_count": len(orphans),
                "anchored": list(hub_to_members.keys()),
                "source": source,
                "counts": {"owned": len(owned), "forks": len(forks), "stars": len(stars)}}
    groups, dropped_singletons = built
    if hub_to_members:
        groups = await cluster.snap_to_anchors(groups, hub_to_members,
                                                threshold=anchor_threshold)
    # Forbid pass — drop any cluster member whose `forbids` list mentions the
    # cluster's anchor hub OR its suggested_name; the dropped member rejoins
    # the unassigned pool via the orphan count.
    forb_dropped = _apply_forbids(groups, forbid_map)
    dropped_singletons.extend(forb_dropped)
    payload = {"available": True, "k": eff_k, "clusters": groups, "hubs": hubs,
               "orphan_count": len(orphans) + len(dropped_singletons),
               "orphan_count_returned": len(dropped_singletons),
               "source": source,
               "anchored": list(hub_to_members.keys()),
               "anchor_threshold": anchor_threshold if hub_to_members else None,
               "counts": {"owned": len(owned), "forks": len(forks), "stars": len(stars)}}
    await _save_result(session_id, payload)
    return payload


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
    name = body.hub_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="hub_name required")
    plan = plan_store.get_plan()

    # Create the hub unless we're adding to one that already exists.
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
    return {"hub": name, "absorbed": absorbed, "promoted": body.promote}


@router.post("/cluster/refresh-forks/{session_id}")
async def refresh_forks(session_id: str):
    """Snapshot the user's owned forked repos into the `fork` table.

    Replacement strategy: DELETE then INSERT in one transaction. Forks are
    cheap to re-fetch; the alternative (incremental diff) saves no meaningful
    work and complicates the schema.
    """
    sess = await require_session(session_id)

    rows = []
    async for r in list_repos(sess["github_token"]):
        if not r.get("fork"):
            continue
        parent = r.get("parent") or {}
        rows.append((
            r.get("full_name", ""),
            r.get("name", ""),
            (r.get("owner") or {}).get("login", ""),
            r.get("description") or "",
            json.dumps(r.get("topics") or []),
            r.get("language") or "",
            parent.get("full_name") or "",
            r.get("pushed_at") or "",
            1 if r.get("archived") else 0,
            r.get("html_url") or "",
        ))

    async for db in get_db():
        await db.execute("DELETE FROM fork")
        await db.executemany(
            """INSERT OR REPLACE INTO fork
               (full_name, name, owner, description, topics, language,
                parent_full_name, pushed_at, archived, url)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        await db.commit()

    log.info("forks refresh: %d forks snapshotted for %s",
             len(rows), sess["github_user"])
    return {"count": len(rows)}
