"""reconcile stub assessment heuristic."""
from routers.reconcile import _stub_reason


def test_repo_with_signal_is_not_stub():
    assert _stub_reason({"size": 5, "stars": 0, "aim": "does a real thing", "topics": []}) is None
    assert _stub_reason({"size": 5, "stars": 3, "aim": "", "topics": []}) is None
    assert _stub_reason({"size": 5, "stars": 0, "aim": "", "topics": ["x"]}) is None


def test_low_signal_repo_is_stub():
    r = {"size": 8, "stars": 0, "aim": "", "topics": [], "is_fork": False}
    reason = _stub_reason(r)
    assert reason and "likely stub" in reason
    assert "no description" in reason


def test_stub_reason_notes_fork():
    r = {"size": 20, "stars": 0, "aim": "", "topics": [], "is_fork": True}
    assert "fork" in _stub_reason(r)
