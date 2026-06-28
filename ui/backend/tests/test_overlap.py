"""overlap: straddle detection + matrix (semantic-only; mocked embeddings)."""
import asyncio

from routers import overlap
from services import embeddings

# Minimal plan: two hubs, each described by its own metadata (no hardcoded taxonomy).
_PLAN = {"hubs": {"map-suite": {"description": "osm mapping", "boundary": ""},
                  "game-hub": {"description": "gaming", "boundary": ""}}}


def _mock_embeddings(monkeypatch):
    """Fake embed → a 2-D [map, game] vector from keyword presence, so cosine is
    deterministic and offline. has_embeddings forced on."""
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: True)

    async def fake_embed(texts):
        out = []
        for t in texts:
            tl = t.lower()
            m = 1.0 if any(k in tl for k in ("map", "osm", "tile", "geo", "gis")) else 0.0
            g = 1.0 if any(k in tl for k in ("game", "gaming", "dungeon", "rpg", "ffxiv", "poke")) else 0.0
            if m == 0 and g == 0:
                m = 1.0          # avoid a zero vector
            out.append([m, g])
        return out

    monkeypatch.setattr(embeddings, "embed", fake_embed)


def test_clear_repo_is_not_a_boundary_case(monkeypatch):
    _mock_embeddings(monkeypatch)
    repos = [{"name": "tilemaker", "aim": "osm vector map tiles geo", "language": "", "topics": []}]
    matrix, cases = asyncio.run(
        overlap._semantic_analyse(repos, ["map-suite", "game-hub"], _PLAN))
    assert cases == []


def test_straddling_repo_flagged_and_counted(monkeypatch):
    _mock_embeddings(monkeypatch)
    # text hitting both map ("map") and game ("dungeon") profiles
    repos = [{"name": "thing", "aim": "procedural dungeon map generator", "language": "", "topics": []}]
    matrix, cases = asyncio.run(
        overlap._semantic_analyse(repos, ["map-suite", "game-hub"], _PLAN))
    assert len(cases) == 1
    pair = {cases[0]["top"][0]["hub"], cases[0]["top"][1]["hub"]}
    assert pair == {"map-suite", "game-hub"}
    # symmetric matrix increment
    assert matrix["map-suite"]["game-hub"] == 1
    assert matrix["game-hub"]["map-suite"] == 1
