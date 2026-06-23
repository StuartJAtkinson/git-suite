"""
cluster.py — assisted group formation.

Embeds the unassigned repos and groups them into a target number of clusters
(spherical k-means over the cached vectors), then suggests a theme per cluster.
The user promotes a member to be the hub or names a new one (with a description
that becomes the hub's LLM-alignment boundary).

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
    """A sane target cluster count for n repos when the user hasn't picked one."""
    return max(2, round(math.sqrt(n / 2))) if n > 3 else max(1, n)


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
) -> list[dict] | None:
    """Cluster owned + forks + stars in one embedding space.

    Each repo is first distilled to a one-line semantic domain (LLM, cached),
    then that distillation is embedded (with the nomic `clustering:` prefix) and
    partitioned into `k` groups by spherical k-means. `k` defaults to ~√(n/2).

    Returns a list of cluster dicts:
        {
          "members": [{"repo": ..., "source": "owned"|"fork"|"star", ...}, ...],
          "suggested_name": ...,
          "suggested_description": ...,
        }

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
    # embed domain + entities (the actual domain signal — not "what the repo
    # does", which is in `purpose` and is what humans re-read on hover).
    # Falls back to raw text per-repo if the LLM is unavailable.
    record_map, _ = await distill.records(pool, stop_on_error=False)
    def _cluster_text(r: dict) -> str:
        rec = record_map.get(distill._key(r)) or {}
        domain = rec.get("domain", "")
        entities = " ".join(rec.get("entities") or [])
        joined = " ".join(p for p in (domain, entities) if p)
        return joined or _text_for(r)
    texts = [_EMBED_PREFIX + _cluster_text(r) for r in pool]
    vecs = await embeddings.embed(texts)
    if not vecs:
        return None
    groups = _kmeans(vecs, k if k is not None else default_k(len(pool)))

    clusters: list[dict] = []
    for idxs in groups:
        members = [pool[i] for i in idxs]
        s = suggest_theme(members)
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
    return clusters
