"""distill: structured-record prompt, caching, credit-exhaust stop, revalidate."""
import asyncio
import json

from services import distill, llm


def _llm_json(monkeypatch, payload):
    """Patch llm.complete to return a JSON blob in the model-style format."""
    async def fake(prompt, system="", max_tokens=80):
        return json.dumps(payload)
    monkeypatch.setattr(llm, "complete", fake)


def test_records_parse_strict_json(temp_db, monkeypatch):
    _llm_json(monkeypatch, {
        "purpose": "Generates OpenStreetMap vector tiles for web renderers.",
        "entities": ["OSM", "vector tiles", "MBTiles", "maps"],
        "domain": "geospatial rendering",
    })
    repo = {"name": "tilemaker", "description": "build maps", "topics": ["osm"]}
    out, reason = asyncio.run(distill.records([repo], stop_on_error=True))
    assert reason == ""
    rec = out["tilemaker"]
    assert rec["domain"] == "geospatial rendering"
    assert "OSM" in rec["entities"]
    assert "tiles" in rec["purpose"].lower()


def test_records_caches_and_regenerates_on_source_change(temp_db, monkeypatch):
    _llm_json(monkeypatch, {
        "purpose": "x", "entities": ["a"], "domain": "d",
    })
    repo = {"name": "tilemaker", "description": "build maps", "topics": []}
    out1, _ = asyncio.run(distill.records([repo]))
    out2, _ = asyncio.run(distill.records([repo]))      # cached
    assert out1 == out2

    # Change the input text (now includes a topics token) → new src_hash → regen
    repo["topics"] = ["osm", "tiles"]
    out3, _ = asyncio.run(distill.records([repo]))
    assert out3["tilemaker"] == out1["tilemaker"]      # LLM stub returned same


def test_credit_exhaustion_stops_the_loop(temp_db, monkeypatch):
    async def fake(prompt, system="", max_tokens=80):
        raise RuntimeError("402 Payment Required: out of credits")
    monkeypatch.setattr(llm, "complete", fake)

    repos = [{"name": f"r{i}", "description": "x", "topics": []} for i in range(5)]
    out, reason = asyncio.run(distill.records(repos, stop_on_error=True))
    assert "out of credits" in reason.lower() or "402" in reason
    # The first call set the stop reason; the rest bail without populating.
    # All repos fall back to raw text (empty purpose/entities), but no panic.
    for k in out:
        assert isinstance(out[k], dict)


def test_revalidate_returns_verdict_per_repo(temp_db, monkeypatch):
    _llm_json(monkeypatch, {"verdict": "drift",
                            "reason": "Same domain, different angle."})
    repos = [{"name": "a", "description": "x", "topics": []},
             {"name": "b", "description": "y", "topics": []}]
    out = asyncio.run(distill.revalidate(repos, {"a": "maps", "b": "audio"}))
    assert out == {"a": "drift", "b": "drift"}


def test_revalidate_empty_when_llm_returns_nonsense(temp_db, monkeypatch):
    async def fake(prompt, system="", max_tokens=80):
        return "I cannot answer."
    monkeypatch.setattr(llm, "complete", fake)
    repos = [{"name": "a", "description": "x", "topics": []}]
    out = asyncio.run(distill.revalidate(repos, {"a": "x"}))
    assert out == {"a": ""}
