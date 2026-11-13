"""
mcp_server.py — the MCP (Model Context Protocol) server for operating the
grouping ledger. stdio transport; an agent (Claude Code, opencode, etc.) drives
the semantic grouping loop through tools/resources, backed directly by the same
service layer the FastAPI routers use — this file holds no grouping logic.

Run (from ui/backend, same GIT_SUITE_HOME as the app):

    python -m mcp_server

Surface (see GROUPING.md for the method):

    resources  gitsuite://ledger, gitsuite://summary, gitsuite://clumps/{slug}
    tools      propose_next, apply_delta, answer_question, set_floor, settle
"""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

import grouping_store
from services import topic_llm

server = MCPServer(
    name="git-suite",
    title="git-suite grouping",
    version="0.1.0",
    description=(
        "Operate git-suite's semantic grouping: propose merge/split/move/rename "
        "deltas over the durable ledger, approve them, answer the LLM's "
        "clarifying questions, and read the resumable per-repo status."
    ),
    instructions=(
        "The workflow is: read gitsuite://summary, call propose_next, review the "
        "deltas (auto-approving those at or above the floor, surfacing the rest "
        "and any questions to the user), then apply_delta for each approved "
        "change. Repeat until propose_next returns no deltas and no questions."
    ),
)


# ── resources ───────────────────────────────────────────────────────────────

@server.resource("gitsuite://ledger", description="Full grouping ledger: per-repo status, clumps, pending deltas, answers.")
def read_ledger() -> str:
    return json.dumps(grouping_store.load(), ensure_ascii=False, indent=2)


@server.resource("gitsuite://summary", description="Traffic-light rollup: counts, clump count, round, floor.")
def read_summary() -> str:
    return json.dumps(grouping_store.summary(), ensure_ascii=False, indent=2)


@server.resource("gitsuite://clumps/{slug}", description="One clump: name/description/confidence plus its member repos.")
def read_clump(slug: str) -> str:
    ledger = grouping_store.load()
    clump = ledger["clumps"].get(slug)
    if clump is None:
        return json.dumps({"error": f"unknown clump {slug!r}"})
    members = grouping_store.members_of(ledger, slug)
    return json.dumps({"slug": slug, **clump, "members": members},
                      ensure_ascii=False, indent=2)


# ── tools ───────────────────────────────────────────────────────────────────

@server.tool(description="Ask the LLM for targeted refinement deltas over the ledger. Writes them to the pending list and returns them with any clarifying questions.")
async def propose_next(session_id: str) -> dict:
    from routers.cluster import _distilled_records
    ledger = grouping_store.load()
    records = await _distilled_records(session_id)
    deltas, questions = await topic_llm.propose_deltas(records, ledger, ledger.get("answers"))
    for i, d in enumerate(deltas):
        d["id"] = f"d{i}"
    ledger["pending"] = deltas
    grouping_store.save(ledger)
    return {"deltas": deltas, "questions": questions,
            "summary": grouping_store.summary(ledger)}


@server.tool(description="Approve (commit) or reject one pending delta. Approving settles the repos it places; edits override fields (e.g. new_name).")
def apply_delta(delta_id: str, approve: bool = True, edits: dict | None = None) -> dict:
    ledger = grouping_store.load()
    pending = ledger.get("pending") or []
    delta = next((d for d in pending if d.get("id") == delta_id), None)
    if delta is None:
        return {"ok": False, "error": "unknown delta id"}
    ledger["pending"] = [d for d in pending if d.get("id") != delta_id]
    if not approve:
        grouping_store.save(ledger)
        return {"ok": True, "applied": False, "summary": grouping_store.summary(ledger)}
    if edits:
        delta = {**delta, **edits}
    res = grouping_store.apply_delta(ledger, delta)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error")}
    grouping_store.save(ledger)
    return {"ok": True, "applied": True, "changed": res.get("changed", []),
            "summary": grouping_store.summary(ledger)}


@server.tool(description="Record the user's answer to a clarifying question, so the next propose_next uses it as steering context.")
def answer_question(question: str, answer: str) -> dict:
    ledger = grouping_store.load()
    ledger.setdefault("answers", []).append({"question": question, "answer": answer})
    grouping_store.save(ledger)
    return {"ok": True, "answers": ledger["answers"]}


@server.tool(description="Set the confidence floor. Deltas at/above it are safe to auto-approve; only below-floor deltas and questions need the human.")
def set_floor(floor: float) -> dict:
    ledger = grouping_store.load()
    ledger["floor"] = float(floor)
    grouping_store.save(ledger)
    return {"ok": True, "floor": ledger["floor"]}


@server.tool(description="Force a repo's mark: settle it into a clump, or unplace it (clump=None). Overrides the LLM's placement.")
def settle(repo: str, clump: str | None = None) -> dict:
    ledger = grouping_store.load()
    if repo not in ledger["statuses"]:
        return {"ok": False, "error": f"unknown repo {repo!r}"}
    if clump and clump not in ledger["clumps"]:
        return {"ok": False, "error": f"unknown clump {clump!r}"}
    if clump:
        ledger["statuses"][repo] = {"status": "settled", "clump": clump,
                                    "confidence": None, "why": "manual"}
    else:
        ledger["statuses"][repo] = {"status": "unsettled", "clump": None,
                                    "confidence": None, "why": "manual"}
    grouping_store.save(ledger)
    return {"ok": True, "summary": grouping_store.summary(ledger)}


if __name__ == "__main__":
    server.run(transport="stdio")
