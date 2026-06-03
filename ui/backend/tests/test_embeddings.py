"""embeddings: cosine, provider-chain construction, graceful absence."""
from services import embeddings


def test_cosine_basics():
    assert embeddings.cosine([1, 0], [1, 0]) == 1.0
    assert embeddings.cosine([1, 0], [0, 1]) == 0.0
    assert abs(embeddings.cosine([1, 1], [1, 1]) - 1.0) < 1e-9
    assert embeddings.cosine([], [1]) == 0.0          # mismatch -> 0


def test_chain_needs_a_provider(monkeypatch):
    monkeypatch.setattr(embeddings, "_config", lambda: {})
    assert embeddings.build_chain() == []
    assert embeddings.has_embeddings() is False


def test_openai_key_enables_chain(monkeypatch):
    monkeypatch.setattr(embeddings, "_config", lambda: {"llm_keys": {"openai": "sk-x"}})
    chain = embeddings.build_chain()
    assert chain and chain[0][0] == "openai"
    assert chain[0][2] == "text-embedding-3-small"


def test_ollama_is_opt_in(monkeypatch):
    monkeypatch.setattr(embeddings, "_config", lambda: {})  # no opt-in
    assert "ollama" not in [n for n, _, _ in embeddings.build_chain()]
    monkeypatch.setattr(embeddings, "_config",
                        lambda: {"llm_priority_order": ["ollama"]})
    assert "ollama" in [n for n, _, _ in embeddings.build_chain()]


def test_embed_returns_none_without_provider(monkeypatch):
    import asyncio
    monkeypatch.setattr(embeddings, "build_chain", lambda: [])
    assert asyncio.run(embeddings.embed(["x"])) is None
