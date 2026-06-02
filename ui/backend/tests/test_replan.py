"""replan: rule scoring and two-phase proposal generation (offline — no LLM)."""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Force rules-only so proposal generation is deterministic and offline."""
    from services import llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)


def test_score_hub_picks_topical_hub():
    from services import replan
    ranked = replan._score_hub("an osm map tile renderer with geo terrain", "")
    assert ranked[0][0] == "map-suite"


def test_rule_proposal_uses_topics():
    from services import replan
    p = replan._rule_proposal({"name": "thing", "aim": "", "language": "", "topics": ["pokemon", "ffxiv"]})
    assert p["proposed"]["hub"] == "game-hub"


def _recon(undecided, orphans, ghosts=None, hubs=None, layers=None):
    return {
        "stats": {"undecided": undecided},
        "orphans": orphans,
        "ghosts": ghosts or [],
        "hubs": hubs or [{"name": "map-suite", "layer": 5, "description": "maps",
                          "absorb_total": 8}],
        "layers": layers or [],
    }


def test_incremental_phase_verdicts_and_ghosts():
    from services import replan
    recon = _recon(
        undecided=2,
        orphans=[
            {"name": "tilemaker", "aim": "osm vector tiles", "language": "C++", "topics": ["maps"]},
            {"name": "map-suite", "aim": "the hub", "language": "", "topics": []},  # a hub
        ],
        ghosts=[{"name": "deadrepo", "hub": "map-suite", "verdict": "absorb"}],
    )
    phase, proposals = asyncio.run(replan.generate_proposals(recon))
    assert phase == "incremental"
    kinds = [p["kind"] for p in proposals]
    assert "verdict" in kinds and "ghost-prune" in kinds
    # the hub repo self-keeps
    hub_p = next(p for p in proposals if p["target"] == "map-suite")
    assert hub_p["proposed"]["verdict"] == "keep"
    # the maps repo is proposed into map-suite
    tile_p = next(p for p in proposals if p["target"] == "tilemaker")
    assert tile_p["proposed"]["hub"] == "map-suite"


def test_replan_phase_unlocks_structural():
    from services import replan
    recon = _recon(
        undecided=0,
        orphans=[],
        hubs=[{"name": "game-hub", "layer": 6, "description": "games", "absorb_total": 21}],
        layers=[{"num": 9, "name": "Creative & Graphics", "hubs": []}],
    )
    phase, proposals = asyncio.run(replan.generate_proposals(recon))
    assert phase == "replan"
    kinds = {p["kind"] for p in proposals}
    assert "split" in kinds       # game-hub absorb_total >= 16
    assert "new-hub" in kinds     # layer 9 has no hub
