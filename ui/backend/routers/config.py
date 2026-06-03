"""config.py — LLM provider and task source configuration."""
import json, logging, os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()
_CONFIG_DIR = Path.home() / ".git-suite"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6", "openai": "gpt-4o",
    "openrouter": "anthropic/claude-sonnet-4-6", "deepseek": "deepseek-chat",
    "xai": "grok-beta", "minimax": "abab6.5-chat", "ollama": "llama3.2",
}
ALL_PROVIDERS = list(_DEFAULT_MODELS.keys())


def _apply_env_from_config():
    """Read anthropic key from config.json and export as ANTHROPIC_API_KEY env var.
    Config file takes priority over .env file — allows zero-env deployment."""
    try:
        if _CONFIG_FILE.exists():
            cfg = json.loads(_CONFIG_FILE.read_text())
            key = cfg.get("llm_keys", {}).get("anthropic") or cfg.get("anthropic_api_key")
            if key and not os.environ.get("ANTHROPIC_API_KEY"):
                os.environ["ANTHROPIC_API_KEY"] = key
                log.info("ANTHROPIC_API_KEY loaded from ~/.git-suite/config.json")
    except Exception as exc:
        log.warning("could not apply config env vars: %s", exc)


# Apply at import time (before uvicorn forks workers)
_apply_env_from_config()


def _load() -> dict:
    try:
        _CONFIG_DIR.mkdir(exist_ok=True)
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text())
    except Exception as exc:
        log.warning("failed to load config: %s", exc)
    return {}


def _save(cfg: dict) -> None:
    _CONFIG_DIR.mkdir(exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    os.chmod(_CONFIG_FILE, 0o600)


class ConfigGetResponse(BaseModel):
    llm_keys: dict[str, str]
    llm_models: dict[str, str]
    llm_priority_order: list[str]
    embedding_models: dict[str, str]   # provider -> embedding model (opt-in)


class ConfigPostRequest(BaseModel):
    llm_keys: dict[str, str] | None = None
    llm_models: dict[str, str] | None = None
    llm_priority_order: list[str] | None = None
    embedding_models: dict[str, str] | None = None


@router.get("/config", response_model=ConfigGetResponse)
async def get_config():
    cfg = _load()
    models = cfg.get("llm_models", {})
    for p in ALL_PROVIDERS:
        if p not in models:
            models[p] = _DEFAULT_MODELS[p]
    return ConfigGetResponse(
        llm_keys=cfg.get("llm_keys", {}), llm_models=models,
        llm_priority_order=cfg.get("llm_priority_order", []),
        embedding_models=cfg.get("embedding_models", {}),
    )


@router.post("/config")
async def post_config(body: ConfigPostRequest):
    cfg = _load()
    cfg.update(body.model_dump(exclude_none=True))
    _save(cfg)
    log.info("config saved")
    return {"saved": True}


@router.get("/config/providers")
async def list_providers():
    return [{"id": p, "default_model": _DEFAULT_MODELS[p]} for p in ALL_PROVIDERS]


@router.get("/config/llm-status")
async def llm_status():
    """Resolved LLM failover chain + embeddings chain (no secrets)."""
    from services import llm, embeddings
    chain = llm.chain_summary()
    embed_chain = [{"provider": n, "model": m} for n, _k, m in embeddings.build_chain()]
    return {
        "configured": bool(chain),
        "chain": chain,
        "embeddings": {"configured": bool(embed_chain), "chain": embed_chain},
    }
