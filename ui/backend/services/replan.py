"""
replan.py — the re-planning engine (the loop that replaces one-shot scoping).

Each *pass* turns current reality (a reconcile result) into a batch of
*proposals* — reviewable plan changes. It is a two-phase state machine:

  incremental phase  (undecided > 0):  propose verdicts for orphans + prune
                                       ghosts. Never touches settled placements.
  replan phase       (undecided == 0): also propose structural changes
                                       (hub splits, new hubs) — advisory only.

Determination is hybrid:
  * deterministic keyword/language rules place obvious orphans (source="rule")
  * the configured LLM handles low-confidence cases (source="llm")
  * with no API key it degrades gracefully to rules-only.

Proposals are advisory until a human accepts them (see routers/replan.py).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# --- rule signals ----------------------------------------------------------
# Keyword → hub. Deliberately broad; scoring picks the strongest hub.
HUB_KEYWORDS: dict[str, list[str]] = {
    "personal-ai-os": ["ai", "llm", "rag", "agent", "chat", "memory", "gpt",
                       "embedding", "prompt", "email", "knowledge", "assistant"],
    "ontology-align": ["ontology", "ontolog", "rdf", "sparql", "semantic",
                       "schema", "owl", "skos", "taxonomy", "graph", "knowledge graph"],
    "homelab-core":   ["docker", "homelab", "infra", "deploy", "secret", "traefik",
                       "server", "self-host", "selfhost", "kubernetes", "proxmox",
                       "vault", "orchestrat", "compose", "gateway", "windows", "linux"],
    "work-hub":       ["jira", "ticket", "crm", "zoho", "task", "project",
                       "workflow", "productivity", "kanban", "issue", "sage"],
    "media-hub":      ["video", "photo", "image", "comic", "manga", "anime",
                       "archive", "social", "youtube", "twitter", "media", "exif",
                       "restore", "clip", "edit", "linkedin", "simkl", "tag"],
    "map-suite":      ["map", "osm", "gis", "geo", "tile", "spatial", "terrain",
                       "3d", "indoor", "cesium", "leaflet", "world", "planet"],
    "game-hub":       ["ffxiv", "pokemon", "pokedex", "zelda", "botw", "game",
                       "dnd", "ttrpg", "foundry", "dungeon", "rpg", "diablo",
                       "guild wars", "dalamud", "heraldry"],
    "code-suite":     ["code", "repo", "git", "search", "cheatsheet", "parser",
                       "scrape", "scraper", "dom", "vscode", "lint", "sql",
                       "page", "clicker", "automation"],
}

# Weak language → hub hints (only break ties / add small weight).
LANG_HINTS: dict[str, str] = {
    "C#": "game-hub",
    "Jupyter Notebook": "personal-ai-os",
    "TypeScript": "media-hub",
}

_RULE_THRESHOLD = 0.5   # rule confidence at/above which we trust the rule
_SPLIT_THRESHOLD = 16   # hub absorb_total at/above which we flag a split


def _score_hub(text: str, language: str) -> list[tuple[str, float]]:
    """Score each hub against a repo's text. Returns [(hub, confidence)] desc."""
    text = text.lower()
    scores: dict[str, float] = {}
    for hub, words in HUB_KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits:
            # 1 hit → 0.45, 2 → 0.65, 3+ → caps near 0.9
            scores[hub] = min(0.9, 0.25 + 0.2 * hits)
    hinted = LANG_HINTS.get(language)
    if hinted:
        scores[hinted] = min(0.92, scores.get(hinted, 0.0) + 0.1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def _rule_proposal(repo: dict) -> dict | None:
    """Best-effort rule verdict for one orphan. None if no signal at all."""
    topics = " ".join(repo.get("topics") or [])
    text = f"{repo['name']} {repo.get('aim', '')} {topics}"
    ranked = _score_hub(text, repo.get("language", ""))
    if not ranked:
        return None
    hub, conf = ranked[0]
    runner = f"; next: {ranked[1][0]} ({ranked[1][1]:.2f})" if len(ranked) > 1 else ""
    return {
        "kind": "verdict",
        "target": repo["name"],
        "proposed": {"verdict": "absorb", "hub": hub},
        "source": "rule",
        "confidence": round(conf, 2),
        "rationale": f"keyword/language match → {hub} ({conf:.2f}){runner}",
    }


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
            f"- {h['name']} (L{h['layer']}): {h['description']}"
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
        # Semantic match (embeddings) takes precedence over keyword rules when
        # there's a clear winner.
        er = emb_rank.get(orphan["name"])
        if er and er[0][1] >= 0.28 and (er[0][1] - er[1][1]) >= 0.04:
            proposals.append({
                "kind": "verdict", "target": orphan["name"],
                "proposed": {"verdict": "absorb", "hub": er[0][0]},
                "source": "embedding", "confidence": round(min(0.9, 0.5 + er[0][1]), 2),
                "rationale": f"semantic match -> {er[0][0]} (cos {er[0][1]:.2f}, next {er[1][0]} {er[1][1]:.2f})",
            })
            continue
        rule = _rule_proposal(orphan)
        if rule and rule["confidence"] >= _RULE_THRESHOLD:
            proposals.append(rule)
            continue
        llm = await _llm_proposal(orphan, hubs)
        if llm:
            proposals.append(llm)
        elif rule:                      # low-confidence rule, no LLM → still surface
            rule["rationale"] = "low-confidence " + rule["rationale"]
            proposals.append(rule)
        else:                           # no signal at all
            proposals.append({
                "kind": "verdict", "target": orphan["name"],
                "proposed": {"verdict": "keep", "hub": None},
                "source": "rule", "confidence": 0.1,
                "rationale": "no keyword/LLM signal — defaulting to keep, please review",
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
        covered = {h["layer"] for h in hubs}
        for layer in recon["layers"]:
            if layer["num"] not in covered and not layer["hubs"]:
                proposals.append({
                    "kind": "new-hub", "target": f"L{layer['num']} {layer['name']}",
                    "proposed": {"layer": layer["num"]},
                    "source": "rule", "confidence": 0.3,
                    "rationale": f"layer {layer['num']} ({layer['name']}) has no hub — create one? (advisory)",
                })

    return phase, proposals
