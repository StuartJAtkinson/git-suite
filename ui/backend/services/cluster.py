"""
cluster.py — assisted group formation.

Embeds the unassigned repos and groups them by semantic similarity
(union-find over a cosine threshold), then suggests a theme per cluster. The
user promotes a member to be the hub or names a new one (with a description
that becomes the hub's LLM-alignment boundary).

No heavy ML deps: clustering is connected-components over a cosine graph.
"""
from __future__ import annotations

import json
import logging
from collections import Counter

from services import embeddings

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.6   # nomic-embed-text: related ~0.6-0.8, unrelated ~0.3-0.5

_STOPWORDS = {"the", "and", "for", "with", "api", "app", "tool", "tools",
              "data", "repo", "test", "main", "core", "lib", "project"}


def _union_find(vectors: list[list[float]], threshold: float) -> list[list[int]]:
    """Connected components: edge i-j if cosine >= threshold."""
    n = len(vectors)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if embeddings.cosine(vectors[i], vectors[j]) >= threshold:
                parent[find(i)] = find(j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
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
    threshold: float = DEFAULT_THRESHOLD,
) -> list[dict] | None:
    """Cluster owned + forks + stars in one embedding space.

    Returns a list of cluster dicts:
        {
          "members": [{"repo": ..., "source": "owned"|"fork"|"star", ...}, ...],
          "suggested_name": ...,
          "suggested_description": ...,
        }

    Returns None if embeddings are unavailable (caller can show a clear
    "configure embeddings" message). Cluster ordering is largest-first.
    Each member is tagged with its source so the UI can render the
    [O]/[F]/[S] prefix symbol.
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

    texts = [_text_for(r) for r in pool]
    vecs = await embeddings.embed(texts)
    if not vecs:
        return None
    groups = _union_find(vecs, threshold)

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
