"""Step 2: targeted deltas over the grouping ledger (apply_delta + the LLM
prompt/validation helpers). No network — pure helpers and ledger mutation."""
import grouping_store
from services.topic_llm import _validate_deltas, _build_delta_prompt


def _ledger():
    return {
        "statuses": {
            "repo-a": {"status": "proposed", "clump": "alpha", "confidence": 0.8, "why": ""},
            "repo-b": {"status": "proposed", "clump": "alpha", "confidence": 0.8, "why": ""},
            "repo-c": {"status": "proposed", "clump": "beta", "confidence": 0.7, "why": ""},
            "repo-d": {"status": "settled", "clump": "alpha", "confidence": 0.95, "why": ""},
            "repo-e": {"status": "unsettled", "clump": None, "confidence": None, "why": ""},
        },
        "clumps": {
            "alpha": {"name": "alpha", "description": "", "confidence": 0.8},
            "beta": {"name": "beta", "description": "", "confidence": 0.7},
        },
        "answers": [], "pending": [], "round": 0, "floor": 0.85,
    }


def test_merge_combines_clumps_and_settles_members(isolated_grouping):
    ledge = _ledger()
    res = grouping_store.apply_delta(ledge, {
        "type": "merge", "a": "alpha", "b": "beta", "new_name": "merged",
        "confidence": 0.9,
    })
    assert res["ok"] is True
    assert "beta" not in ledge["clumps"]
    assert ledge["clumps"]["alpha"]["name"] == "merged"
    # repo-c moved from beta into alpha, and every alpha member is now settled
    assert ledge["statuses"]["repo-c"]["clump"] == "alpha"
    assert ledge["statuses"]["repo-c"]["status"] == "settled"
    assert ledge["statuses"]["repo-a"]["status"] == "settled"
    assert ledge["statuses"]["repo-d"]["status"] == "settled"


def test_split_peels_members_into_new_clump(isolated_grouping):
    ledge = _ledger()
    res = grouping_store.apply_delta(ledge, {
        "type": "split", "cluster": "alpha", "members": ["repo-b"],
        "new_name": "alpha-core", "confidence": 0.6,
    })
    assert res["ok"] is True
    assert "alpha-core" in ledge["clumps"]
    assert ledge["statuses"]["repo-b"]["clump"] == "alpha-core"
    assert ledge["statuses"]["repo-b"]["status"] == "settled"
    assert ledge["statuses"]["repo-a"]["clump"] == "alpha"


def test_move_repo_to_another_clump_settles_it(isolated_grouping):
    ledge = _ledger()
    res = grouping_store.apply_delta(ledge, {
        "type": "move", "repo": "repo-a", "from": "alpha", "to": "beta",
        "confidence": 0.8,
    })
    assert res["ok"] is True
    assert ledge["statuses"]["repo-a"]["clump"] == "beta"
    assert ledge["statuses"]["repo-a"]["status"] == "settled"


def test_move_repo_to_unplaced_marks_unsettled(isolated_grouping):
    ledge = _ledger()
    res = grouping_store.apply_delta(ledge, {
        "type": "move", "repo": "repo-a", "from": "alpha", "to": "unplaced",
        "confidence": 0.8,
    })
    assert res["ok"] is True
    assert ledge["statuses"]["repo-a"]["status"] == "unsettled"
    assert ledge["statuses"]["repo-a"]["clump"] is None


def test_move_settled_repo_rejected(isolated_grouping):
    ledge = _ledger()
    res = grouping_store.apply_delta(ledge, {
        "type": "move", "repo": "repo-d", "from": "alpha", "to": "beta",
    })
    assert res["ok"] is False
    assert "settled" in res["error"]
    assert ledge["statuses"]["repo-d"]["clump"] == "alpha"


def test_split_settled_repo_rejected(isolated_grouping):
    ledge = _ledger()
    res = grouping_store.apply_delta(ledge, {
        "type": "split", "cluster": "alpha", "members": ["repo-d"],
        "new_name": "nope",
    })
    assert res["ok"] is False
    assert "settled" in res["error"]


def test_rename_clump(isolated_grouping):
    ledge = _ledger()
    res = grouping_store.apply_delta(ledge, {
        "type": "rename", "cluster": "alpha", "new_name": "my ideal project",
    })
    assert res["ok"] is True
    assert ledge["clumps"]["alpha"]["name"] == "my ideal project"


def test_validate_deltas_drops_bad_and_coerces_confidence():
    clumps = {"alpha", "beta"}
    repos = {"repo-a", "repo-b", "repo-c"}
    items = [
        {"type": "merge", "a": "alpha", "b": "beta", "new_name": "x", "confidence": 0.9},
        {"type": "merge", "a": "alpha", "b": "nope", "new_name": "y"},       # bad clump
        {"type": "move", "repo": "repo-a", "from": "alpha", "to": "beta", "confidence": "0.4"},
        {"type": "rename", "cluster": "beta", "new_name": "renamed"},
        {"type": "bogus"},
    ]
    out = _validate_deltas(items, clumps, repos)
    kinds = [(d["type"], d["confidence"]) for d in out]
    assert kinds == [("merge", 0.9), ("move", 0.4), ("rename", None)]


def test_build_delta_prompt_separates_frozen_from_actionable():
    records = [
        {"name": "repo-a", "purpose": "p", "entities": [], "domain": "d"},
        {"name": "repo-d", "purpose": "p", "entities": [], "domain": "d"},  # settled
        {"name": "repo-e", "purpose": "p", "entities": [], "domain": "d"},
    ]
    prompt = _build_delta_prompt(records, _ledger())
    assert "FROZEN" in prompt
    assert "repo-d -> alpha" in prompt
    # settled repo must NOT appear in the actionable table
    actionable = prompt.split("ACTIONABLE")[1]
    assert "repo-d" not in actionable
    assert "repo-a" in actionable
    assert "repo-e" in actionable
