"""
llm_providers.py — registry of LLM providers, driving the failover chain.

Adapted from the belzona-tickets pattern. Each provider declares its API
shape (api_type), endpoint, default model, and the substrings that mean
"this account is out of credits/quota" — which is what triggers failover to
the next provider in services/llm.py.
"""
from __future__ import annotations

from typing import Literal, TypedDict

ApiType = Literal["anthropic", "openai_compat", "ollama"]


class ProviderMeta(TypedDict):
    display_name: str
    api_type: ApiType
    base_url: str
    setup_url: str
    default_model: str
    needs_key: bool
    exhaust_patterns: list[str]


# Substrings checked across all providers (in addition to per-provider ones).
GLOBAL_EXHAUST_PHRASES: tuple[str, ...] = (
    "insufficient credits", "out of credits", "quota exceeded",
    "payment required", "billing", "402",
)

# Substrings that mean "this provider is misconfigured/unavailable right now"
# — also worth failing over (a bad key shouldn't sink the whole call).
TRANSIENT_PHRASES: tuple[str, ...] = (
    "invalid api key", "invalid_api_key", "authentication", "unauthorized",
    "401", "permission", "rate limit", "rate_limit", "429",
    "overloaded", "503", "502", "500", "timeout", "timed out",
    "connection", "could not connect",
)


PROVIDERS: dict[str, ProviderMeta] = {
    "anthropic": {
        "display_name": "Anthropic",
        "api_type": "anthropic",
        "base_url": "",
        "setup_url": "https://console.anthropic.com/settings/keys",
        "default_model": "claude-sonnet-4-6",
        "needs_key": True,
        "exhaust_patterns": [
            "credit balance is too low", "your credit balance",
            "insufficient_quota", "billing_not_active",
        ],
    },
    "openai": {
        "display_name": "OpenAI",
        "api_type": "openai_compat",
        "base_url": "https://api.openai.com/v1",
        "setup_url": "https://platform.openai.com/api-keys",
        "default_model": "gpt-4o",
        "needs_key": True,
        "exhaust_patterns": [
            "insufficient_quota", "exceeded your current quota",
            "billing hard limit", "you've run out of credits",
        ],
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "api_type": "openai_compat",
        "base_url": "https://api.deepseek.com/v1",
        "setup_url": "https://platform.deepseek.com/api_keys",
        "default_model": "deepseek-chat",
        "needs_key": True,
        "exhaust_patterns": [
            "insufficient balance", "account balance is insufficient", "quota exceeded",
        ],
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "api_type": "openai_compat",
        "base_url": "https://openrouter.ai/api/v1",
        "setup_url": "https://openrouter.ai/keys",
        "default_model": "anthropic/claude-sonnet-4-6",
        "needs_key": True,
        "exhaust_patterns": ["no credits", "insufficient credits", "out of credits"],
    },
    "xai": {
        "display_name": "xAI",
        "api_type": "openai_compat",
        "base_url": "https://api.x.ai/v1",
        "setup_url": "https://console.x.ai/",
        "default_model": "grok-3-mini",
        "needs_key": True,
        "exhaust_patterns": ["insufficient credits", "quota exceeded"],
    },
    "minimax": {
        "display_name": "MiniMax",
        # Anthropic-compatible endpoint — same /v1/messages + /v1/models shape
        # as api.anthropic.com, just a different host. Listing + completions
        # both go through the Anthropic branch with this base_url.
        "api_type": "anthropic",
        "base_url": "https://api.minimax.io/anthropic",
        "setup_url": "https://platform.minimax.io/user-center/basic-information/interface-key",
        "default_model": "MiniMax-M2",
        "needs_key": True,
        "exhaust_patterns": ["insufficient balance", "account has been limited", "quota exceeded"],
    },
    "ollama": {
        "display_name": "Ollama (local)",
        "api_type": "ollama",
        "base_url": "http://localhost:11434",
        "setup_url": "https://ollama.com",
        "default_model": "llama3.2",
        "needs_key": False,
        "exhaust_patterns": [],  # local — no credit concept
    },
}

# Default failover order when config has no explicit priority list.
DEFAULT_PRIORITY: list[str] = [
    "anthropic", "openai", "deepseek", "openrouter", "xai", "minimax", "ollama",
]
