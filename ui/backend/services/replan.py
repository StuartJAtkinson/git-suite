"""
replan.py — the re-planning engine (the loop that replaces one-shot scoping).

Each *pass* turns current reality (a reconcile result) into a batch of
*proposals* — reviewable plan changes. It is a two-phase state machine:

  incremental phase  (undecided > 0):  propose verdicts for orphans + prune
                                       ghosts. Never touches settled placements.
  replan phase       (undecided == 0): also propose structural changes
                                       (hub splits, new hubs) — advisory only.

Determination is hybrid:
  * embedding similarity against the *actual plan hubs* places clear matches
    (source="embedding") — no hardcoded taxonomy; hubs come from the scan
  * the configured LLM handles ambiguous cases (source="llm")
  * with neither configured it degrades to "keep — please review".

Proposals are advisory until a human accepts them (see routers/replan.py).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_SPLIT_THRESHOLD = 16   # hub absorb_total at/above which we flag a split


# --- LLM determination -----------------------------------------------------

def _llm_available() -> bool:
    from services import llm
    return llm.has_provider()


async def _llm_proposal(repo: dict, hubs: list[dict]) -> dict | None:
    """Ask the LLM for a verdict on an ambiguous repo. None on any failure.

    Goes through the failover chain (services/llm), so if the primary provider
    is out of credits it transparently uses the next configured one.
    """
    from services import llm
    if not llm.has_provider():
        return None
    try:
        hub_lines = "\n".join(
            f"- {h['name']}: {h['description']}"
            + (f"\n    boundary: {h['boundary']}" if h.get('boundary') else "")
            for h in hubs
        )
        prompt = f"""You assign a GitHub repo to a portfolio plan. Choose exactly one verdict.

Repo:
  name: {repo['name']}
  language: {repo.get('language') or 'unknown'}
  description: {repo.get('aim') or '(none)'}

Hubs (for verdict "absorb", pick the single best hub name):
{hub_lines}

Verdicts:
  absorb  — fold this repo into the best-fitting hub above
  archive — retire it (superseded, abandoned, or out of scope)
  keep    — leave standalone (a working tool, library, or reference fork)

Return ONLY this JSON, no markdown:
{{"verdict":"absorb|archive|keep","hub":"<hub name or null>","confidence":0.0,"rationale":"one short sentence"}}"""
        data = await llm.complete_json(prompt, max_tokens=300)
        verdict = data.get("verdict", "keep")
        hub = data.get("hub") if verdict == "absorb" else None
        return {
            "kind": "verdict",
            "target": repo["name"],
            "proposed": {"verdict": verdict, "hub": hub},
            "source": "llm",
            "confidence": round(float(data.get("confidence", 0.6)), 2),
            "rationale": data.get("rationale", "")[:300],
        }
    except Exception as exc:
        log.warning("LLM proposal failed for %s: %s", repo["name"], exc)
        return None


# --- pass generation -------------------------------------------------------

async def _embed_rank(orphans: list[dict], hubs: list[dict]) -> dict[str, list[tuple[str, float]]]:
    """Per-orphan hub ranking by embedding similarity. {} if embeddings off."""
    from services import embeddings
    if not embeddings.has_embeddings() or not orphans:
        return {}
    hub_texts = [f"{h['name']}. {h.get('description', '')}. {h.get('boundary', '')}" for h in hubs]
    repo_texts = [f"{o['name']}. {o.get('aim', '')}. {' '.join(o.get('topics') or [])}" for o in orphans]
    hv = await embeddings.embed(hub_texts)
    rv = await embeddings.embed(repo_texts)
    if not hv or not rv:
        return {}
    out: dict[str, list[tuple[str, float]]] = {}
    for o, vec in zip(orphans, rv):
        out[o["name"]] = sorted(
            ((hubs[i]["name"], embeddings.cosine(vec, h)) for i, h in enumerate(hv)),
            key=lambda kv: -kv[1],
        )
    return out


async def generate_proposals(recon: dict) -> tuple[str, list[dict]]:
    """Turn a reconcile result into (phase, proposals).

    Phase follows Stuart's rule: incremental until nothing is undecided, then
    the structural replan options unlock.
    """
    undecided = recon["stats"]["undecided"]
    phase = "incremental" if undecided > 0 else "replan"
    hubs = recon["hubs"]
    proposals: list[dict] = []

    hub_names = {h["name"] for h in hubs}
    emb_rank = await _embed_rank(recon["orphans"], hubs)

    # --- always: fill in orphans (the incremental work) ---
    for orphan in recon["orphans"]:
        # A hub repo is never absorbed into a hub — it IS one. Keep it.
        if orphan["name"] in hub_names:
            proposals.append({
                "kind": "verdict", "target": orphan["name"],
                "proposed": {"verdict": "keep", "hub": None},
                "source": "rule", "confidence": 0.95,
                "rationale": "this repo is itself a hub — keep standalone",
            })
            continue
        # Low-signal stub -> propose archiving it (unless it's function-distinct,
        # which the human decides on review).
        if orphan.get("stub_reason"):
            proposals.append({
                "kind": "verdict", "target": orphan["name"],
                "proposed": {"verdict": "archive", "hub": None},
                "source": "rule", "confidence": 0.7,
                "rationale": orphan["stub_reason"] + " — archive unless function-distinct",
            })
            continue
        # Semantic match (embeddings) against the actual plan hubs.
        er = emb_rank.get(orphan["name"]) or []
        # `next` margin guards against a tie; with a single hub there's no next,
        # so the margin is the score itself (gap from nothing).
        nxt = er[1][1] if len(er) > 1 else 0.0
        if er and er[0][1] >= 0.28 and (er[0][1] - nxt) >= 0.04:
            next_note = f", next {er[1][0]} {er[1][1]:.2f}" if len(er) > 1 else ""
            proposals.append({
                "kind": "verdict", "target": orphan["name"],
                "proposed": {"verdict": "absorb", "hub": er[0][0]},
                "source": "embedding", "confidence": round(min(0.9, 0.5 + er[0][1]), 2),
                "rationale": f"semantic match -> {er[0][0]} (cos {er[0][1]:.2f}{next_note})",
            })
            continue
        llm = await _llm_proposal(orphan, hubs)
        if llm:
            proposals.append(llm)
        else:                           # no embedding/LLM signal
            proposals.append({
                "kind": "verdict", "target": orphan["name"],
                "proposed": {"verdict": "keep", "hub": None},
                "source": "rule", "confidence": 0.1,
                "rationale": "no embedding/LLM signal — defaulting to keep, please review",
            })

    # --- always: prune ghosts that were once live but are now deleted ---
    # External (never-owned) absorb targets are never live by design — skip them.
    for ghost in recon["ghosts"]:
        if not ghost.get("was_live"):
            continue
        proposals.append({
            "kind": "ghost-prune", "target": ghost["name"],
            "proposed": {"verdict": "orphan", "hub": ghost.get("hub")},
            "source": "rule", "confidence": 0.8,
            "rationale": f"planned for {ghost.get('hub') or 'archive'} but not live — remove from plan",
        })

    # --- replan phase only: structural advisories ---
    if phase == "replan":
        for h in hubs:
            if h["absorb_total"] >= _SPLIT_THRESHOLD:
                proposals.append({
                    "kind": "split", "target": h["name"],
                    "proposed": {"absorb_total": h["absorb_total"]},
                    "source": "rule", "confidence": 0.5,
                    "rationale": f"{h['name']} absorbs {h['absorb_total']} repos — consider splitting (advisory)",
                })

    return phase, proposals
