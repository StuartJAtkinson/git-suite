"""replan: rule scoring and two-phase proposal generation (offline — no LLM)."""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Force rules-only so proposal generation is deterministic and offline."""
    from services import llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)


def _recon(undecided, orphans, ghosts=None, hubs=None):
    return {
        "stats": {"undecided": undecided},
        "orphans": orphans,
        "ghosts": ghosts or [],
        "hubs": hubs or [{"name": "map-suite", "description": "maps",
                          "absorb_total": 8}],
    }


def test_incremental_phase_verdicts_and_ghosts(monkeypatch):
    from services import replan
    # No keyword rules anymore: the absorb proposal comes from the embedding path,
    # which ranks against the actual plan hubs. Stub it so the test stays offline.
    async def fake_rank(orphans, hubs):
        return {"tilemaker": [("map-suite", 0.7)]}
    monkeypatch.setattr(replan, "_embed_rank", fake_rank)
    recon = _recon(
        undecided=2,
        orphans=[
            {"name": "tilemaker", "aim": "osm vector tiles", "language": "C++", "topics": ["maps"]},
            {"name": "map-suite", "aim": "the hub", "language": "", "topics": []},  # a hub
        ],
        ghosts=[
            {"name": "deadrepo", "hub": "map-suite", "verdict": "absorb", "was_live": True},
            {"name": "external-lib", "hub": "map-suite", "verdict": "absorb", "was_live": False},
        ],
    )
    phase, proposals = asyncio.run(replan.generate_proposals(recon))
    assert phase == "incremental"
    kinds = [p["kind"] for p in proposals]
    assert "verdict" in kinds and "ghost-prune" in kinds
    # only the once-live ghost is proposed for pruning; external one is left alone
    prune_targets = {p["target"] for p in proposals if p["kind"] == "ghost-prune"}
    assert prune_targets == {"deadrepo"}
    # the hub repo self-keeps
    hub_p = next(p for p in proposals if p["target"] == "map-suite")
    assert hub_p["proposed"]["verdict"] == "keep"
    # the maps repo is proposed into map-suite
    tile_p = next(p for p in proposals if p["target"] == "tilemaker")
    assert tile_p["proposed"]["hub"] == "map-suite"


def test_stub_orphan_proposed_for_archive():
    from services import replan
    recon = _recon(
        undecided=1,
        orphans=[{"name": "junk", "aim": "", "language": "", "topics": [],
                  "stub_reason": "likely stub: 4KB, no description, no stars/topics"}],
    )
    _, proposals = asyncio.run(replan.generate_proposals(recon))
    p = next(x for x in proposals if x["target"] == "junk")
    assert p["proposed"]["verdict"] == "archive"


def test_replan_phase_unlocks_structural():
    from services import replan
    recon = _recon(
        undecided=0,
        orphans=[],
        hubs=[{"name": "game-hub", "description": "games", "absorb_total": 21}],
    )
    phase, proposals = asyncio.run(replan.generate_proposals(recon))
    assert phase == "replan"
    kinds = {p["kind"] for p in proposals}
    assert "split" in kinds       # game-hub absorb_total >= 16
