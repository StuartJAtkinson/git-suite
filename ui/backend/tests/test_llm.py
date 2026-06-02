"""llm: failover detection and the provider-chain loop."""
import asyncio

import pytest


def test_should_failover_exhaustion():
    from services import llm
    assert llm._should_failover(RuntimeError("Your credit balance is too low"), "anthropic")


def test_should_failover_transient():
    from services import llm
    assert llm._should_failover(RuntimeError("HTTP 429: rate limit"), "openai")


def test_should_not_failover_on_normal_error():
    from services import llm
    assert not llm._should_failover(RuntimeError("json decode failed"), "openai")


def test_build_chain_respects_priority_and_keys(monkeypatch):
    from services import llm
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_config", lambda: {
        "llm_keys": {"anthropic": "k1", "deepseek": "k2"},
        "llm_priority_order": ["deepseek", "anthropic"],
    })
    chain = [(n, m) for n, _k, m in llm.build_chain()]
    assert chain[0][0] == "deepseek"
    assert chain[1][0] == "anthropic"


def test_build_chain_excludes_ollama_unless_opted_in(monkeypatch):
    from services import llm
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_config", lambda: {"llm_keys": {"anthropic": "k1"}})
    assert "ollama" not in [n for n, _, _ in llm.build_chain()]
    monkeypatch.setattr(llm, "_config", lambda: {
        "llm_keys": {"anthropic": "k1"}, "llm_priority_order": ["anthropic", "ollama"]})
    assert "ollama" in [n for n, _, _ in llm.build_chain()]


def test_build_chain_empty_without_config(monkeypatch):
    from services import llm
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_config", lambda: {})
    assert llm.build_chain() == []
    assert llm.has_provider() is False


def test_complete_fails_over_to_next_provider(monkeypatch):
    from services import llm
    llm.reset_floor()
    monkeypatch.setattr(llm, "build_chain", lambda: [("anthropic", "k1", "m1"), ("openai", "k2", "m2")])
    tried = []

    async def fake(name, key, model, prompt, system, mt):
        tried.append(name)
        if name == "anthropic":
            raise RuntimeError("credit balance is too low")
        return "ok from " + name

    monkeypatch.setattr(llm, "_dispatch", fake)
    out = asyncio.run(llm.complete("hi"))
    assert out == "ok from openai"
    assert tried == ["anthropic", "openai"]
    # floor advanced — a second call skips the exhausted provider
    tried.clear()
    asyncio.run(llm.complete("again"))
    assert tried == ["openai"]


def test_complete_raises_when_no_providers(monkeypatch):
    from services import llm
    llm.reset_floor()
    monkeypatch.setattr(llm, "build_chain", lambda: [])
    with pytest.raises(llm.AllProvidersFailed):
        asyncio.run(llm.complete("hi"))
