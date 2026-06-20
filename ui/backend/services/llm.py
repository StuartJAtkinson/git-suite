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
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{base_url or 'https://api.anthropic.com/v1'}/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=body,
        )
        if r.status_code >= 400:                # body carries the exhaust/quota text
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        if not data.get("content"):
            raise RuntimeError("anthropic returned empty content")
        return data["content"][0]["text"]


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

    last_exc: Exception | None = None
    idx = min(_floor, len(chain) - 1)
    while idx < len(chain):
        name, key, model = chain[idx]
        try:
            text = await _dispatch(name, key, model, prompt, system, max_tokens)
        except Exception as exc:
            last_exc = exc
            if _should_failover(exc, name) and idx + 1 < len(chain):
                log.warning("LLM provider %s failing over: %s", name, str(exc)[:160])
                _floor = idx + 1
                idx += 1
                continue
            raise
        if not text or not text.strip():
            if idx + 1 < len(chain):
                log.warning("LLM provider %s returned empty — failing over", name)
                _floor = idx + 1
                idx += 1
                continue
            raise AllProvidersFailed("all providers returned empty")
        if idx != _floor:
            _floor = idx  # stick with the one that worked
        return text

    raise AllProvidersFailed(f"all providers failed; last error: {last_exc}")


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


async def complete_json(prompt: str, system: str = "", max_tokens: int = 1024):
    """complete() + JSON parse, stripping any ```json fences the model adds."""
    raw = (await complete(prompt, system=system, max_tokens=max_tokens)).strip()
    m = _FENCE.match(raw)
    return json.loads(m.group(1) if m else raw)
