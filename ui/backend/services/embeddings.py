"""
embeddings.py — semantic vectors with provider failover + DB cache.

Embeds repo/hub text so overlap and absorb suggestions are semantic rather than
keyword-matched. Mirrors the llm.py philosophy: a priority chain of providers,
degrade gracefully (return None) when none is configured so callers fall back
to the keyword rules.

Embedding-capable providers: OpenAI (and OpenAI-compatible) + Ollama (local).
Vectors are cached in the `embedding` table keyed by model+text hash, so repeat
runs are cheap and only new/changed text is embedded.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math

import httpx

log = logging.getLogger(__name__)

EMBED_PROVIDERS: dict[str, dict] = {
    "openai": {"api_type": "openai_compat", "base_url": "https://api.openai.com/v1",
               "default_model": "text-embedding-3-small", "needs_key": True},
    "ollama": {"api_type": "ollama", "base_url": "http://localhost:11434",
               "default_model": "nomic-embed-text", "needs_key": False},
}
DEFAULT_PRIORITY = ["openai", "ollama"]


def _config() -> dict:
    try:
        from routers.config import _load
        return _load()
    except Exception:
        return {}


def build_chain() -> list[tuple[str, str, str]]:
    """Ordered [(provider, key, model)] of usable embedding providers."""
    cfg = _config()
    keys = dict(cfg.get("llm_keys", {}))
    emodels = cfg.get("embedding_models", {})
    explicit = cfg.get("llm_priority_order") or []
    order = [p for p in explicit if p in EMBED_PROVIDERS] + \
            [p for p in DEFAULT_PRIORITY if p not in explicit]
    chain = []
    for name in order:
        meta = EMBED_PROVIDERS[name]
        key = keys.get(name, "")
        if meta["needs_key"]:
            if not key:
                continue
        else:  # keyless (ollama) — opt-in only
            if name not in explicit and name not in emodels:
                continue
        chain.append((name, key, emodels.get(name) or meta["default_model"]))
    return chain


def has_embeddings() -> bool:
    return bool(build_chain())


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --- provider calls --------------------------------------------------------

async def _embed_openai(base, key, model, texts):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{base}/embeddings",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"model": model, "input": texts})
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        return [d["embedding"] for d in r.json()["data"]]


async def _embed_ollama(base, model, texts):
    out = []
    async with httpx.AsyncClient(timeout=120) as c:
        for t in texts:
            r = await c.post(f"{base}/api/embeddings", json={"model": model, "prompt": t})
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            out.append(r.json()["embedding"])
    return out


async def _embed_with(provider, key, model, texts):
    meta = EMBED_PROVIDERS[provider]
    if meta["api_type"] == "openai_compat":
        return await _embed_openai(meta["base_url"], key, model, texts)
    return await _embed_ollama(key or meta["base_url"], model, texts)


# --- cache -----------------------------------------------------------------

def _key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}::{text}".encode("utf-8")).hexdigest()


async def _load_cache(model: str, texts: list[str]) -> dict[str, list[float]]:
    from database import get_db
    keys = {t: _key(model, t) for t in texts}
    out: dict[str, list[float]] = {}
    async for db in get_db():
        rows = await db.execute_fetchall(
            f"SELECT key, vector FROM embedding WHERE key IN ({','.join('?' * len(keys))})",
            tuple(keys.values()),
        ) if keys else []
    by_key = {r["key"]: json.loads(r["vector"]) for r in rows}
    for t, k in keys.items():
        if k in by_key:
            out[t] = by_key[k]
    return out


async def _store_cache(model: str, texts: list[str], vecs: list[list[float]]) -> None:
    from database import get_db
    async for db in get_db():
        await db.executemany(
            "INSERT OR REPLACE INTO embedding (key, model, vector) VALUES (?, ?, ?)",
            [(_key(model, t), model, json.dumps(v)) for t, v in zip(texts, vecs)],
        )
        await db.commit()


async def embed(texts: list[str]) -> list[list[float]] | None:
    """Return a vector per text (cached), or None if no provider is usable."""
    if not texts:
        return []
    for provider, key, model in build_chain():
        cached = await _load_cache(model, texts)
        missing = [t for t in texts if t not in cached]
        if missing:
            try:
                vecs = await _embed_with(provider, key, model, missing)
            except Exception as exc:
                log.warning("embedding provider %s failed: %s", provider, str(exc)[:160])
                continue  # try next provider
            await _store_cache(model, missing, vecs)
            cached.update(dict(zip(missing, vecs)))
        return [cached[t] for t in texts]
    return None
