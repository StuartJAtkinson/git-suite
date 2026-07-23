"""
themes_bundle.py — single-shot themes bundler.

Produces ONE structured JSON document the LLM can ingest in a single call:
every repo's scan metadata + entities/domain/purpose + the FULL readme text.

Token-budget aware:
  - target 70% of the model's context window (default MiniMax-M3: 1M → 700k)
  - if the raw bundle exceeds it, find the top-25%-largest READMEs by char
    count and LLM-summarise them
  - re-estimate; if still over, summarise the next-largest residual cohort
  - cap on iterations so a pathological input can't loop forever

Persists the bundle (and a meta block: token estimate, which repos were
summarised, when) to ~/.git-suite/themes-bundle.json so the user can audit
exactly what hit the model.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from routers.auth import require_session
from services import distill, github, llm
from llm_providers import context_window_for

log = logging.getLogger(__name__)


# Conservative 4-chars-per-token heuristic: Tiktoken averages closer to ~3.5
# for English + markdown, but 4 leaves headroom. The LLM provider's own
# tokenizer would be exact; we estimate because we need an answer before
# making the LLM call that depends on it.
_CHARS_PER_TOKEN = 4.0

# Default budget: 70% of the model's context window. Auto-picked per call
# from the active LLM chain via llm_providers.context_window_for. Env var
# THEMES_CTX_TOKENS overrides if you really want to force a number.
DEFAULT_BUDGET_FRACTION = 0.70


def _active_window() -> int:
    """Read the configured chain, pick the first live entry's context window."""
    env = os.environ.get("THEMES_CTX_TOKENS")
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    try:
        chain = llm.build_chain()
        if chain:
            provider, _key, model = chain[0]
            return context_window_for(model, provider)
    except Exception:
        pass
    return int(os.environ.get("THEMES_CTX_TOKENS", "200000"))


# ── token estimator ─────────────────────────────────────────────────────────
def est_tokens(s: str) -> int:
    """Rough token count: ~4 chars/token for English+markdown."""
    if not s:
        return 0
    return max(1, int(len(s) / _CHARS_PER_TOKEN))


def est_bundle_tokens(bundle: list[dict]) -> int:
    """Sum the per-repo block plus a small fixed overhead for the wrapping
    JSON keys + the prompt/system text on either side of it."""
    overhead = est_tokens("portfolio bundle: each entry has the schema:")
    n = overhead
    for r in bundle:
        # Cost = everything we'd serialise into the prompt for this repo.
        block = json.dumps(r, ensure_ascii=False)
        n += est_tokens(block) + 1         # +1 for the newline separator
    return n


# ── README fetch (extended from github.get_readme, no truncation) ─────────
async def _fetch_full_readme(token: str, owner: str, repo: str,
                              max_chars: int = 200_000) -> str | None:
    """Fetch the *full* readme (not the 2000-char excerpt github.get_readme
    returns). Hard cap at max_chars so a 12MB auto-generated README can't
    stall the bundle for minutes; in practice anything >200k is a sign the
    LLM summarise pass should nuke it anyway."""
    import base64
    import httpx
    GH_API = "https://api.github.com"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GH_API}/repos/{owner}/{repo}/readme",
                              headers=headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        try:
            text = base64.b64decode(r.json()["content"]).decode("utf-8",
                                                                 errors="replace")
        except Exception:
            return None
    return text[:max_chars]


# ── build the raw bundle: scan meta + distilled + full readme ───────────────
async def build_raw_bundle(session_id: str) -> list[dict]:
    """One dict per repo, every signal we have on it. None of the fields are
    optional — empty strings are fine, missing keys break the prompt."""
    sess = await require_session(session_id)
    token = sess["github_token"]

    # Reuse reconcile so we get the same repo set the cluster page uses.
    from routers.reconcile import reconcile
    recon = await reconcile(session_id)
    repos = recon.get("repos", [])

    # Project to the shape distill expects + parse owner/name out of the URL.
    pool = []
    for r in repos:
        url = (r.get("url") or "").rstrip("/")
        parts = url.split("/")[-2:]
        full_name = f"{parts[0]}/{parts[1]}" if len(parts) == 2 and parts[0] and parts[1] \
                    else r["name"]
        pool.append({
            "name": r["name"],
            "full_name": full_name,
            "aim": r.get("aim") or "",
            "topics": r.get("topics") or [],
            "url": r.get("url") or "",
            "language": r.get("language") or "",
            "stars": r.get("stars") or 0,
        })

    records, stop_reason = await distill.records(pool, stop_on_error=False)

    async def one_readme(p: dict) -> tuple[str, str | None]:
        fn = p.get("full_name") or p.get("name") or ""
        if "/" not in fn:
            return fn, None
        owner, repo = fn.split("/", 1)
        try:
            text = await _fetch_full_readme(token, owner, repo)
        except Exception as exc:
            log.warning("readme fetch %s failed: %s", fn, str(exc)[:120])
            return fn, None
        return fn, text

    sem = asyncio.Semaphore(8)
    async def bounded(p):
        async with sem:
            return await one_readme(p)

    fetched = dict(await asyncio.gather(*[bounded(p) for p in pool]))

    bundle: list[dict] = []
    for p in pool:
        fn = p.get("full_name") or p.get("name") or ""
        rec = records.get(fn) or records.get(p.get("name") or "") \
              or {"purpose": "", "entities": [], "domain": ""}
        readme = fetched.get(fn) or ""
        bundle.append({
            "name": p.get("name") or "",
            "full_name": fn,
            "source": "owned",          # bundler currently covers owned; threads/forks coming
            "language": p.get("language") or "",
            "stars": p.get("stars") or 0,
            "description": (p.get("aim") or "").strip(),
            "url": p.get("url") or "",
            "topics": p.get("topics") or [],
            "purpose": rec.get("purpose", ""),
            "entities": rec.get("entities", []),
            "domain": rec.get("domain", ""),
            "readme": readme,
        })

    if stop_reason:
        log.warning("themes_bundle distill stop_reason: %s", stop_reason)
    return bundle


# ── size cohort + summarise ─────────────────────────────────────────────────
def _cohort_top_pct(bundle: list[dict], pct: float) -> list[int]:
    """Indices into bundle for the top `pct`% by readme char count. Ties broken
    deterministically by name."""
    sizes = [(len(b.get("readme") or ""), b.get("name") or "", i)
             for i, b in enumerate(bundle)]
    sizes.sort(reverse=True)               # big first
    cutoff = max(1, int(len(sizes) * pct))
    return sorted([i for _, _, i in sizes[:cutoff]])


_SUMM_SYS = (
    "You compress a repository's README into a tight semantic fingerprint "
    "for portfolio-level clustering. Preserve all concrete entities "
    "(library names, protocol names, product names, real-world nouns) and "
    "the user-facing purpose. Drop installation steps, screenshots, badge "
    "blocks, contributor lists, license prose. Output STRICT JSON with "
    "keys: purpose (one sentence ≤25 words), entities (3-6 concrete "
    "nouns), domain (≤3 words naming the activity served). No prose, no "
    "fences, just the JSON object."
)


async def _summarise_one(name: str, readme: str) -> dict:
    """One LLM call to compress a large README into the distilled schema.
    Falls back to a deterministic heuristic if the LLM chain is dead."""
    try:
        raw = await llm.complete(
            f"REPO: {name}\n\nREADME:\n{readme[:30000]}",
            system=_SUMM_SYS, max_tokens=400,
        )
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        blob = m.group(0) if m else raw
        d = json.loads(blob)
        return {
            "purpose": str(d.get("purpose", "")).strip()[:400],
            "entities": [str(x).strip() for x in (d.get("entities") or [])][:6],
            "domain": str(d.get("domain", "")).strip()[:60],
        }
    except Exception as exc:
        # Heuristic fallback: keep the first ~25 lines / 1500 chars of the
        # README — clustering falls back on text embedding if needed.
        log.warning("themes_bundle summarise %s fell back: %s", name,
                    str(exc)[:120])
        snippet = readme[:1500]
        return {
            "purpose": snippet.splitlines()[0][:200] if snippet else "",
            "entities": [],
            "domain": "",
            "_heuristic": True,
        }


async def _summarise_cohort(cohort: list[dict],
                             concurrency: int = 6) -> list[dict]:
    """Returns [{idx, summary_dict}] for each repo in the cohort."""
    sem = asyncio.Semaphore(concurrency)

    async def one(idx: int, b: dict) -> tuple[int, dict]:
        async with sem:
            s = await _summarise_one(b.get("name") or b.get("full_name") or "",
                                     b.get("readme") or "")
            return idx, s

    return await asyncio.gather(*[one(i, c) for i, c in enumerate(cohort)])


# ── iterate until bundle fits ───────────────────────────────────────────────
async def fit_to_budget(bundle: list[dict],
                         target_tokens: int,
                         max_iters: int = 6) -> tuple[list[dict], dict]:
    """Trim until the bundle is under target_tokens. Each iteration picks the
    top 25% largest READMEs in the still-too-big bundle and summarises them.
    Returns (final_bundle, meta). meta captures the audit trail."""
    meta: dict = {
        "target_tokens": target_tokens,
        "iterations": [],
        "summarised_repos": [],
        "stop_reason": None,
    }
    cur = list(bundle)

    for it in range(max_iters):
        tokens = est_bundle_tokens(cur)
        meta["iterations"].append({"pass": it, "tokens": tokens})
        if tokens <= target_tokens:
            meta["stop_reason"] = f"fit at pass {it}"
            return cur, meta

        # Pick the top 25% by current readme size. Summarise them.
        cohort_indices = _cohort_top_pct(cur, 0.25)
        targets = [cur[i] for i in cohort_indices]
        # Pair each target with its own before_chars for the audit trail.
        indexed_targets = [(ci, cur[ci]) for ci in cohort_indices]
        summaries = await _summarise_cohort(targets)
        for (idx, target_b), (abs_idx, summary) in zip(
                indexed_targets, zip(cohort_indices, summaries)):
            entry = cur[abs_idx]
            entry["readme"] = ""                    # drop the prose entirely
            entry["purpose"] = summary.get("purpose", entry.get("purpose", ""))
            entry["entities"] = summary.get("entities", entry.get("entities", []))
            entry["domain"] = summary.get("domain", entry.get("domain", ""))
            entry["_summarised"] = True
            entry["_heuristic"] = bool(summary.get("_heuristic", False))
            meta["summarised_repos"].append({
                "pass": it,
                "name": entry.get("name"),
                "heuristic": entry["_heuristic"],
                "before_chars": len(target_b.get("readme") or ""),
            })

    meta["stop_reason"] = f"max_iters ({max_iters}) reached — bundle still {est_bundle_tokens(cur)} tokens"
    return cur, meta


# ── persist to ~/.git-suite/themes-bundle.json ─────────────────────────────
_BUNDLE_PATH = Path(os.environ.get(
    "GIT_SUITE_HOME", str(Path.home() / ".git-suite"))) / "themes-bundle.json"


async def build_and_persist(session_id: str,
                             target_tokens: int | None = None,
                             context_window: int | None = None,
                             force_full_readme: bool = False) -> dict:
    """Top-level entry: build the bundle, trim to budget, persist to disk,
    return the meta block + the path so the caller can hand it to the LLM."""
    ct_window = context_window or _active_window()
    target = target_tokens or int(ct_window * DEFAULT_BUDGET_FRACTION)

    raw = await build_raw_bundle(session_id)
    trimmed, meta = await fit_to_budget(raw, target)

    artefact = {
        "schema": "themes-bundle/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "context_window": ct_window,
        "target_tokens": target,
        "meta": meta,
        "bundle": trimmed,
    }

    _BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _BUNDLE_PATH.write_text(json.dumps(artefact, ensure_ascii=False, indent=0),
                            encoding="utf-8")
    meta["path"] = str(_BUNDLE_PATH)
    meta["size_bytes"] = _BUNDLE_PATH.stat().st_size
    return meta


# ── serialise into the themes prompt ────────────────────────────────────────
def to_prompt_records(artefact: dict) -> list[dict]:
    """Strip the readme text for the prompt (it's been summarised into
    purpose/entities/domain already if it was kept)."""
    out = []
    for r in artefact.get("bundle", []):
        out.append({
            "name": r.get("name", ""),
            "full_name": r.get("full_name", ""),
            "purpose": r.get("purpose", ""),
            "entities": r.get("entities") or [],
            "domain": r.get("domain", ""),
            "topics": r.get("topics") or [],
            "language": r.get("language", ""),
            "stars": r.get("stars", 0),
            "description": r.get("description", ""),
        })
    return out
