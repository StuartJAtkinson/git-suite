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


def test_complete_retries_transient_error_on_same_provider_before_failover(monkeypatch):
    """A DNS blip / rate-limit / timeout on a SINGLE-provider chain (the
    common case — only one API key configured, nothing to fail over to)
    must not be immediately fatal. Retry the same provider a couple of
    times first."""
    from services import llm
    llm.reset_floor()
    monkeypatch.setattr(llm, "build_chain", lambda: [("minimax", "k1", "m1")])

    sleeps = []
    async def fake_sleep(s):
        sleeps.append(s)
    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)

    calls = []
    async def fake(name, key, model, prompt, system, mt):
        calls.append(name)
        if len(calls) < 3:
            raise RuntimeError("HTTP 429: rate limit exceeded")
        return "ok after retries"

    monkeypatch.setattr(llm, "_dispatch", fake)
    out = asyncio.run(llm.complete("hi"))
    assert out == "ok after retries"
    assert calls == ["minimax", "minimax", "minimax"]
    assert len(sleeps) == 2                 # backed off before each retry


def test_complete_does_not_retry_exhaustion_errors(monkeypatch):
    """Credits/quota gone — retrying the same provider can't help, so it
    should fail over (or raise, if it's the only provider) immediately."""
    from services import llm
    llm.reset_floor()
    monkeypatch.setattr(llm, "build_chain", lambda: [("minimax", "k1", "m1")])

    calls = []
    async def fake(name, key, model, prompt, system, mt):
        calls.append(name)
        raise RuntimeError("insufficient balance")

    monkeypatch.setattr(llm, "_dispatch", fake)
    with pytest.raises(llm.AllProvidersFailed):
        asyncio.run(llm.complete("hi"))
    assert calls == ["minimax"]             # no retry attempts
