"""
stars.py — starred repos as a first-class dedup input.

The product goal: organise owned repos AND stars into one framework so
functionality isn't duplicated. Two signals come out of this module:

  1. duplicates      — per owned repo, starred projects that already do the
                       same thing ("build vs adopt": archive yours, use theirs)
  2. hub_suggestions — per hub, starred projects that cover the hub's scope
                       (candidate OSS alternatives, today hand-curated in
                       HUB_ALTERNATIVES)

Semantic path embeds star/repo/hub texts through the embeddings failover
chain (vectors are DB-cached, so re-runs only embed new text). Falls back to
deterministic token-overlap scoring when no embedding provider is usable —
same degradation philosophy as cluster and overlap.
"""
from __future__ import annotations

import logging
import math
import re

import numpy as np

from services import embeddings

log = logging.getLogger(__name__)

# Cosine thresholds (nomic/text-embedding-3: related ~0.6-0.8).
SEM_DUP_MIN = 0.65     # owned repo vs star: high similarity = likely duplicate
SEM_HUB_MIN = 0.50     # hub profile vs star: hub texts are abstract, score lower
# Token-overlap thresholds (different scale: normalised set intersection).
KW_DUP_MIN = 0.35
KW_HUB_MIN = 0.25

TOP_MATCHES = 3        # starred matches kept per owned repo
TOP_SUGGESTIONS = 5    # starred suggestions kept per hub

_STOPWORDS = {"the", "and", "for", "with", "api", "app", "tool", "tools",
              "data", "repo", "test", "main", "core", "lib", "project",
              "based", "using", "your", "from", "that", "this"}


def repo_text(name: str, description: str, topics: list[str]) -> str:
    return f"{name}. {description or ''}. {' '.join(topics or [])}"


def _tokens(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower())
            if len(w) > 2 and w not in _STOPWORDS}


def _kw_score(a: set[str], b: set[str]) -> float:
    """Normalised token overlap — cosine on token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


def _star_payload(s: dict, score: float) -> dict:
    return {
        "full_name": s["full_name"],
        "description": s.get("description") or "",
        "language": s.get("language") or "",
        "stars": s.get("stars") or 0,
        "url": s.get("url") or "",
        "score": round(score, 3),
    }


def _normalise(vecs: list[list[float]]) -> np.ndarray:
    m = np.asarray(vecs, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


async def _semantic(owned: list[dict], stars: list[dict],
                    hubs: dict[str, dict]) -> tuple[list[dict], dict] | None:
    """Embedding-based dedup. Returns (duplicates, hub_suggestions) or None."""
    if not embeddings.has_embeddings():
        return None
    star_texts = [repo_text(s["name"], s.get("description"), s.get("topics")) for s in stars]
    owned_texts = [repo_text(r["name"], r.get("aim"), r.get("topics")) for r in owned]
    hub_names = list(hubs.keys())
    hub_texts = [
        f"{h}. {hubs[h].get('description', '')}. {hubs[h].get('boundary', '')}"
        for h in hub_names
    ]
    star_vecs = await embeddings.embed(star_texts)
    owned_vecs = await embeddings.embed(owned_texts)
    hub_vecs = await embeddings.embed(hub_texts) if hub_texts else []
    if not star_vecs or not owned_vecs:
        return None

    sm = _normalise(star_vecs)                      # (S, d)
    duplicates = []
    if owned:
        om = _normalise(owned_vecs)                 # (O, d)
        sim = om @ sm.T                             # (O, S) cosine matrix
        for i, r in enumerate(owned):
            idx = np.argsort(-sim[i])[:TOP_MATCHES]
            matches = [_star_payload(stars[j], float(sim[i][j]))
                       for j in idx if sim[i][j] >= SEM_DUP_MIN]
            if matches:
                duplicates.append({"repo": r["name"], "verdict": r.get("verdict"),
                                   "hub": r.get("hub"), "matches": matches})

    suggestions: dict[str, list[dict]] = {}
    if hub_texts and hub_vecs:
        hm = _normalise(hub_vecs)
        hsim = hm @ sm.T                            # (H, S)
        for i, h in enumerate(hub_names):
            idx = np.argsort(-hsim[i])[:TOP_SUGGESTIONS]
            picks = [_star_payload(stars[j], float(hsim[i][j]))
                     for j in idx if hsim[i][j] >= SEM_HUB_MIN]
            if picks:
                suggestions[h] = picks
    return duplicates, suggestions


def _keyword(owned: list[dict], stars: list[dict],
             hubs: dict[str, dict]) -> tuple[list[dict], dict]:
    """Deterministic token-overlap dedup — no provider needed."""
    star_toks = [_tokens(repo_text(s["name"], s.get("description"), s.get("topics")))
                 for s in stars]

    duplicates = []
    for r in owned:
        rt = _tokens(repo_text(r["name"], r.get("aim"), r.get("topics")))
        scored = sorted(((j, _kw_score(rt, st)) for j, st in enumerate(star_toks)),
                        key=lambda js: -js[1])[:TOP_MATCHES]
        matches = [_star_payload(stars[j], s) for j, s in scored if s >= KW_DUP_MIN]
        if matches:
            duplicates.append({"repo": r["name"], "verdict": r.get("verdict"),
                               "hub": r.get("hub"), "matches": matches})

    suggestions: dict[str, list[dict]] = {}
    for h, meta in hubs.items():
        ht = _tokens(f"{h}. {meta.get('description', '')}. {meta.get('boundary', '')}")
        scored = sorted(((j, _kw_score(ht, st)) for j, st in enumerate(star_toks)),
                        key=lambda js: -js[1])[:TOP_SUGGESTIONS]
        picks = [_star_payload(stars[j], s) for j, s in scored if s >= KW_HUB_MIN]
        if picks:
            suggestions[h] = picks
    return duplicates, suggestions


async def dedup(owned: list[dict], stars: list[dict],
                hubs: dict[str, dict]) -> dict:
    """Match owned repos + hubs against the starred snapshot.

    owned rows need: name, aim, topics (list), verdict, hub.
    star rows need: full_name, name, description, topics (list), language,
    stars, url.
    """
    if not stars:
        return {"method": None, "duplicates": [], "hub_suggestions": {}}

    method = "semantic"
    result = await _semantic(owned, stars, hubs)
    if result is None:
        method = "keyword"
        result = _keyword(owned, stars, hubs)
    duplicates, suggestions = result
    # Strongest duplication signals first.
    duplicates.sort(key=lambda d: -d["matches"][0]["score"])
    return {"method": method, "duplicates": duplicates, "hub_suggestions": suggestions}
