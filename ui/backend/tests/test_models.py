"""models: live listing request shapes per dialect + kind filtering."""
import pytest

from services import models


def test_filter_llm_drops_non_text_modalities():
    ids = ["gpt-4o", "whisper-1", "text-embedding-3-small", "tts-1",
           "dall-e-3", "gpt-4o-realtime-preview", "deepseek-chat"]
    out = models.filter_models(ids, "llm")
    assert "gpt-4o" in out and "deepseek-chat" in out
    assert not any(m in out for m in
                   ["whisper-1", "text-embedding-3-small", "tts-1",
                    "dall-e-3", "gpt-4o-realtime-preview"])


def test_filter_embedding_keeps_only_embed():
    ids = ["gpt-4o", "text-embedding-3-small", "nomic-embed-text", "llama3.2"]
    assert models.filter_models(ids, "embedding") == \
        ["nomic-embed-text", "text-embedding-3-small"]


def test_anthropic_spec_dual_auth():
    url, headers = models.request_spec("anthropic", "sk-test")
    assert url.startswith("https://api.anthropic.com/v1/models")
    # Real Anthropic reads x-api-key; Anthropic-compatible endpoints read
    # Bearer — both are sent so listing works either way (Atelier pattern).
    assert headers["x-api-key"] == "sk-test"
    assert headers["Authorization"] == "Bearer sk-test"
    assert "anthropic-version" in headers


def test_openai_compat_spec():
    url, headers = models.request_spec("deepseek", "sk-d")
    assert url == "https://api.deepseek.com/v1/models"
    assert headers == {"Authorization": "Bearer sk-d"}


def test_ollama_spec_keyless_tags():
    url, headers = models.request_spec("ollama", "")
    assert url.endswith("/api/tags")
    assert headers == {}


def test_minimax_has_no_listing():
    with pytest.raises(ValueError, match="no model-listing endpoint"):
        models.request_spec("minimax", "k")


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="unknown provider"):
        models.request_spec("nope", "k")


def test_parse_ids_shapes():
    assert models.parse_ids("openai_compat",
                            {"data": [{"id": "a"}, {"id": "b"}]}) == ["a", "b"]
    assert models.parse_ids("anthropic",
                            {"data": [{"id": "claude-sonnet-4-6"}]}) == ["claude-sonnet-4-6"]
    assert models.parse_ids("ollama",
                            {"models": [{"name": "llama3.2"}]}) == ["llama3.2"]
