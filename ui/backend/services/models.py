"""
models.py — live model listing per provider dialect.

Atelier-Harness contract: no static model lists — they rot. Once a key is
present, the provider's own models endpoint is the source of truth. The
api_type (dialect) drives the query shape, not the vendor:

  anthropic      GET {base}/v1/models?limit=1000 — dual auth (x-api-key for
                 real Anthropic, Bearer for Anthropic-compatible endpoints
                 like MiniMax at api.minimax.io/anthropic)
  openai_compat  GET {base}/models — Bearer
  ollama         GET {base}/api/tags — keyless

git-suite makes one-off completion calls (llm.complete), so the "llm" kind
filters out non-text modalities (audio/image/embedding/realtime); the
"embedding" kind keeps only embedding models for the embeddings chain.
"""
from __future__ import annotations

import httpx

from llm_providers import PROVIDERS

TIMEOUT = 8.0

# Modalities this app never calls with a one-off text completion.
_NON_TEXT = ("embed", "whisper", "tts", "audio", "dall-e", "image",
             "moderation", "realtime", "transcribe")


def filter_models(ids: list[str], kind: str) -> list[str]:
    if kind == "embedding":
        return sorted(i for i in ids if "embed" in i.lower())
    return sorted(i for i in ids if not any(t in i.lower() for t in _NON_TEXT))


def request_spec(provider: str, key: str) -> tuple[str, dict]:
    """(url, headers) for the provider's model-listing call.

    Raises ValueError for providers with no listing endpoint (MiniMax's
    chat-completion host) so the UI can fall back to free-text entry.
    """
    meta = PROVIDERS.get(provider)
    if not meta:
        raise ValueError(f"unknown provider: {provider}")
    api = meta["api_type"]
    if api == "anthropic":
        base = (meta["base_url"] or "https://api.anthropic.com").rstrip("/")
        return (f"{base}/v1/models?limit=1000",
                {"x-api-key": key, "Authorization": f"Bearer {key}",
                 "anthropic-version": "2023-06-01"})
    if api == "openai_compat":
        return (f"{meta['base_url'].rstrip('/')}/models",
                {"Authorization": f"Bearer {key}"})
    if api == "ollama":
        return (f"{meta['base_url'].rstrip('/')}/api/tags", {})
    raise ValueError(
        f"{meta['display_name']} has no model-listing endpoint — enter a model name manually"
    )


def parse_ids(api_type: str, body: dict) -> list[str]:
    """Ollama /api/tags returns {models:[{name}]}; everything else {data:[{id}]}."""
    if api_type == "ollama":
        return [m.get("name", "") for m in body.get("models", [])]
    return [m.get("id", "") for m in body.get("data", [])]


async def list_models(provider: str, key: str = "", kind: str = "llm") -> list[str]:
    url, headers = request_spec(provider, key)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        ids = parse_ids(PROVIDERS[provider]["api_type"], r.json())
    return filter_models([i for i in ids if i], kind)
