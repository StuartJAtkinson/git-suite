"""
overlap.py — semantic overlap between hubs (the "venn") + boundary cases.

Every live repo is embedded and scored (cosine) against each hub's profile
(name + description + boundary). A repo whose top two hubs score close together
is a "boundary case" — it straddles those hubs. Aggregated across repos this
gives a hub x hub overlap matrix (how often each pair competes for the same
repos). Requires embeddings; with none configured the analysis is unavailable
(no hardcoded keyword taxonomy — hubs come from the scan).
"""
import logging

from fastapi import APIRouter

import plan_store
from routers.reconcile import reconcile
from services import embeddings

log = logging.getLogger(__name__)
router = APIRouter()

_SEM_GAP = 0.05       # semantic (cosine): top two within this => straddles
_SEM_MIN = 0.2        # semantic: runner-up cosine must be at least this


async def _semantic_analyse(repos, hubs, plan):
    """Embedding-based overlap. Returns (matrix, cases) or None if unavailable.

    A straddle needs two hubs to compare, so <2 hubs trivially yields no cases.
    """
    if not embeddings.has_embeddings() or len(hubs) < 2:
        return None
    hub_texts = [
        f"{h}. {plan['hubs'][h].get('description', '')}. {plan['hubs'][h].get('boundary', '')}"
        for h in hubs
    ]
    repo_texts = [
        f"{r['name']}. {r.get('aim', '')}. {' '.join(r.get('topics') or [])}" for r in repos
    ]
    hub_vecs = await embeddings.embed(hub_texts)
    repo_vecs = await embeddings.embed(repo_texts)
    if not hub_vecs or not repo_vecs:
        return None

    matrix = {a: {b: 0 for b in hubs} for a in hubs}
    cases = []
    for r, rv in zip(repos, repo_vecs):
        scored = sorted(
            ((hubs[i], embeddings.cosine(rv, hv)) for i, hv in enumerate(hub_vecs)),
            key=lambda kv: -kv[1],
        )
        (h1, s1), (h2, s2) = scored[0], scored[1]
        if s2 >= _SEM_MIN and (s1 - s2) <= _SEM_GAP:
            matrix[h1][h2] += 1
            matrix[h2][h1] += 1
            cases.append({
                "repo": r["name"], "verdict": r.get("verdict"), "assigned_hub": r.get("hub"),
                "top": [{"hub": h, "score": round(s, 3)} for h, s in scored[:3]],
                "gap": round(s1 - s2, 3),
            })
    cases.sort(key=lambda c: c["gap"])
    return matrix, cases


@router.get("/overlap/{session_id}")
async def overlap(session_id: str):
    recon = await reconcile(session_id)
    plan = plan_store.get_plan()
    hubs = list(plan.get("hubs", {}).keys())

    boundaries = {h: plan["hubs"][h].get("boundary", "") for h in hubs}
    result = await _semantic_analyse(recon["repos"], hubs, plan)
    if result is None:
        # No embeddings → no analysis (we never fall back to a hardcoded taxonomy).
        return {"hubs": hubs, "method": "unavailable",
                "matrix": {a: {b: 0 for b in hubs} for a in hubs},
                "cases": [], "boundaries": boundaries}
    matrix, cases = result
    return {"hubs": hubs, "method": "semantic", "matrix": matrix,
            "cases": cases, "boundaries": boundaries}
