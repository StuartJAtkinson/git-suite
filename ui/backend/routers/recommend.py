"""
recommend.py — Step 6: per-orphan-repo best-hub feature absorption.

  GET /api/recommend/{session_id}/{repo}   cached best-hub-for-this-repo

For each repo without a verdict yet, ask the LLM which hub's feature set
absorbs a single concrete feature from it. Persist the answer in
`feature_recommendations` (session_id, source_repo) and serve from cache on
subsequent reads.

Signal precedence (design rule 3, walkthrough 2026-08-17):
  - User-authored Notes (from Scan page) override the LLM-distilled record.
  - If neither exists, no recommendation is produced (returns null).

The Triage page prefetches in parallel on load. The one-click Absorb button
calls the existing `api.setVerdict(name, 'absorb', target_hub)` — no new
verdict token, no plan.json schema change.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from services import llm

log = logging.getLogger(__name__)
router = APIRouter()


RECOMMEND_SYSTEM = (
    "You recommend ONE existing hub whose feature set most naturally absorbs "
    "a single concrete feature from the repo described below. 'Absorb' means "
    "the user would lift ONE small, checkable feature (e.g. 'OAuth2 login', "
    "'CSV export', 'rate-limited API client') into the hub — not the whole "
    "repo, not a restatement of purpose, not the technology. Pick from the "
    "candidate hubs exactly. Confidence is how clearly the one feature fits "
    "that hub's stated boundary. Return JSON only."
)


# --- helpers ---------------------------------------------------------------

async def _distilled_record(repo: str) -> dict:
    """purpose/entities/domain for one repo from the distill cache, or empty
    strings/list if it's never been distilled. Mirrors the helper in
    routers/order.py — kept private+local rather than cross-imported."""
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT record FROM repo_domain WHERE repo = ?", (repo,))
    if not rows or not rows[0]["record"]:
        return {"purpose": "", "entities": [], "domain": ""}
    try:
        return json.loads(rows[0]["record"])
    except Exception:
        return {"purpose": "", "entities": [], "domain": ""}


async def _note_for(session_id: str, repo: str) -> str:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT note FROM repo_notes WHERE session_id = ? AND repo = ?",
            (session_id, repo),
        )
    return (rows[0]["note"] or "") if rows else ""


async def _load_cached(session_id: str, repo: str) -> dict | None:
    async for db in get_db():
        rows = await db.execute_fetchall(
            """SELECT target_hub, feature, confidence, rationale, signal
               FROM feature_recommendations
               WHERE session_id = ? AND source_repo = ?""",
            (session_id, repo),
        )
    if not rows:
        return None
    r = rows[0]
    return {
        "source_repo": repo,
        "recommendation": {
            "target_hub": r["target_hub"],
            "feature": r["feature"],
            "confidence": float(r["confidence"]),
            "rationale": r["rationale"] or "",
            "signal": r["signal"],
        },
    }


async def _compute(session_id: str, repo: str) -> dict | None:
    """One LLM call. Returns the recommendation dict or None on no-signal /
    hallucination. Does NOT persist — the caller does."""
    note = await _note_for(session_id, repo)
    distill = await _distilled_record(repo)

    if not note and not distill.get("purpose"):
        return None

    plan = plan_store.get_plan()
    hubs = list(plan.get("hubs", {}).keys())
    if not hubs:
        return None

    hub_blurbs = "\n".join(
        f"- {h}: description={plan['hubs'][h].get('description', '') or '(none)'}, "
        f"boundary={plan['hubs'][h].get('boundary', '') or '(none)'}"
        for h in hubs
    )

    if note:
        signal = "notes"
        about = f"USER NOTE: {note}"
    else:
        signal = "distill"
        about = (
            f"DISTILLED: purpose={distill.get('purpose', '')}, "
            f"domain={distill.get('domain', '')}, "
            f"entities={', '.join(distill.get('entities') or [])}"
        )

    prompt = f"""Candidate hubs:
{hub_blurbs}

Repo: {repo}
{about}

Pick the ONE hub whose feature set most naturally absorbs a single feature
from this repo. Reply with JSON only:
{{"target_hub": "<hub>", "feature": "<2-6 word concrete feature>",
  "confidence": <0.0-1.0>, "rationale": "<one short sentence>"}}
"""
    try:
        out = await llm.complete_json(prompt, system=RECOMMEND_SYSTEM, max_tokens=512)
    except Exception as exc:
        log.warning("recommend %s: LLM failed: %s", repo, str(exc)[:160])
        return None

    target = (out.get("target_hub") or "").strip()
    if target not in hubs:
        return None    # hallucination guard — don't persist garbage

    try:
        confidence = float(out.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "source_repo": repo,
        "recommendation": {
            "target_hub": target,
            "feature": str(out.get("feature", "")).strip()[:80],
            "confidence": confidence,
            "rationale": str(out.get("rationale", "")).strip()[:240],
            "signal": signal,
        },
    }


async def _persist(session_id: str, rec: dict | None) -> None:
    """Upsert one row. None → DELETE the cache (so the row doesn't lie
    forever about a now-empty signal)."""
    async for db in get_db():
        if not rec or not rec.get("recommendation"):
            await db.execute(
                "DELETE FROM feature_recommendations "
                "WHERE session_id = ? AND source_repo = ?",
                (session_id, rec["source_repo"] if rec else ""),
            )
            await db.commit()
            return
        r = rec["recommendation"]
        await db.execute(
            """INSERT INTO feature_recommendations
                 (session_id, source_repo, target_hub, feature,
                  confidence, rationale, signal, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(session_id, source_repo) DO UPDATE SET
                 target_hub = excluded.target_hub,
                 feature = excluded.feature,
                 confidence = excluded.confidence,
                 rationale = excluded.rationale,
                 signal = excluded.signal,
                 computed_at = datetime('now')""",
            (session_id, rec["source_repo"], r["target_hub"], r["feature"],
             r["confidence"], r["rationale"], r["signal"]),
        )
        await db.commit()


# --- endpoint --------------------------------------------------------------

@router.get("/recommend/{session_id}/{repo}")
async def get_recommendation(session_id: str, repo: str):
    """Cached best-hub-for-this-repo. Computes on first call."""
    await require_session(session_id)
    cached = await _load_cached(session_id, repo)
    if cached is not None:
        return cached

    rec = await _compute(session_id, repo)
    await _persist(session_id, rec) if rec else None
    if rec is None:
        return {"source_repo": repo, "recommendation": None}
    return rec


# Pydantic models reserved for future POST endpoints (e.g. invalidate). Kept
# here so the router module is the canonical home for any recommendation I/O.
class _InvalidateRequest(BaseModel):    # ponytail: reserved, not wired yet
    repo: str