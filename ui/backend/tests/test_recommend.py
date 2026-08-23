"""Step 6 — recommend router tests.

The /api/recommend/{sid}/{repo} endpoint serves a cached best-hub-for-this-repo
recommendation, computing on first miss. Signal precedence: user Notes override
the LLM-distilled record. Hallucinated target_hubs are dropped.

LLM is mocked by patching `services.llm.complete` — `complete_json` calls it
and parses the result, so we don't need to patch two layers.
"""
import asyncio
import json


def _add_session(temp_db, sid="s1", github_user="tester"):
    async def _go():
        async for db in temp_db.get_db():
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) "
                "VALUES (?,?,?,?)",
                (sid, "tok", github_user, "/tmp"),
            )
            await db.commit()
    asyncio.run(_go())


def _set_note(temp_db, sid, repo, note):
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        c.post(f"/api/scan/notes/{sid}", json={"repo": repo, "note": note})


def _set_distill(temp_db, repo, record):
    async def _go():
        async for db in temp_db.get_db():
            await db.execute(
                "INSERT INTO repo_domain (repo, summary, record, src_hash) "
                "VALUES (?,?,?,?)",
                (repo, record.get("domain", ""), json.dumps(record), "hash"),
            )
            await db.commit()
    asyncio.run(_go())


def _fake_llm(monkeypatch, return_value, *, capture=None):
    """Patch services.llm.complete. Optionally record the prompt into `capture`."""
    from services import llm
    counter = {"n": 0}

    async def fake_complete(prompt, system="", max_tokens=1024):
        counter["n"] += 1
        if capture is not None:
            capture.append({"prompt": prompt, "system": system})
        return json.dumps(return_value)

    monkeypatch.setattr(llm, "complete", fake_complete)
    return counter


def test_recommend_uses_note_over_distill(temp_db, isolated_plan, monkeypatch):
    """A user Note drives the prompt; the LLM never sees the distilled record."""
    from fastapi.testclient import TestClient
    from main import app

    _add_session(temp_db)
    _set_note(temp_db, "s1", "quivr", "personal RAG memory tool")
    _set_distill(temp_db, "quivr", {
        "purpose": "vector store wrapper",
        "domain": "databases",
        "entities": ["vectors", "embeddings"],
    })

    captured = []
    counter = _fake_llm(monkeypatch, {
        "target_hub": "personal-ai-os",
        "feature": "RAG memory persistence",
        "confidence": 0.82,
        "rationale": "Note explicitly names personal RAG.",
    }, capture=captured)

    with TestClient(app) as c:
        r = c.get("/api/recommend/s1/quivr")
    assert r.status_code == 200
    body = r.json()
    assert body["source_repo"] == "quivr"
    assert body["recommendation"]["target_hub"] == "personal-ai-os"
    assert body["recommendation"]["signal"] == "notes"
    assert body["recommendation"]["confidence"] == 0.82
    assert counter["n"] == 1
    assert len(captured) == 1
    assert "USER NOTE: personal RAG memory tool" in captured[0]["prompt"]
    # The distilled record must NOT appear when a note drove it.
    assert "vector store wrapper" not in captured[0]["prompt"]


def test_recommend_falls_back_to_distill_when_no_note(temp_db, isolated_plan, monkeypatch):
    """No user Note → distilled record drives the prompt; signal='distill'."""
    from fastapi.testclient import TestClient
    from main import app

    _add_session(temp_db)
    _set_distill(temp_db, "quivr", {
        "purpose": "vector store wrapper",
        "domain": "databases",
        "entities": ["vectors", "embeddings"],
    })

    captured = []
    counter = _fake_llm(monkeypatch, {
        "target_hub": "personal-ai-os",
        "feature": "vector indexing",
        "confidence": 0.61,
        "rationale": "Distilled domain matches.",
    }, capture=captured)

    with TestClient(app) as c:
        r = c.get("/api/recommend/s1/quivr")
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation"]["signal"] == "distill"
    assert counter["n"] == 1
    assert "DISTILLED:" in captured[0]["prompt"]
    assert "vector store wrapper" in captured[0]["prompt"]
    # Note keyword must not appear when there's no note.
    assert "USER NOTE" not in captured[0]["prompt"]


def test_recommend_returns_none_when_no_signal(temp_db, isolated_plan, monkeypatch):
    """No Note + no distill purpose → no LLM call, recommendation is null."""
    from fastapi.testclient import TestClient
    from main import app

    _add_session(temp_db)
    # no note, no repo_domain row

    counter = _fake_llm(monkeypatch, {
        "target_hub": "personal-ai-os",
        "feature": "x",
        "confidence": 0.5,
        "rationale": "x",
    })

    with TestClient(app) as c:
        r = c.get("/api/recommend/s1/quivr")
    assert r.status_code == 200
    body = r.json()
    assert body == {"source_repo": "quivr", "recommendation": None}
    assert counter["n"] == 0    # LLM never invoked — no signal means no call


def test_recommend_persists_and_caches(temp_db, isolated_plan, monkeypatch):
    """Second call hits the cache — LLM called exactly once across two reads."""
    from fastapi.testclient import TestClient
    from main import app

    _add_session(temp_db)
    _set_note(temp_db, "s1", "quivr", "personal RAG memory")

    counter = _fake_llm(monkeypatch, {
        "target_hub": "personal-ai-os",
        "feature": "RAG memory",
        "confidence": 0.88,
        "rationale": "matches",
    })

    with TestClient(app) as c:
        r1 = c.get("/api/recommend/s1/quivr").json()
        r2 = c.get("/api/recommend/s1/quivr").json()
    assert r1 == r2
    assert counter["n"] == 1    # cached — second call did NOT re-invoke the LLM


def test_recommend_drops_hallucinated_hub(temp_db, isolated_plan, monkeypatch):
    """LLM picks a hub not in plan['hubs'] → drop, don't persist garbage."""
    from fastapi.testclient import TestClient
    from main import app

    _add_session(temp_db)
    _set_note(temp_db, "s1", "quivr", "personal RAG")

    counter = _fake_llm(monkeypatch, {
        "target_hub": "nonexistent-hub",
        "feature": "RAG",
        "confidence": 0.9,
        "rationale": "x",
    })

    with TestClient(app) as c:
        r = c.get("/api/recommend/s1/quivr")
    body = r.json()
    assert body["recommendation"] is None
    assert counter["n"] == 1    # we DID ask the LLM, just rejected the answer

    # No row persisted in the cache (next call would still hit the LLM).
    async def _check():
        async for db in temp_db.get_db():
            rows = await db.execute_fetchall(
                "SELECT * FROM feature_recommendations WHERE session_id='s1'"
            )
        return rows
    assert asyncio.run(_check()) == []


def test_set_note_invalidates_recommendation(temp_db, isolated_plan, monkeypatch):
    """Writing a new Note drops the cached recommendation so the next read
    recomputes with the new signal. Two LLM invocations total: first seeds,
    second re-seeds after invalidation."""
    from fastapi.testclient import TestClient
    from main import app

    _add_session(temp_db)
    _set_distill(temp_db, "quivr", {"purpose": "x", "domain": "y", "entities": []})

    counter = _fake_llm(monkeypatch, {
        "target_hub": "personal-ai-os",
        "feature": "x",
        "confidence": 0.6,
        "rationale": "x",
    })

    with TestClient(app) as c:
        # 1st call: seed (signal=distill)
        r1 = c.get("/api/recommend/s1/quivr").json()
        assert r1["recommendation"]["signal"] == "distill"

        # 2nd: write a new note — invalidates the cache
        c.post("/api/scan/notes/s1", json={"repo": "quivr", "note": "personal RAG"})

        # 3rd: re-read — must recompute (signal=notes now)
        r2 = c.get("/api/recommend/s1/quivr").json()
        assert r2["recommendation"]["signal"] == "notes"

    assert counter["n"] == 2    # one before, one after the note change