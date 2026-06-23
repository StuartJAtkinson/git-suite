"""
distill.py — per-repo semantic record, produced by the LLM distillation loop.

The OLD problem: raw repo blurbs are dominated by generic "it's software/a
tool/a library" framing, so nomic embeddings of them bunch into one tight,
undifferentiated band. The LLM has the real signal (purpose, entities, domain)
but only sees a one-line blurb.

The NEW shape: for each repo we hand the LLM a STRICT three-field schema
returned as JSON — `purpose` (one sentence), `entities` (list of 2-5 concrete
nouns), `domain` (≤3 words naming the field). The prompt is the same for every
repo, so the resulting records are directly comparable across the portfolio.

Clustering consumes `domain` + `entities` (those are the signal the embedding
cares about). A future revalidate pass re-asks the LLM "is the purpose still
consistent with the cluster it landed in?" and reports fit / drift.

Distillation is intentionally a SEPARATE step from scan (a button on /scan, a
loop you can interrupt by closing the page, and one you can resume by running
it again — the cache key is src_hash). The loop also stops on the first
LLM credit-exhausted error so we don't hammer a dead provider.

Stops on `OutOfCredits` and on the first LLM failure if `stop_on_error=True`
(the default for the /scan/distill endpoint). The cluster fallback (raw text
embedding) still works if no records exist yet.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re

from database import get_db
from services import llm

log = logging.getLogger(__name__)


# ── system prompt — same for every repo, that's the point ──────────────────
_SYS = (
    "You produce a STRICT JSON object describing one code repository. "
    "Do NOT call it software, a tool, a library, an app, a framework, or a "
    "project, and do NOT name the programming language. The schema is exactly:\n"
    + '{"purpose": "<one sentence, max 25 words, naming what the repo does '
    + 'for its users, not how it is built>", '
    + '"entities": ["<concrete noun 1>", "<concrete noun 2>", ... 2 to 5 items], '
    + '"domain": "<max 3 words naming the field or industry>"}\n'
    + "If the inputs are insufficient, answer with empty strings / empty list."
)

# system prompt for the revalidate (cluster-fit) pass — same for every repo.
_SYS_RV = (
    "You judge whether a repo's purpose still belongs in the cluster it was "
    "assigned. Answer STRICT JSON: {\"verdict\":\"fit|drift|mis-clustered\","
    "\"reason\":\"<≤15 words>\"}. Empty/unknown → empty verdict."
)


# ── source composition + change detection ───────────────────────────────────
def _src(repo: dict) -> str:
    """The text we hand the LLM. Stable order → stable hash → stable cache."""
    parts = [
        f"NAME: {repo.get('name') or repo.get('repo') or ''}",
        f"DESCRIPTION: {repo.get('aim') or repo.get('description') or ''}",
        f"TOPICS: {' '.join(repo.get('topics') or [])}",
        f"README_URL: {repo.get('readme_url') or ''}",
        f"REPO_URL: {repo.get('url') or ''}",
    ]
    return "\n".join(parts).strip()


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _key(repo: dict) -> str:
    """Stable key. full_name if present (for stars); fall back to name."""
    return repo.get("full_name") or repo.get("name") or repo.get("repo") or ""


# ── prompt + parse ──────────────────────────────────────────────────────────
async def _ask(record_src: str) -> dict:
    """One LLM call → parsed dict. Raises on parse failure or LLM error."""
    raw = (await llm.complete(record_src, system=_SYS, max_tokens=200)).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    blob = m.group(0) if m else raw
    out = json.loads(blob)
    return {
        "purpose": str(out.get("purpose", "")).strip()[:400],
        "entities": [str(x).strip() for x in (out.get("entities") or [])][:5],
        "domain": str(out.get("domain", "")).strip()[:60],
    }


# ── cache I/O ───────────────────────────────────────────────────────────────
async def _cached(keys: list[str]) -> dict[str, tuple[str, str]]:
    if not keys:
        return {}
    async for db in get_db():
        rows = await db.execute_fetchall(
            f"SELECT repo, record, src_hash FROM repo_domain "
            f"WHERE repo IN ({','.join('?' * len(keys))})",
            tuple(keys),
        )
    out: dict[str, tuple[str, str]] = {}
    for r in rows:
        rec = r["record"]
        if rec:
            out[r["repo"]] = (rec, r["src_hash"])
    return out


async def _store(items: list[tuple[str, dict, str]]) -> None:
    if not items:
        return
    async for db in get_db():
        await db.executemany(
            "INSERT OR REPLACE INTO repo_domain (repo, summary, record, src_hash) "
            "VALUES (?, ?, ?, ?)",
            [(k, rec.get("domain", ""), json.dumps(rec), h) for k, rec, h in items],
        )
        await db.commit()


# ── public API ──────────────────────────────────────────────────────────────
async def records(repos: list[dict], stop_on_error: bool = True,
                  concurrency: int = 6) -> tuple[dict[str, dict], str | None]:
    """Distil each repo. Returns ({key: record}, stop_reason).

    Re-uses cached rows whose src_hash matches. Stops on the first LLM error
    if stop_on_error is set; otherwise records the failure and continues. The
    summary string is "" on success, or a short reason ("no provider", "rate
    limit", "out of credits") on early stop.
    """
    srcs = {_key(r): _src(r) for r in repos}
    cache = await _cached(list(srcs))
    out: dict[str, dict] = {}
    todo: list[str] = []
    for k, src in srcs.items():
        hit = cache.get(k)
        if hit and hit[1] == _hash(src):
            out[k] = json.loads(hit[0])
        else:
            todo.append(k)

    if not todo:
        return out, ""

    sem = asyncio.Semaphore(concurrency)
    stop_reason = ""

    async def one(k: str) -> tuple[str, dict | None, str | None]:
        nonlocal stop_reason
        async with sem:
            if stop_reason and stop_on_error:
                return k, None, None
            try:
                rec = await _ask(srcs[k])
            except llm.AllProvidersFailed as exc:
                stop_reason = f"no provider ({exc})"
                return k, None, stop_reason
            except Exception as exc:        # parse fail, HTTP, transient
                # Distinguish "ran out of money" from transient network noise.
                msg = str(exc).lower()
                if any(w in msg for w in ("credit", "quota", "billing", "402",
                                          "payment", "rate limit", "429")):
                    stop_reason = f"LLM: {str(exc)[:120]}"
                    return k, None, stop_reason
                if stop_on_error:
                    stop_reason = f"LLM: {str(exc)[:120]}"
                    return k, None, stop_reason
                log.warning("distill %s failed (continuing): %s", k, str(exc)[:120])
                return k, None, None
            return k, rec, None

    results = await asyncio.gather(*[one(k) for k in todo])
    store_items = [(k, rec, _hash(srcs[k]))
                   for k, rec, _ in results if rec is not None]
    await _store(store_items)
    for k, rec, _ in results:
        if rec is not None:
            out[k] = rec
        elif k in srcs and not stop_reason:
            # soft failure → use raw text for THIS run, leave uncached
            out[k] = {"purpose": "", "entities": [], "domain": srcs[k]}
    return out, stop_reason


async def revalidate(repos: list[dict], clusters: dict[str, str],
                     stop_on_error: bool = True) -> dict[str, str]:
    """Second pass. Re-asks the LLM with the cluster context and returns a
    verdict per repo: 'fit', 'drift', or 'mis-clustered' (empty when unknown)."""
    srcs = {_key(r): _src(r) for r in repos}
    out: dict[str, str] = {}

    sem = asyncio.Semaphore(6)
    stop_reason = ""

    async def one(k: str) -> tuple[str, str]:
        nonlocal stop_reason
        cluster = clusters.get(k, "")
        prompt = (
            f"{srcs[k]}\n\n"
            f"CLUSTER_LABEL: {cluster}\n"
            "Does this repo's purpose fit that cluster, drift (same domain but "
            "different angle), or is it mis-clustered?"
        )
        async with sem:
            if stop_reason and stop_on_error:
                return k, ""
            try:
                raw = (await llm.complete(prompt, system=_SYS_RV,
                                          max_tokens=80)).strip()
            except Exception as exc:
                msg = str(exc).lower()
                if any(w in msg for w in ("credit", "quota", "billing", "402",
                                          "rate limit", "429")):
                    stop_reason = f"LLM: {str(exc)[:120]}"
                elif stop_on_error:
                    stop_reason = f"LLM: {str(exc)[:120]}"
                return k, ""
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            try:
                v = json.loads(m.group(0) if m else raw)
            except Exception:
                return k, ""
            return k, str(v.get("verdict", "")).strip() or ""
    out_list = await asyncio.gather(*[one(k) for k in srcs])
    for k, v in out_list:
        out[k] = v
    return out
