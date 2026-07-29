"""absorb service + router: history-preserving git runbook per (hub, repo).

The Absorb flow's only contract is:
  * a deterministic git runbook that moves the source repo's content into a
    subdirectory of the hub with full history preserved (`git subtree add`),
  * the app never runs git itself — the runbook is text the user executes,
  * the result is cached per (hub, repo), invalidating on input change.

Tests cover the rule-built plan shape (subtree sequence, history preservation,
module naming), the URL parser, the cache hit path on second call, the 404
guards on the router, and that the LLM-on-failure path leaves the rule plan
intact.
"""
import asyncio
import json

from conftest import insert_scan


# --- service --------------------------------------------------------------

def test_slug_and_module():
    from services import absorb
    assert absorb.slug("FFXIV-Scraping") == "ffxiv-scraping"
    assert absorb._module_for("AllaganTools", None) == "allagantools"
    assert absorb._module_for("AllaganTools", "ffxiv_data") == "ffxiv-data"


def test_parse_github_https_and_ssh_and_unknown():
    from services import absorb
    assert absorb._parse_github("https://github.com/StuartJAtkinson/AllaganTools") \
        == ("github.com", "StuartJAtkinson", "AllaganTools")
    assert absorb._parse_github("https://github.com/StuartJAtkinson/AllaganTools.git") \
        == ("github.com", "StuartJAtkinson", "AllaganTools")
    assert absorb._parse_github("git@github.com:StuartJAtkinson/AllaganTools.git") \
        == ("github.com", "StuartJAtkinson", "AllaganTools")
    assert absorb._parse_github("https://gitlab.com/foo/bar") == ("gitlab.com", "foo", "bar")
    assert absorb._parse_github("not a url") is None
    assert absorb._parse_github("") is None


def test_canonical_remote_is_https():
    from services import absorb
    assert absorb._canonical_remote("github.com", "x", "y") == "https://github.com/x/y.git"


def test_rule_plan_uses_subtree_and_preserves_history():
    """The canonical Absorb runbook: `git subtree add --prefix=modules/<name>`
    with no `--squash` — full history preserved."""
    from services import absorb
    out = absorb._rule_plan(
        "game-hub", "https://github.com/StuartJAtkinson/AllaganTools.git",
        repo="AllaganTools", module="allagantools",
        target_branch="main", source_branch=None, strategy="subtree",
    )
    cmds = out["commands"]
    assert any("git subtree add --prefix=modules/allagantools" in c and
               "absorb-source main" in c for c in cmds), cmds
    assert any(c.startswith("# ") for c in cmds), "runbook must be self-documenting"
    joined = "\n".join(cmds)
    assert "--squash" not in joined, "must NOT squash — history is preserved"
    assert "git remote add absorb-source" in joined
    assert "git remote remove absorb-source" in joined
    assert out["strategy"] == "subtree"
    assert out["source_branch"] == "main"          # default assumed when not given
    assert out["module"] == "allagantools"
    assert out["remote"] == "https://github.com/StuartJAtkinson/AllaganTools.git"


def test_rule_plan_honours_source_branch_override():
    from services import absorb
    out = absorb._rule_plan(
        "code-suite", "https://github.com/x/y.git",
        repo="y", module="y", target_branch="main", source_branch="master", strategy="subtree",
    )
    assert out["source_branch"] == "master"
    joined = "\n".join(out["commands"])
    assert "absorb-source master" in joined


def test_post_checklist_names_hub_and_repo():
    from services import absorb
    steps = absorb._post_checklist("game-hub", "AllaganTools", "allagantools", "main")
    assert any("AllaganTools" in s for s in steps)
    assert any("game-hub" in s for s in steps)
    assert any("Archive AllaganTools" in s for s in steps)
    assert any("Mark AllaganTools absorbed" in s for s in steps)


def test_plan_for_works_without_llm(monkeypatch):
    from services import absorb, llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)
    out = asyncio.run(absorb.plan_for(
        "game-hub", "https://github.com/x/AllaganTools.git",
        repo="AllaganTools", repo_meta={"language": "C#", "topics": ["ffxiv"]},
    ))
    assert out["source"] == "rule"
    assert out["module"] == "allagantools"
    assert any("git subtree add" in c for c in out["commands"])
    assert out["checklist"]


def test_plan_for_llm_failure_falls_back_to_rule(monkeypatch):
    """LLM is configured but the call fails — we must still return a usable
    rule-built plan (advisory layer never replaces the safety-critical commands)."""
    from services import absorb, llm

    async def boom(*a, **k):
        raise RuntimeError("simulated outage")
    monkeypatch.setattr(llm, "has_provider", lambda: True)
    monkeypatch.setattr(llm, "complete", boom)

    out = asyncio.run(absorb.plan_for(
        "game-hub", "https://github.com/x/AllaganTools.git",
        repo="AllaganTools", repo_meta={"language": "C#", "topics": []},
    ))
    assert out["source"] == "rule"
    assert any("git subtree add" in c for c in out["commands"])


def test_plan_for_llm_advice_layered_not_replacing(monkeypatch):
    """LLM succeeds — its branch hint + warnings appear as *notes*, never as
    replacement commands. The git sequence is still rule-built."""
    from services import absorb, llm

    async def fake_complete(prompt, max_tokens=400):
        return "1. BRANCH: master is the right default branch for this repo.\n\n" \
               "2. WARNINGS:\n" \
               "- The repo has a top-level modules/ folder already; expect a path conflict.\n" \
               "- History is unusually shallow (one commit)."
    monkeypatch.setattr(llm, "has_provider", lambda: True)
    monkeypatch.setattr(llm, "complete", fake_complete)

    out = asyncio.run(absorb.plan_for(
        "game-hub", "https://github.com/x/AllaganTools.git",
        repo="AllaganTools", repo_meta={"language": "C#", "topics": []},
    ))
    assert out["source"] == "llm+rule"
    assert any("git subtree add" in c for c in out["commands"])        # unchanged
    notes = " ".join(out["notes"])
    assert "branch" in notes.lower()                                    # branch note present
    assert "modules/" in notes or "path conflict" in notes              # warning surfaced


def test_unknown_source_url_still_produces_runbook():
    """Non-GitHub remote URL → the rule plan still produces a subtree add
    using the literal URL (git subtree add works with any remote git URL)."""
    from services import absorb
    out = absorb._rule_plan(
        "code-suite", "https://git.example.com/foo/bar.git",
        repo="bar", module="bar", target_branch="main",
        source_branch=None, strategy="subtree",
    )
    assert any("https://git.example.com/foo/bar.git" in c for c in out["commands"])


# --- router ---------------------------------------------------------------

def test_gen_plan_404_unknown_hub(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        r = c.post("/api/absorb/plan/s1", json={
            "hub": "no-such-hub", "repo": "quivr",
            "source_url": "https://github.com/x/quivr.git",
        })
    assert r.status_code == 404


def test_gen_plan_404_non_absorb_repo(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app
    insert_scan(temp_db, repos=[{"name": "loose-repo"}])
    with TestClient(app) as c:
        r = c.post("/api/absorb/plan/s1", json={
            "hub": "personal-ai-os", "repo": "loose-repo",
            "source_url": "https://github.com/x/loose-repo.git",
        })
    assert r.status_code == 404


def test_gen_plan_400_missing_source_url(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        r = c.post("/api/absorb/plan/s1", json={
            "hub": "personal-ai-os", "repo": "quivr", "source_url": "",
        })
    assert r.status_code == 400


def test_gen_plan_400_bad_strategy(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        r = c.post("/api/absorb/plan/s1", json={
            "hub": "personal-ai-os", "repo": "quivr",
            "source_url": "https://github.com/x/quivr.git",
            "strategy": "warp-drive",
        })
    assert r.status_code == 400


def test_gen_plan_returns_subtree_runbook_and_caches(temp_db, isolated_plan, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from services import llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)

    insert_scan(temp_db, repos=[{"name": "quivr", "language": "Python"}])
    body = {"hub": "personal-ai-os", "repo": "quivr",
            "source_url": "https://github.com/StuartJAtkinson/quivr.git"}
    with TestClient(app) as c:
        first = c.post("/api/absorb/plan/s1", json=body).json()
        second = c.post("/api/absorb/plan/s1", json=body).json()

    # rule-built plan shape
    assert first["source"] == "rule"
    assert first["module"] == "quivr"
    assert first["strategy"] == "subtree"
    assert any("git subtree add --prefix=modules/quivr" in c for c in first["commands"])
    assert any("absorb-source main" in c for c in first["commands"])
    assert any("Archive quivr" in s for s in first["checklist"])
    assert any("Mark quivr absorbed" in s for s in first["checklist"])

    # second call served from the absorb_plan cache, not regenerated
    assert second.get("cached") is True
    assert second["commands"] == first["commands"]


def test_gen_plan_regenerate_bypasses_cache(temp_db, isolated_plan, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from services import llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        c.post("/api/absorb/plan/s1", json={
            "hub": "personal-ai-os", "repo": "quivr",
            "source_url": "https://github.com/x/quivr.git",
        })
        r = c.post("/api/absorb/plan/s1", json={
            "hub": "personal-ai-os", "repo": "quivr",
            "source_url": "https://github.com/x/quivr.git",
            "regenerate": True,
        }).json()
    assert r.get("cached") is False


def test_get_plan_404_when_uncached(temp_db, isolated_plan):
    from fastapi.testclient import TestClient
    from main import app
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        r = c.get("/api/absorb/plan/personal-ai-os/quivr/s1")
    assert r.status_code == 404


def test_get_plan_returns_cached(temp_db, isolated_plan, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from services import llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    with TestClient(app) as c:
        c.post("/api/absorb/plan/s1", json={
            "hub": "personal-ai-os", "repo": "quivr",
            "source_url": "https://github.com/x/quivr.git",
        })
        r = c.get("/api/absorb/plan/personal-ai-os/quivr/s1").json()
    assert r["hub"] == "personal-ai-os"
    assert r["repo"] == "quivr"
    assert r.get("cached") is True
    assert any("git subtree add" in c for c in r["commands"])


def test_cache_key_changes_on_branch_override(temp_db, isolated_plan, monkeypatch):
    """Different source_branch → cache miss → regenerated. Same repo + URL
    must not poison the cache for a different branch hint."""
    from routers import absorb as absorb_router
    base = {"source_url": "u", "target_branch": "main", "module": "r", "strategy": "subtree"}
    a = absorb_router._cache_key("h", "r", {**base, "source_branch": None})
    b = absorb_router._cache_key("h", "r", {**base, "source_branch": "master"})
    assert a != b


# --- ponytail self-check (mirror promote.py) -----------------------------

def test_self_check_runs():
    """The same self-check the maintainer script runs — keeps absorb.py
    honest against its own contract."""
    import subprocess, sys
    out = subprocess.run(
        [sys.executable, "-m", "services.absorb"], capture_output=True, text=True,
        cwd=".",  # pytest is run with ui/backend as cwd
    )
    assert out.returncode == 0, out.stderr
    assert "self-check OK" in out.stdout, out.stdout