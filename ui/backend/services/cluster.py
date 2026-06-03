"""
cluster.py — assisted group formation.

Embeds the unassigned repos and groups them by semantic similarity
(union-find over a cosine threshold), then suggests a theme per cluster. The
user promotes a member to be the hub or names a new one (with a description
that becomes the hub's LLM-alignment boundary).

No heavy ML deps: clustering is connected-components over a cosine graph.
"""
from __future__ import annotations

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


async def build_clusters(repos: list[dict], threshold: float = DEFAULT_THRESHOLD):
    """Return [ [member dict, ...], ... ] sorted largest first, or None if
    embeddings are unavailable."""
    if not embeddings.has_embeddings() or not repos:
        return None
    texts = [
        f"{r['name']}. {r.get('aim', '')}. {' '.join(r.get('topics') or [])}" for r in repos
    ]
    vecs = await embeddings.embed(texts)
    if not vecs:
        return None
    groups = _union_find(vecs, threshold)
    clusters = [[repos[i] for i in idxs] for idxs in groups]
    clusters.sort(key=len, reverse=True)
    return clusters
