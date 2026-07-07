"""
cluster.py — assisted group formation.

Embeds the unassigned repos and groups them into a target number of clusters
(spherical k-means over the cached vectors), then suggests a theme per cluster.
The user promotes a member to be the hub or names a new one (with a description
that becomes the hub's LLM-alignment boundary).

Re-clustering: once a cluster has been promoted to a hub, the next pass can
treat that hub's members as anchors — its centroid is pinned, the rest of the
portfolio re-clusters around it, and each free cluster either snaps into the
nearest anchor (cosine >= threshold) or stays free. See snap_to_anchors().

No heavy ML deps: k-means is pure-Python Lloyd's iteration (see _kmeans).
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter

from services import distill, embeddings

log = logging.getLogger(__name__)

# nomic-embed-text was trained with task prefixes; "clustering:" is the right one
# and sharpens separation. Harmless for OpenAI embeddings.
_EMBED_PREFIX = "clustering: "

_STOPWORDS = {"the", "and", "for", "with", "api", "app", "tool", "tools",
              "data", "repo", "test", "main", "core", "lib", "project"}


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def default_k(n: int) -> int:
    """A sane target cluster count for n repos when the user hasn't picked one.
    Returns ~sqrt(n) — tighter than the older sqrt(n/2), because the
    cluster_text composition already does most of the semantic work and the
    user wants granular columns, not 5 giant ones.
    """
    return max(2, round(math.sqrt(n))) if n > 3 else max(1, n)


def _kmeans(vectors: list[list[float]], k: int, iters: int = 30) -> list[list[int]]:
    """Spherical k-means (cosine) → exactly up-to-k clusters, no threshold to
    guess and no single-linkage chaining.

    Deterministic farthest-point init (seed 0, then repeatedly add the point
    least similar to any chosen seed) so identical inputs give identical groups.
    Empty clusters are dropped. Returns member-index lists.

    # ponytail: pure-Python Lloyd's iteration over the cached vectors — no
    # numpy/sklearn. Fine at portfolio scale (~hundreds of repos); reach for a
    # real BLAS only if n grows into the thousands.
    """
    n = len(vectors)
    k = max(1, min(k, n))
    pts = [_unit(v) for v in vectors]

    seeds = [0]
    while len(seeds) < k:
        far_i, far_sim = -1, 2.0
        for i in range(n):
            if i in seeds:
                continue
            sim = max(_dot(pts[i], pts[s]) for s in seeds)
            if sim < far_sim:
                far_sim, far_i = sim, i
        if far_i < 0:
            break
        seeds.append(far_i)
    centroids = [pts[s][:] for s in seeds]

    assign = [-1] * n
    dim = len(pts[0]) if pts else 0
    for _ in range(iters):
        changed = False
        for i in range(n):
            best_c, best_sim = 0, -2.0
            for c, cen in enumerate(centroids):
                sim = _dot(pts[i], cen)
                if sim > best_sim:
                    best_sim, best_c = sim, c
            if assign[i] != best_c:
                assign[i] = best_c
                changed = True
        sums = [[0.0] * dim for _ in centroids]
        cnt = [0] * len(centroids)
        for i in range(n):
            c = assign[i]
            cnt[c] += 1
            row = sums[c]
            for d, x in enumerate(pts[i]):
                row[d] += x
        for c in range(len(centroids)):
            if cnt[c]:
                centroids[c] = _unit(sums[c])
        if not changed:
            break

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(assign[i], []).append(i)
    return list(groups.values())


def suggest_theme(members: list[dict]) -> dict:
    """Rule-based name + description from shared topics / name tokens."""
    cnt: Counter = Counter()
    for m in members:
        for t in (m.get("topics") or []):
            cnt[t.lower()] += 2
        for w in m["name"].replace("-", " ").replace("_", " ").split():
            w = w.lower()
            if len(w) > 3 and w not in _STOPWORDS:
                cnt[w] += 1
    top = [w for w, _ in cnt.most_common(3)]
    name = f"{top[0]}-hub" if top else "new-hub"
    desc = ("Unifies repos around " + ", ".join(top) + ".") if top else ""
    return {"name": name, "description": desc, "keywords": top}


def _text_for(r: dict) -> str:
    """Build the embedding text for any source dict. Branches the field names
    so owned repos (aim/topics), forks (description/topics) and stars
    (description/topics) all feed the same vector space."""
    parts = [r.get("name", "")]
    parts.append(r.get("aim") or r.get("description") or "")
    topics = r.get("topics") or []
    if isinstance(topics, str):
        try:
            topics = json.loads(topics)
        except Exception:
            topics = []
    parts.append(" ".join(topics))
    return ". ".join(p for p in parts if p)


async def build_clusters_mixed(
    owned: list[dict],
    forks: list[dict],
    stars: list[dict],
    k: int | None = None,
    min_cluster_size: int = 1,
    coherence_floor: float = 0.40,
) -> tuple[list[dict], list[dict]] | None:
    """Cluster owned + forks + stars in one embedding space.

    Each repo is first distilled to a one-line semantic domain (LLM, cached),
    then that distillation is embedded (with the nomic `clustering:` prefix) and
    partitioned into `k` groups by spherical k-means. `k` defaults to ~√(n/2).

    Returns `(clusters, orphans_returned)`:
      clusters: list of cluster dicts:
        {
          "members": [{"repo": ..., "source": "owned"|"fork"|"star", ...}, ...],
          "suggested_name": ...,
          "suggested_description": ...,
        }
      orphans_returned: repos that came out below `min_cluster_size` and were
        kept out of any cluster. Caller merges them into the unassigned pool.

    Returns None if embeddings are unavailable (caller can show a clear
    "configure embeddings" message). Cluster ordering is largest-first.
    Each member is tagged with its source so the UI can render the source glyph.
    """
    if not embeddings.has_embeddings():
        return None
    if not (owned or forks or stars):
        return None

    def _tag(r: dict, source: str) -> dict:
        out = dict(r)
        out["source"] = source
        # Normalise the description field so the router can render the same
        # `aim` key for all sources.
        if source != "owned" and not out.get("aim"):
            out["aim"] = out.get("description") or ""
        return out

    pool: list[dict] = []
    for r in owned:
        pool.append(_tag(r, "owned"))
    for r in forks:
        pool.append(_tag(r, "fork"))
    for r in stars:
        pool.append(_tag(r, "star"))
    # Stable order → deterministic k-means seeding (and persisted assignments
    # that don't churn between identical re-runs).
    pool.sort(key=lambda r: (r.get("name") or r.get("repo") or "").lower())

    # Distil each repo to a structured record (purpose/entities/domain), then
    # embed a tightly-weighted signal: purpose (what humans read on hover) +
    # entities (the real-world nouns) repeated for emphasis, with the bare
    # domain DROPPED when it's a generic over-broad category. Without this
    # the model happily groups 100+ unrelated repos into "software
    # development" / "data" / "computer" hubs — everything looks similar
    # because the embedding sees the same generic noun everywhere.
    record_map, _ = await distill.records(pool, stop_on_error=False)
    _BLOATED_DOMAINS = {
        "software development", "software", "development", "programming",
        "computer", "computing", "data", "data processing", "data science",
        "automation", "tool", "tools", "library", "libraries", "framework",
        "utilities", "utility", "system", "systems", "app", "apps",
        "web development", "web", "machine learning", "ai", "open source",
        "developer tools", "development tools", "general purpose",
    }
    def _is_broad(domain: str) -> bool:
        d = (domain or "").strip().lower()
        if not d:
            return True
        # Reject if any token (or the whole phrase) is in the bloated set.
        tokens = {d, *(d.split())}
        return bool(tokens & _BLOATED_DOMAINS)
    def _cluster_text(r: dict) -> str:
        rec = record_map.get(distill._key(r)) or {}
        purpose = (rec.get("purpose") or "").strip()
        entities = rec.get("entities") or []
        domain = (rec.get("domain") or "").strip()
        # Compose: purpose first (sentence-level meaning), entities x3
        # (nomic up-weights repeated tokens in cosine), then a domain token
        # ONLY if it's not a generic category word.
        parts = [purpose] if purpose else []
        for _ in range(3):
            parts.append(" ".join(str(e) for e in entities if e))
        if domain and not _is_broad(domain):
            parts.append(domain)
        joined = " ".join(p for p in parts if p)
        return joined or _text_for(r)
    texts = [_EMBED_PREFIX + _cluster_text(r) for r in pool]
    vecs = await embeddings.embed(texts)
    if not vecs:
        return None
    groups = _kmeans(vecs, k if k is not None else default_k(len(pool)))

    clusters: list[dict] = []
    orphans_returned: list[dict] = []
    for idxs in groups:
        members = [pool[i] for i in idxs]
        if min_cluster_size > 1 and len(members) < min_cluster_size:
            # Singletons (or below the user's `min`) go back to the unassigned
            # pool — don't force-merge the long tail into one starving cluster.
            # Tag each as 'owned' so `_own_member_dicts` can re-ingest if the
            # caller asks for a second pass over the residual.
            for m in members:
                tag = dict(m)
                tag["source"] = "owned"
                orphans_returned.append(tag)
            continue
        # Coherence check — average member cosine to the cluster centroid
        # must clear the floor, otherwise drop the whole group to orphans.
        # Unit-normalised so dot product == cosine. Default 0.40 keeps
        # anything tighter than "barely related"; raise for stricter
        # semantic comparison.
        member_vecs = [_unit(vecs[i]) for i in idxs if vecs[i] is not None]
        if not member_vecs:
            for m in members:
                tag = dict(m); tag["source"] = "owned"
                orphans_returned.append(tag)
            continue
        dim = len(member_vecs[0])
        cen = [sum(v[d] for v in member_vecs) / len(member_vecs) for d in range(dim)]
        cen = _unit(cen)
        avg_cos = sum(_dot(v, cen) for v in member_vecs) / len(member_vecs)
        if avg_cos < coherence_floor:
            for m in members:
                tag = dict(m); tag["source"] = "owned"
                orphans_returned.append(tag)
            log.info("cluster dropped (coherence %.3f < %.2f, %d repos)",
                     avg_cos, coherence_floor, len(members))
            continue
        # Name the cluster from its distilled substance (domain + entities),
        # not the raw tech topics — the name should read like the activity it
        # serves, e.g. "tabletop role-playing", not "python" or "bot".
        named = []
        for m in members:
            rec = record_map.get(distill._key(m)) or {}
            nm = dict(m)
            subj = (rec.get("entities") or []) + (
                [rec["domain"]] if rec.get("domain") else [])
            nm["topics"] = subj or nm.get("topics") or []
            named.append(nm)
        s = suggest_theme(named)
        clusters.append({
            "members": [
                {"repo": m.get("repo") or m.get("name"),
                 "full_name": m.get("full_name"),
                 "source": m["source"],
                 "language": m.get("language", ""),
                 "stars": m.get("stars", 0),
                 "domain": (record_map.get(distill._key(m)) or {}).get("domain", ""),
                 "entities": (record_map.get(distill._key(m)) or {}).get("entities", []),
                 "purpose": (record_map.get(distill._key(m)) or {}).get("purpose", ""),
                 "aim": m.get("aim") or m.get("description") or ""}
                for m in members
            ],
            "suggested_name": s["name"],
            "suggested_description": s["description"],
            "size": len(members),
        })
    # Largest first; ties broken by name for determinism in tests.
    clusters.sort(key=lambda c: (-c["size"], c["suggested_name"]))
    return clusters, orphans_returned


# ── anchor-driven re-cluster ───────────────────────────────────────────────
async def _embed_member(r: dict) -> list[float] | None:
    """Embed one repo the same way build_clusters_mixed does (distilled domain
    + entities, with the nomic clustering prefix). Returns unit vector or None
    if embeddings are unavailable."""
    recs, _ = await distill.records([r], stop_on_error=False)
    rec = recs.get(distill._key(r)) or {}
    domain = rec.get("domain", "")
    entities = " ".join(rec.get("entities") or [])
    text = " ".join(p for p in (domain, entities) if p) or _text_for(r)
    vecs = await embeddings.embed([_EMBED_PREFIX + text])
    if not vecs or vecs[0] is None:
        return None
    return _unit(vecs[0])


async def _anchor_centroid(members: list[dict]) -> list[float] | None:
    """Mean of member vectors, re-normalised. None if no member embedded."""
    vecs: list[list[float]] = []
    for m in members:
        v = await _embed_member(m)
        if v is not None:
            vecs.append(v)
    if not vecs:
        return None
    dim = len(vecs[0])
    mean = [sum(v[d] for v in vecs) / len(vecs) for d in range(dim)]
    return _unit(mean)


async def snap_to_anchors(
    clusters: list[dict],
    anchors: dict[str, list[dict]],
    threshold: float = 0.7,
) -> list[dict]:
    """Snap each cluster to its nearest anchored hub, or leave it free.

    clusters : output of build_clusters_mixed (each has 'members' with the
               same shape distill.records keys on).
    anchors  : {hub_name: [repo_dict, ...]} — promoted hubs whose member set
               is considered decided. The dict can be empty (no-op).
    threshold: minimum cosine between a cluster's centroid and an anchor's
               centroid for the cluster to be absorbed into the anchor.

    Returns a NEW list of cluster dicts. Each cluster gains:
        anchored_to  : hub_name | None
        anchor_sim   : float  (cosine to the chosen anchor, or best candidate)

    Side effect: clusters that snap into an anchor are NOT removed — the caller
    decides whether to merge their members into the hub or just label them.
    Membership is preserved so the UI can show "12 members would join homelab"
    before the user commits.

    # ponytail: one pass, no re-clustering of anchors. Anchors are pinned; we
    # only compute their centroids once. Fine at portfolio scale.
    """
    if not anchors or not clusters:
        for c in clusters:
            c.setdefault("anchored_to", None)
            c.setdefault("anchor_sim", 0.0)
        return clusters

    # Compute centroids. dict order is insertion order in py3.7+, which is fine
    # for determinism — anchors are loaded from plan_store in stable order.
    cents: dict[str, list[float]] = {}
    for hub_name, members in anchors.items():
        c = await _anchor_centroid(members)
        if c is not None:
            cents[hub_name] = c

    if not cents:
        for c in clusters:
            c.setdefault("anchored_to", None)
            c.setdefault("anchor_sim", 0.0)
        return clusters

    hub_names = list(cents.keys())
    hub_vecs = [cents[h] for h in hub_names]

    for cluster in clusters:
        members = cluster.get("members", [])
        if not members:
            cluster["anchored_to"] = None
            cluster["anchor_sim"] = 0.0
            continue
        # Re-embed this cluster's members the same way; reuse cached vecs where
        # possible via embeddings.embed (it keys on sha256(text) per model).
        recs, _ = await distill.records(members, stop_on_error=False)
        texts = []
        for m in members:
            rec = recs.get(distill._key(m)) or {}
            domain = rec.get("domain", "")
            entities = " ".join(rec.get("entities") or [])
            text = " ".join(p for p in (domain, entities) if p) or _text_for(m)
            texts.append(_EMBED_PREFIX + text)
        vecs = await embeddings.embed(texts)
        pts = [_unit(v) for v in vecs if v is not None]
        if not pts:
            cluster["anchored_to"] = None
            cluster["anchor_sim"] = 0.0
            continue
        dim = len(pts[0])
        cen = [sum(p[d] for p in pts) / len(pts) for d in range(dim)]
        cen = _unit(cen)
        # Pick the best hub; record its sim either way.
        best_h, best_sim = None, -2.0
        for h, hv in zip(hub_names, hub_vecs):
            sim = _dot(cen, hv)
            if sim > best_sim:
                best_sim, best_h = sim, h
        cluster["anchor_sim"] = round(best_sim, 4)
        cluster["anchored_to"] = best_h if best_sim >= threshold else None
    return clusters
