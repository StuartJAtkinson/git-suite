"""
plan_store.py — the single source of truth for the portfolio plan.

Design philosophy #1: the plan is *data*, not code. The hardcoded dicts in
plan.py are now only the SEED. At runtime the canonical plan lives in one
editable JSON document (~/.git-suite/plan.json) that the web UI, the CLI and
the README generator all read and write. Every other module derives from here.

Shape of the canonical plan:

    {
      "hubs": {
        "<hub>": {
          "layer": int, "priority": int, "description": str,
          "absorbs": [repo, ...],
          "alternatives": {"oss": [...], "commercial": [...]}
        }
      },
      "archives": { "<repo>": "<hub|null>" },
      "keeps":    [repo, ...],
      "layer_names": { "<int>": str }
    }
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

import plan as seed  # the immutable defaults

log = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".git-suite"
_PLAN_FILE = _CONFIG_DIR / "plan.json"
_LOCK = threading.Lock()

VERDICTS = {"absorb", "archive", "keep", "orphan"}


def _seed_plan() -> dict:
    """Build the default plan document from plan.py constants."""
    return {
        "hubs": {
            name: {
                "layer": meta["layer"],
                "priority": meta["priority"],
                "description": meta["description"],
                "absorbs": list(seed.HUB_ABSORBS.get(name, [])),
                "alternatives": seed.HUB_ALTERNATIVES.get(name, {"oss": [], "commercial": []}),
            }
            for name, meta in seed.HUB_META.items()
        },
        "archives": dict(seed.ARCHIVE_HUB),
        "keeps": sorted(seed.KEEP_AS_IS),
        "layer_names": {str(k): v for k, v in seed.LAYER_NAMES.items()},
    }


def _load() -> dict:
    """Load the canonical plan, seeding the file on first run."""
    try:
        if _PLAN_FILE.exists():
            return json.loads(_PLAN_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # corrupt file — fall back to seed, don't crash
        log.warning("plan.json unreadable (%s); using seed", exc)
    plan = _seed_plan()
    _write(plan)
    log.info("seeded plan.json from plan.py defaults")
    return plan


def _write(plan: dict) -> None:
    _CONFIG_DIR.mkdir(exist_ok=True)
    _PLAN_FILE.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(_PLAN_FILE, 0o600)
    except OSError:
        pass  # no-op on Windows


def get_plan() -> dict:
    """Return the current canonical plan (always read fresh from disk)."""
    with _LOCK:
        return _load()


def save_plan(plan: dict) -> None:
    with _LOCK:
        _write(plan)


def reset() -> dict:
    """Discard edits and re-seed from plan.py defaults."""
    with _LOCK:
        plan = _seed_plan()
        _write(plan)
        return plan


def blank() -> dict:
    """Start from scratch: keep the hub *shells* (layer/priority/description/
    alternatives) and layer names, but clear every repo assignment — no
    absorbs, no archives, no keeps. After a scan every repo is undecided, so
    the plan is rebuilt from the real portfolio via triage/replan, and hubs are
    (re)created consistently through Execute rather than assumed to exist."""
    with _LOCK:
        seed = _seed_plan()
        plan = {
            "hubs": {
                name: {**meta, "absorbs": []}
                for name, meta in seed["hubs"].items()
            },
            "archives": {},
            "keeps": [],
            "layer_names": seed["layer_names"],
        }
        _write(plan)
        return plan


# --- derived lookups -------------------------------------------------------

def repo_placement(plan: dict | None = None) -> dict[str, dict]:
    """Map every planned repo -> {"verdict", "hub"}.

    A repo can appear in exactly one place; if the seed ever double-lists a
    repo, absorb wins over archive wins over keep (most specific intent).
    """
    plan = plan or get_plan()
    placement: dict[str, dict] = {}
    # A hub repo is definitionally kept — it's the destination, not a candidate.
    for hub in plan.get("hubs", {}):
        placement[hub] = {"verdict": "keep", "hub": None}
    for repo in plan.get("keeps", []):
        placement[repo] = {"verdict": "keep", "hub": None}
    for repo, hub in plan.get("archives", {}).items():
        placement[repo] = {"verdict": "archive", "hub": hub}
    for hub, meta in plan.get("hubs", {}).items():
        for repo in meta.get("absorbs", []):
            placement[repo] = {"verdict": "absorb", "hub": hub}
    return placement


def _unassign(plan: dict, repo: str) -> None:
    """Remove a repo from every placement in-place."""
    plan["keeps"] = [r for r in plan.get("keeps", []) if r != repo]
    plan.get("archives", {}).pop(repo, None)
    for meta in plan.get("hubs", {}).values():
        meta["absorbs"] = [r for r in meta.get("absorbs", []) if r != repo]


def set_verdict(repo: str, verdict: str, hub: str | None = None) -> dict:
    """Set a single repo's fate and persist. Returns the updated placement.

    verdict:
      absorb  -> requires a hub; repo added to that hub's absorbs
      archive -> hub optional; repo recorded as an archive target
      keep    -> repo added to keeps
      orphan  -> repo removed from every placement (back to undecided)
    """
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}")

    with _LOCK:
        plan = _load()
        if verdict == "absorb":
            if not hub or hub not in plan.get("hubs", {}):
                raise ValueError("absorb requires a known hub")
        _unassign(plan, repo)

        if verdict == "absorb":
            absorbs = plan["hubs"][hub].setdefault("absorbs", [])
            if repo not in absorbs:
                absorbs.append(repo)
        elif verdict == "archive":
            plan.setdefault("archives", {})[repo] = hub
        elif verdict == "keep":
            plan.setdefault("keeps", []).append(repo)
        # orphan: already unassigned

        _write(plan)
        log.info("verdict %s -> %s%s", repo, verdict, f" ({hub})" if hub else "")
        return {"repo": repo, "verdict": verdict, "hub": hub if verdict != "keep" else None}
