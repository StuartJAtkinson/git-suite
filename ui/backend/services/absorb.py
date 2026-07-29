"""
absorb.py — the Absorb flow: move a repo's content into a hub with history preserved.

ROADMAP Phase 2: "Absorb flow: move a repo's *content* into a hub with history
preserved — still manual (git detach checklist); no automated transfer/rename."

git-suite never runs git itself. It produces the exact runbook the user runs
locally: a sequence of `git subtree add` invocations (the canonical git-native
mechanism for absorbing an external codebase into a subdirectory while keeping
every commit, author, and timestamp intact), one verification step, and a
follow-up checklist.

The plan is deterministic by default — pure function of (hub, repo, source URL,
target branch). An optional LLM pass can suggest a non-default source branch or
flag a likely file/path collision, falling back to the rule-built plan on any
failure.

Public surface:

  plan_for(hub, source_url, *, repo, module=None, target_branch="main",
           source_branch=None, strategy="subtree")
      -> { commands, notes, strategy, source_branch, target_branch, module, source }

  checklist_for(hub, source_url, *, repo, module=None, target_branch="main")
      -> { steps, source }

The plan is the *runbook*; the checklist is the *post-merge to-do list* (update
README, archive source, mark absorbed, etc.) — both are useful, both belong in
the cache row.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

log = logging.getLogger(__name__)


# --- naming ---------------------------------------------------------------

def slug(name: str) -> str:
    """Mirror migration.slug() so module paths line up across the two features."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _module_for(repo: str, override: str | None) -> str:
    return slug(override) if override else slug(repo)


def _parse_github(source_url: str) -> tuple[str, str, str] | None:
    """For a GitHub source URL return (host, owner, repo); else None.

    Accepts both https and git forms. The host is the canonical origin (so
    `git@github.com:...` and `https://github.com/...` normalise to the same
    fetch URL)."""
    if not source_url:
        return None
    raw = source_url.strip()
    if raw.startswith("git@"):
        # git@github.com:owner/repo(.git)
        m = re.match(r"git@([^:]+):([^/]+)/(.+?)(?:\.git)?$", raw)
        if not m:
            return None
        return m.group(1), m.group(2), m.group(3)
    try:
        u = urlparse(raw if "://" in raw else f"https://{raw}")
    except ValueError:
        return None
    if not u.netloc or u.netloc == "github.com":
        host = "github.com"
    else:
        host = u.netloc
    parts = [p for p in u.path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    return host, parts[0], parts[1].removesuffix(".git")


def _canonical_remote(host: str, owner: str, repo: str) -> str:
    if host in ("github.com", "ssh.github.com"):
        return f"https://{host}/{owner}/{repo}.git"
    return f"https://{host}/{owner}/{repo}.git"


# --- strategy -------------------------------------------------------------

def _strategy_default(repo: dict | None) -> str:
    """`subtree` is the canonical history-preserving absorb — single import,
    full commit graph, clean authorship. `join` is the no-squash merger that
    grafts histories at root (use only if the user wants the source's commits
    at the hub root rather than under modules/<repo>/)."""
    return "subtree"


# --- rule-built absorb plan ----------------------------------------------

def _rule_plan(hub: str, source_url: str, *, repo: str, module: str,
               target_branch: str, source_branch: str | None,
               strategy: str) -> dict:
    parsed = _parse_github(source_url)
    if parsed:
        host, owner, name = parsed
        remote = _canonical_remote(host, owner, name)
        origin_pretty = f"{owner}/{name}"
    else:
        # Not a recognisable GitHub URL — fall back to a literal remote. The
        # `git subtree add` command still works for non-GitHub remotes.
        remote = source_url
        origin_pretty = source_url

    branch = source_branch or "main"
    subtree_path = f"modules/{module}"
    squash_flag = ""                                # never squash — history preserved
    strategy_note = (
        "Subtree preserves the source repo's full history (every commit, author, "
        "timestamp) under a single squashed merge commit in the hub."
        if strategy == "subtree" else
        "Join grafts both histories at the hub root with no squash — every "
        "source commit becomes a separate commit in the hub. History is "
        "preserved but the log is verbose."
    )

    commands = [
        f"# Absorb {origin_pretty} into {hub} under {subtree_path}/",
        f"# (history preserved; this is the canonical Absorb flow)",
        "",
        f"# 1. Clone the hub locally (or `cd` into an existing clone).",
        f"git clone https://github.com/<you>/{hub}.git",
        f"cd {hub}",
        "",
        f"# 2. Confirm a clean tree on the branch you want to absorb into.",
        f"git checkout {target_branch}",
        f"git status                          # expect: nothing to commit, working tree clean",
        f"git pull --ff-only                  # bring the hub up to date",
        "",
        f"# 3. Add the source repo as a temporary remote.",
        f"git remote add absorb-source {remote}",
        f"git fetch absorb-source {branch}",
        "",
        f"# 4. Absorb the source into a subdirectory, preserving history.",
        f"git subtree add --prefix={subtree_path}{squash_flag} absorb-source {branch}",
        "",
        f"# 5. Drop the temporary remote.",
        f"git remote remove absorb-source",
        "",
        f"# 6. Verify the history landed under the prefix.",
        f"git log --oneline -- {subtree_path}/ | head",
        f"git log --follow -- README.md       # any file from the source still traces back",
        "",
        f"# 7. Push the merge back to the hub.",
        f"git push origin {target_branch}",
    ]
    notes = [
        f"Strategy: {strategy} — {strategy_note}",
        f"Source branch assumed `{branch}`; pass `source_branch` if the repo's default is different (e.g. `master`).",
        f"Subdirectory `{subtree_path}/` lines up with the per-absorb scaffold the migration checklist uses.",
        f"Use `--squash` only if you don't want the source's history in the hub's log — adding it collapses N commits into one and you lose attribution.",
    ]
    return {
        "commands": commands,
        "notes": notes,
        "strategy": strategy,
        "source_branch": branch,
        "target_branch": target_branch,
        "module": module,
        "remote": remote,
        "source": "rule",
    }


# --- LLM-enhanced plan (optional) ----------------------------------------

async def _llm_plan(hub: str, source_url: str, *, repo: str, module: str,
                    target_branch: str, source_branch: str | None,
                    repo_meta: dict | None) -> dict | None:
    """Ask the LLM for two things: (a) is `main` the right source branch, and
    (b) any obvious path/name collisions to warn about. Returns a notes patch
    or None on failure. The git command sequence stays rule-built — LLM touches
    the notes only, never the commands themselves (safety)."""
    from services import llm
    if not llm.has_provider():
        return None
    meta = repo_meta or {}
    try:
        prompt = f"""You are reviewing an Absorb plan: the user wants to move the
contents of `{repo}` into the hub `{hub}` under `modules/{module}/`, preserving
full git history via `git subtree add`.

Source URL: {source_url}
Hub default branch (target): {target_branch}
Source default branch (assumed): {source_branch or 'main'}
Repo language: {meta.get('language') or 'unknown'}
Repo description: {meta.get('aim') or '(none)'}
Repo topics: {', '.join(meta.get('topics') or []) or 'none'}

Answer two things, in plain text:

1. BRANCH: is `main` likely the right source branch for `{repo}`, or should
the user pass something else (e.g. `master`, `develop`)? One sentence.

2. WARNINGS: any likely collision or gotcha to flag — e.g. a `modules/` folder
already in the source, a language-name collision with an existing
`modules/<existing-repo>/`, an unusually shallow history, a binary-heavy repo.
Zero or more short bullets.

Do NOT write code or commands — keep this advisory only."""
        text = await llm.complete(prompt, max_tokens=400)
        if not text:
            return None
        return {"branch_note": _first_line(text), "warnings": _bullet_lines(text)}
    except Exception as exc:
        log.warning("LLM absorb plan failed for %s: %s", repo, exc)
        return None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.lower().startswith(("answer", "1.", "2.")):
            return line
        if line and line[0].isdigit() and "." in line[:3]:
            return line.split(".", 1)[1].strip()
    return ""


def _bullet_lines(text: str) -> list[str]:
    """Pull the WARNING bullets out of the LLM reply — anything after the
    second `2.` heading that starts with `-`, `*`, or `•`."""
    out: list[str] = []
    in_warn = False
    for raw in text.splitlines():
        s = raw.strip()
        if not in_warn and (s.startswith("2.") or s.lower().startswith("warnings")):
            in_warn = True
            continue
        if in_warn:
            if s.startswith(("-", "*", "•")):
                out.append(s.lstrip("-*• ").strip())
            elif not s:
                continue
            elif s[0].isdigit():                 # rolled into next numbered section
                break
    return out


# --- post-merge checklist (separate from the git runbook) ---------------

def _post_checklist(hub: str, repo: str, module: str, target_branch: str) -> list[str]:
    return [
        f"Confirm the new subtree at modules/{module}/ builds/tests locally in {hub}.",
        f"Wire {repo}'s entrypoint into {hub}'s API/CLI surface if needed.",
        f"Update {hub}'s README to list {repo} as an absorbed member; push.",
        f"Archive {repo} on GitHub (Settings → Archive).",
        f"Mark {repo} absorbed in git-suite via Execute → 'Finish absorbs' → 'Mark absorbed'.",
        f"Optional: `git remote remove origin` inside any local clone of {repo} and `git remote add origin` to {hub}.",
        f"Push the absorb to {target_branch} (`git push origin {target_branch}`) — already in the runbook, but re-check after the merge.",
    ]


# --- public surface ------------------------------------------------------

async def plan_for(hub: str, source_url: str, *, repo: str, module: str | None = None,
                   target_branch: str = "main", source_branch: str | None = None,
                   strategy: str | None = None, repo_meta: dict | None = None) -> dict:
    """Build the absorb plan. Always returns a usable runbook; LLM may layer
    advisory notes on top, never replaces the rule-built commands."""
    mod = _module_for(repo, module)
    strat = strategy or _strategy_default(repo_meta)
    base = _rule_plan(hub, source_url, repo=repo, module=mod,
                      target_branch=target_branch, source_branch=source_branch,
                      strategy=strat)
    advisory = await _llm_plan(hub, source_url, repo=repo, module=mod,
                               target_branch=target_branch,
                               source_branch=source_branch, repo_meta=repo_meta)
    if advisory:
        if advisory.get("branch_note"):
            base["notes"].append(f"LLM check — branch: {advisory['branch_note']}")
        for w in advisory.get("warnings") or []:
            base["notes"].append(f"LLM check — warning: {w}")
        base["source"] = "llm+rule"
    base["checklist"] = _post_checklist(hub, repo, mod, target_branch)
    return base


def checklist_for(hub: str, source_url: str, *, repo: str, module: str | None = None,
                  target_branch: str = "main") -> dict:
    """Sync helper — same module/target-branch naming, just the post-merge steps."""
    mod = _module_for(repo, module)
    return {"steps": _post_checklist(hub, repo, mod, target_branch), "source": "rule"}


if __name__ == "__main__":
    # ponytail: smallest self-check — the rule plan names the source/hub, lays
    # out the canonical subtree-add sequence, and never claims to have run git.
    # Force the rule-only path (no LLM reach-out during the self-check).
    from services import llm as _llm
    _llm._config = lambda: {}        # noqa: SLF001 — self-check bypass
    import asyncio, json
    out = asyncio.run(plan_for(
        "game-hub", "https://github.com/x/AllaganTools.git",
        repo="AllaganTools", repo_meta={"language": "C#", "aim": "FFXIV data tool"},
    ))
    assert any("git subtree add" in c for c in out["commands"]), out["commands"]
    assert any("modules/allagantools" in n for n in out["notes"]), out["notes"]
    assert "--squash" not in " ".join(out["commands"]), "must preserve history"
    assert any("Archive AllaganTools" in s for s in out["checklist"]), out["checklist"]
    assert out["module"] == "allagantools"
    print("absorb.py self-check OK")
    print(json.dumps(out, indent=2)[:600], "…")