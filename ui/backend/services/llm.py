"""
llm.py — unified async LLM call with provider failover.

Builds a priority-ordered provider chain from config (~/.git-suite/config.json
+ env), then tries each in turn. When a provider is out of credits/quota — or
is transiently broken (bad key, rate-limited, 5xx) — it advances to the next
and remembers that, so later calls skip the dead provider too.

This is the async adaptation of the belzona-tickets LLMClient pattern, scoped
to what git-suite needs: a single text/JSON completion (no streaming/tools).

Usage:
    from services import llm
    text = await llm.complete("prompt", system="optional", max_tokens=512)
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

from llm_providers import (
    PROVIDERS, DEFAULT_PRIORITY, GLOBAL_EXHAUST_PHRASES, TRANSIENT_PHRASES,
)

log = logging.getLogger(__name__)

# Persisted across calls: index of the first provider worth trying. Advances
# when a leading provider is found exhausted/dead so we stop hammering it.
_floor = 0


class AllProvidersFailed(RuntimeError):
    pass


# --- chain construction ----------------------------------------------------

def _config() -> dict:
    try:
        from routers.config import _load
        return _load()
    except Exception:
        return {}


def build_chain() -> list[tuple[str, str, str]]:
    """Return ordered [(provider, key, model)] of usable providers."""
    cfg = _config()
    keys: dict[str, str] = dict(cfg.get("llm_keys", {}))
    models: dict[str, str] = cfg.get("llm_models", {})
    # Anthropic key may live only in the environment (Infisical / .env).
    if not keys.get("anthropic") and os.environ.get("ANTHROPIC_API_KEY"):
        keys["anthropic"] = os.environ["ANTHROPIC_API_KEY"]

    explicit = cfg.get("llm_priority_order") or []
    # Append any known providers not explicitly ordered, in default order.
    order = explicit + [p for p in DEFAULT_PRIORITY if p not in explicit]

    chain: list[tuple[str, str, str]] = []
    for name in order:
        meta = PROVIDERS.get(name)
        if not meta:
            continue
        key = keys.get(name, "")
        if meta["needs_key"]:
            if not key:
                continue
        else:
            # Keyless providers (Ollama) require explicit opt-in so we never
            # hammer localhost when the user hasn't configured them.
            if name not in explicit and name not in models:
                continue
        model = models.get(name) or meta["default_model"]
        chain.append((name, key, model))
    return chain


def has_provider() -> bool:
    return bool(build_chain())


def chain_summary() -> list[dict]:
    """For the UI: the resolved failover order (no secrets)."""
    chain = build_chain()
    return [
        {"provider": n, "display": PROVIDERS[n]["display_name"],
         "model": m, "active": i == _floor}
        for i, (n, _k, m) in enumerate(chain)
    ]


def reset_floor() -> None:
    global _floor
    _floor = 0


# --- failover detection ----------------------------------------------------

def _matches(msg: str, patterns) -> bool:
    msg = msg.lower()
    return any(p.lower() in msg for p in patterns)


def _should_failover(exc: Exception, provider: str) -> bool:
    msg = str(exc)
    meta = PROVIDERS.get(provider, {})
    return (
        _matches(msg, meta.get("exhaust_patterns", []))
        or _matches(msg, GLOBAL_EXHAUST_PHRASES)
        or _matches(msg, TRANSIENT_PHRASES)
    )


# --- per-provider calls ----------------------------------------------------

async def _call_anthropic(base_url, key, model, prompt, system, max_tokens) -> str:
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    # Anthropic-compat providers (e.g. MiniMax at api.minimax.io/anthropic)
    # may chain a mandatory thinking block before the text answer. If the
    # caller passed a tight max_tokens (e.g. 200 for a distill JSON parse),
    # the thinking block eats the entire budget and produces no text. Floor
    # to 4096 (light calls) or 16384 (the topic-discovery prompt that asks
    # for a 30-theme JSON — without that headroom MiniMax truncates mid-
    # array and the response won't parse).
    body["max_tokens"] = max(body["max_tokens"], 4096)
    if max_tokens >= 8000:
        body["max_tokens"] = max(body["max_tokens"], 16384)
    # Anthropic-compat providers (e.g. MiniMax at api.minimax.io/anthropic)
    # already include the /v1 segment in their base_url; doubling up
    # (base/v1/v1/messages) returns 404. Strip a trailing /v1 if present so
    # the canonical https://api.anthropic.com default still gets its /v1.
    base = base_url.rstrip("/") if base_url else "https://api.anthropic.com/v1"
    if base.endswith("/v1"):
        url = f"{base}/messages"
    else:
        url = f"{base}/v1/messages"
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            url,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=body,
        )
        if r.status_code >= 400:                # body carries the exhaust/quota text
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        content = data.get("content") or []
        # Take the last text block — Anthropic-compat providers (e.g. MiniMax)
        # may emit intermediate `thinking` blocks before the answer.
        text = next((b.get("text") for b in reversed(content)
                     if isinstance(b, dict) and b.get("type") == "text"), None)
        if not text:
            raise RuntimeError("anthropic returned no text block")
        return text


async def _call_openai_compat(base_url, key, model, prompt, system, max_tokens) -> str:
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": msgs, "max_tokens": max_tokens},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


async def _call_ollama(base_url, model, prompt, system, max_tokens) -> str:
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{base_url}/api/chat",
            json={"model": model, "messages": msgs, "stream": False},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["message"]["content"]


async def _dispatch(name, key, model, prompt, system, max_tokens) -> str:
    # Call URLs are a standard element of each provider — hardcoded in the
    # registry, not user-configurable (provider URL changes are rare events
    # handled by a registry edit).
    api_type = PROVIDERS[name]["api_type"]
    base = PROVIDERS[name]["base_url"]
    if api_type == "anthropic":
        return await _call_anthropic(base, key, model, prompt, system, max_tokens)
    if api_type == "openai_compat":
        return await _call_openai_compat(base, key, model, prompt, system, max_tokens)
    if api_type == "ollama":
        return await _call_ollama(key or base, model, prompt, system, max_tokens)
    raise RuntimeError(f"unknown api_type {api_type}")


# --- public entry ----------------------------------------------------------

async def complete(prompt: str, system: str = "", max_tokens: int = 1024) -> str:
    """Run a completion through the failover chain. Raises AllProvidersFailed."""
    global _floor
    chain = build_chain()
    if not chain:
        raise AllProvidersFailed("no LLM providers configured")

    errors: list[str] = []
    idx = min(_floor, len(chain) - 1)
    while idx < len(chain):
        name, key, model = chain[idx]
        try:
            text = await _dispatch(name, key, model, prompt, system, max_tokens)
        except Exception as exc:
            # Fail over on ANY provider error — a misconfigured leading provider
            # (e.g. a 404 from a wrong endpoint/model) must not kill the chain.
            # `_should_failover` now only flavours the log; the next provider is
            # always tried.
            errors.append(f"{name}: {str(exc)[:160]}")
            log.warning("LLM provider %s failed (failover=%s): %s",
                        name, _should_failover(exc, name), str(exc)[:160])
            if idx + 1 < len(chain):
                _floor = idx + 1            # skip this dead leading provider next time
                idx += 1
                continue
            raise AllProvidersFailed("all LLM providers failed — "
                                     + "; ".join(errors)) from exc
        if not text or not text.strip():
            errors.append(f"{name}: empty response")
            if idx + 1 < len(chain):
                log.warning("LLM provider %s returned empty — failing over", name)
                _floor = idx + 1
                idx += 1
                continue
            raise AllProvidersFailed("all LLM providers failed — " + "; ".join(errors))
        if idx != _floor:
            _floor = idx  # stick with the one that worked
        return text

    raise AllProvidersFailed("all LLM providers failed — " + "; ".join(errors))


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


async def complete_json(prompt: str, system: str = "", max_tokens: int = 1024):
    """complete() + JSON parse, stripping any ```json fences the model adds."""
    raw = (await complete(prompt, system=system, max_tokens=max_tokens)).strip()
    m = _FENCE.match(raw)
    return json.loads(m.group(1) if m else raw)
