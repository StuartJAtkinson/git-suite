"""
overlap.py — semantic overlap between hubs (the "venn") + boundary cases.

Reuses the replan keyword/topic scorer: every live repo is scored against each
hub's profile. A repo whose top two hubs score close together is a "boundary
case" — it straddles those hubs. Aggregated across repos this gives a hub x hub
overlap matrix (how often each pair competes for the same repos).
"""
import logging
from collections import defaultdict

from fastapi import APIRouter

import plan_store
from routers.reconcile import reconcile
from services.replan import _score_hub

log = logging.getLogger(__name__)
router = APIRouter()

_CLOSE_GAP = 0.2      # runner-up within this of the top => straddles
_MIN_SCORE = 0.4      # runner-up must be at least this to count


def _analyse(repos: list[dict], hubs: list[str]) -> tuple[dict, list[dict]]:
    matrix: dict[str, dict[str, int]] = {a: {b: 0 for b in hubs} for a in hubs}
    cases: list[dict] = []
    for r in repos:
        text = f"{r['name']} {r.get('aim', '')} {' '.join(r.get('topics') or [])}"
        ranked = _score_hub(text, r.get("language", ""))
        if len(ranked) < 2:
            continue
        (h1, s1), (h2, s2) = ranked[0], ranked[1]
        if s2 >= _MIN_SCORE and (s1 - s2) <= _CLOSE_GAP:
            if h1 in matrix and h2 in matrix[h1]:
                matrix[h1][h2] += 1
                matrix[h2][h1] += 1
            cases.append({
                "repo": r["name"],
                "verdict": r.get("verdict"),
                "assigned_hub": r.get("hub"),
                "top": [{"hub": h, "score": round(s, 2)} for h, s in ranked[:3]],
                "gap": round(s1 - s2, 2),
            })
    cases.sort(key=lambda c: c["gap"])   # tightest straddles first
    return matrix, cases


@router.get("/overlap/{session_id}")
async def overlap(session_id: str):
    recon = await reconcile(session_id)
    plan = plan_store.get_plan()
    hubs = list(plan.get("hubs", {}).keys())
    matrix, cases = _analyse(recon["repos"], hubs)
    return {
        "hubs": hubs,
        "matrix": matrix,
        "cases": cases,
        "boundaries": {h: plan["hubs"][h].get("boundary", "") for h in hubs},
    }
