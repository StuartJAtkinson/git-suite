"""MCP server: tools/resources are thin adapters over grouping_store + topic_llm."""
import asyncio
import json

import grouping_store
import mcp_server
from services import topic_llm


def _call(name, args):
    r = asyncio.run(mcp_server.server.call_tool(name, args))
    assert not r.is_error, getattr(r, "content", None)
    return json.loads(r.content[0].text)


def _read(uri):
    items = list(asyncio.run(mcp_server.server.read_resource(uri)))
    return json.loads(items[0].content)


def _seed(isolated_grouping):
    ledger = {
        "statuses": {
            "repo-a": {"status": "proposed", "clump": "alpha", "confidence": 0.8, "why": ""},
            "repo-b": {"status": "proposed", "clump": "alpha", "confidence": 0.8, "why": ""},
            "repo-c": {"status": "proposed", "clump": "beta", "confidence": 0.7, "why": ""},
        },
        "clumps": {
            "alpha": {"name": "alpha", "description": "", "confidence": 0.8},
            "beta": {"name": "beta", "description": "", "confidence": 0.7},
        },
        "answers": [], "pending": [], "round": 0, "floor": 0.85,
    }
    isolated_grouping.save(ledger)
    return ledger


def test_set_floor_tool(isolated_grouping):
    _seed(isolated_grouping)
    assert _call("set_floor", {"floor": 0.6})["ok"] is True
    assert grouping_store.load()["floor"] == 0.6


def test_answer_question_tool(isolated_grouping):
    _seed(isolated_grouping)
    assert _call("answer_question", {"question": "q?", "answer": "a"})["ok"] is True
    assert grouping_store.load()["answers"] == [{"question": "q?", "answer": "a"}]


def test_settle_tool_and_unplace(isolated_grouping):
    _seed(isolated_grouping)
    assert _call("settle", {"repo": "repo-a", "clump": "beta"})["ok"] is True
    assert grouping_store.load()["statuses"]["repo-a"] == {
        "status": "settled", "clump": "beta", "confidence": None, "why": "manual"}
    assert _call("settle", {"repo": "repo-b", "clump": None})["ok"] is True
    assert grouping_store.load()["statuses"]["repo-b"]["status"] == "unsettled"


def test_apply_delta_tool_commits_pending(isolated_grouping):
    ledger = _seed(isolated_grouping)
    ledger["pending"] = [{"id": "d0", "type": "rename", "cluster": "alpha",
                          "new_name": "my ideal", "confidence": 1.0}]
    isolated_grouping.save(ledger)
    out = _call("apply_delta", {"delta_id": "d0", "approve": True})
    assert out["applied"] is True
    assert grouping_store.load()["clumps"]["alpha"]["name"] == "my ideal"
    assert grouping_store.load()["pending"] == []


def test_apply_delta_reject_removes_pending(isolated_grouping):
    ledger = _seed(isolated_grouping)
    ledger["pending"] = [{"id": "d0", "type": "rename", "cluster": "alpha", "new_name": "x"}]
    isolated_grouping.save(ledger)
    out = _call("apply_delta", {"delta_id": "d0", "approve": False})
    assert out["applied"] is False
    assert grouping_store.load()["pending"] == []


def test_apply_delta_unknown_id_returns_error(isolated_grouping):
    _seed(isolated_grouping)
    out = _call("apply_delta", {"delta_id": "nope"})
    assert out["ok"] is False
    assert out["error"] == "unknown delta id"


def test_read_ledger_resource(isolated_grouping):
    _seed(isolated_grouping)
    data = _read("gitsuite://ledger")
    assert "repo-a" in data["statuses"]
    assert data["clumps"]["alpha"]["name"] == "alpha"


def test_read_summary_resource(isolated_grouping):
    _seed(isolated_grouping)
    data = _read("gitsuite://summary")
    assert data["clumps"] == 2
    assert data["counts"]["proposed"] == 3


def test_read_clump_resource(isolated_grouping):
    _seed(isolated_grouping)
    data = _read("gitsuite://clumps/alpha")
    assert data["slug"] == "alpha"
    assert set(data["members"]) == {"repo-a", "repo-b"}


def test_propose_next_tool(monkeypatch, isolated_grouping):
    _seed(isolated_grouping)

    async def fake_records(session_id):
        return [{"name": "repo-a", "purpose": "p", "entities": [], "domain": "d"}]

    async def fake_propose(records, ledger, answers=None):
        return ([{"type": "merge", "a": "alpha", "b": "beta", "new_name": "x",
                  "confidence": 0.9}], [])

    import routers.cluster as cluster_mod
    monkeypatch.setattr(cluster_mod, "_distilled_records", fake_records)
    monkeypatch.setattr(topic_llm, "propose_deltas", fake_propose)

    out = _call("propose_next", {"session_id": "s1"})
    assert out["deltas"][0]["id"] == "d0"
    assert grouping_store.load()["pending"][0]["id"] == "d0"
