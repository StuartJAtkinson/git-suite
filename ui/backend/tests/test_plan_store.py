"""plan_store: the single source of truth — verdicts, placement, persistence."""
import pytest


def test_seed_shape(isolated_plan):
    p = isolated_plan.get_plan()
    assert len(p["hubs"]) == 8
    assert len(p["archives"]) == 37          # canonical (drift fixed)
    assert "git-suite" in p["keeps"]


def test_hub_is_implicitly_keep(isolated_plan):
    placement = isolated_plan.repo_placement()
    assert placement["game-hub"] == {"verdict": "keep", "hub": None}


def test_set_verdict_keep(isolated_plan):
    isolated_plan.set_verdict("foo", "keep")
    assert "foo" in isolated_plan.get_plan()["keeps"]


def test_set_verdict_absorb_requires_hub(isolated_plan):
    with pytest.raises(ValueError):
        isolated_plan.set_verdict("foo", "absorb")            # no hub
    with pytest.raises(ValueError):
        isolated_plan.set_verdict("foo", "absorb", "no-such-hub")


def test_set_verdict_absorb(isolated_plan):
    isolated_plan.set_verdict("foo", "absorb", "media-hub")
    assert "foo" in isolated_plan.get_plan()["hubs"]["media-hub"]["absorbs"]
    assert isolated_plan.repo_placement()["foo"] == {"verdict": "absorb", "hub": "media-hub"}


def test_verdict_moves_repo_no_dupes(isolated_plan):
    isolated_plan.set_verdict("foo", "absorb", "media-hub")
    isolated_plan.set_verdict("foo", "archive", "media-hub")  # move
    plan = isolated_plan.get_plan()
    assert "foo" not in plan["hubs"]["media-hub"]["absorbs"]
    assert plan["archives"]["foo"] == "media-hub"


def test_orphan_unassigns(isolated_plan):
    isolated_plan.set_verdict("foo", "keep")
    isolated_plan.set_verdict("foo", "orphan")
    p = isolated_plan.get_plan()
    assert "foo" not in p["keeps"] and "foo" not in p["archives"]


def test_unknown_verdict_raises(isolated_plan):
    with pytest.raises(ValueError):
        isolated_plan.set_verdict("foo", "banish")


def test_persistence_roundtrip(isolated_plan):
    isolated_plan.set_verdict("foo", "keep")
    # a fresh read parses the file from disk
    assert "foo" in isolated_plan.get_plan()["keeps"]


def test_blank_clears_assignments_keeps_hub_shells(isolated_plan):
    isolated_plan.set_verdict("foo", "absorb", "media-hub")
    p = isolated_plan.blank()
    assert len(p["hubs"]) == 8                 # hub shells remain
    assert all(h["absorbs"] == [] for h in p["hubs"].values())
    assert p["archives"] == {} and p["keeps"] == []
    # a hub is still implicitly keep
    assert isolated_plan.repo_placement(p)["media-hub"]["verdict"] == "keep"
