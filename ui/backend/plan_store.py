"""
plan_store.py — the single source of truth for the portfolio plan.

Design philosophy #1: the plan is *data*, not code. There is NO seed: the
default plan is empty and nothing is ever assumed to be a hub. Hubs emerge only
from the actual GitHub scan (clustering → promote/create). At runtime the
canonical plan lives in one editable JSON document (~/.git-suite/plan.json) that
the web UI, the CLI and the README generator all read and write. Every other
module derives from here.

Shape of the canonical plan:

    {
      "hubs": {
        "<hub>": {
          "priority": int|null, "description": str,
          "absorbs": [repo, ...],
          "alternatives": {"oss": [...], "commercial": [...]}
        }
      },
      "archives": { "<repo>": "<hub|null>" },
      "keeps":    [repo, ...]
    }

Hub ordering is emergent: no hardcoded layer taxonomy. Default order is by hub
size (absorb count, largest first); `priority` is an optional manual override.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_CONFIG_DIR = Path(os.environ.get("GIT_SUITE_HOME", str(Path.home() / ".git-suite")))
_PLAN_FILE = _CONFIG_DIR / "plan.json"
_LOCK = threading.Lock()

VERDICTS = {"absorb", "archive", "keep", "orphan"}


def _seed_plan() -> dict:
    """The default plan on first run: fully empty. Nothing is assumed — no
    hubs, no repo→hub assignments, no archives. Hubs emerge only from the actual
    GitHub scan (clustering → promote/create); there is no curated seed."""
    return {"hubs": {}, "archives": {}, "keeps": []}


def _heal(plan: dict) -> dict:
    """Structural-only self-heal: ensure the top-level keys and per-hub fields
    exist so older plan.json files keep working, without ever inventing content.
    No taxonomy is seeded — a hub's metadata comes from how the user created it.

    Drops the legacy `layer`/`layer_names` taxonomy from older plans (ordering
    is now emergent)."""
    plan.setdefault("hubs", {})
    plan.setdefault("archives", {})
    plan.setdefault("keeps", [])
    plan.pop("layer_names", None)
    for hub in plan["hubs"].values():
        hub.pop("layer", None)
        hub.setdefault("priority", None)
        hub.setdefault("description", "")
        hub.setdefault("boundary", "")
        hub.setdefault("alternatives", {"oss": [], "commercial": []})
        hub.setdefault("absorbs", [])
    return plan


def _load() -> dict:
    """Load the canonical plan, seeding the file on first run."""
    try:
        if _PLAN_FILE.exists():
            return _heal(json.loads(_PLAN_FILE.read_text(encoding="utf-8")))
    except Exception as exc:  # corrupt file — fall back to seed, don't crash
        log.warning("plan.json unreadable (%s); using seed", exc)
    plan = _seed_plan()
    _write(plan)
    log.info("created empty plan.json (no seed — hubs come from the scan)")
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
    """Discard edits and return to the empty default (no assumed hubs)."""
    with _LOCK:
        plan = _seed_plan()
        _write(plan)
        return plan


def blank() -> dict:
    """Start fresh while keeping the hub *shells* you've already defined
    (priority/description/boundary/alternatives) — just clears every repo
    assignment (no absorbs, no archives, no keeps). Operates on the CURRENT
    plan's hubs, so a removed hub is never resurrected."""
    with _LOCK:
        plan = _load()
        plan = {
            "hubs": {
                name: {**meta, "absorbs": []}
                for name, meta in plan.get("hubs", {}).items()
            },
            "archives": {},
            "keeps": [],
        }
        _write(plan)
        return plan


# --- derived lookups -------------------------------------------------------

def hub_sort_key(priority: int | None, size: int, name: str) -> tuple:
    """Emergent hub order: manual `priority` first (unset sorts last), then
    larger hubs (more absorbs) first, then name. Replaces the old layer sort."""
    return (priority if priority is not None else 1_000, -size, name)



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


def clear() -> dict:
    """Truly empty plan: no hubs, no assignments. Nothing is assumed to be a
    hub — hubs are rebuilt explicitly from the scan."""
    with _LOCK:
        plan = {"hubs": {}, "archives": {}, "keeps": []}
        _write(plan)
        return plan


def upsert_hub(name: str, priority: int | None = None,
               description: str = "", boundary: str = "",
               alternatives: dict | None = None) -> dict:
    """Create or update a hub definition. Preserves existing absorbs.

    priority is optional — None means 'unassigned' (emergent ordering by hub
    size), stored as null rather than coerced to a hardcoded number."""
    if not name or not name.strip():
        raise ValueError("hub name required")
    with _LOCK:
        plan = _load()
        hub = plan["hubs"].get(name, {"absorbs": []})
        hub.update({
            "priority": int(priority) if priority is not None else None,
            "description": description, "boundary": boundary,
            "alternatives": alternatives or hub.get("alternatives") or {"oss": [], "commercial": []},
        })
        hub.setdefault("absorbs", [])
        plan["hubs"][name] = hub
        _write(plan)
        return hub


def remove_hub(name: str) -> dict:
    """Delete a hub definition; any repos archived 'to' it lose that hub link."""
    with _LOCK:
        plan = _load()
        plan["hubs"].pop(name, None)
        for repo, hub in list(plan.get("archives", {}).items()):
            if hub == name:
                plan["archives"][repo] = None
        _write(plan)
        return {"removed": name}


def add_hub_alternative(hub: str, name: str, kind: str = "oss") -> dict:
    """Append a starred/external project to a hub's OSS/commercial alternatives
    list (idempotent). This is how a Stars suggestion gets accepted into the plan."""
    return _edit_alternative(hub, name, kind, add=True)


def remove_hub_alternative(hub: str, name: str, kind: str = "oss") -> dict:
    return _edit_alternative(hub, name, kind, add=False)


def _edit_alternative(hub: str, name: str, kind: str, add: bool) -> dict:
    if kind not in ("oss", "commercial"):
        raise ValueError(f"unknown kind {kind!r}")
    if not name or not name.strip():
        raise ValueError("alternative name required")
    with _LOCK:
        plan = _load()
        if hub not in plan.get("hubs", {}):
            raise ValueError(f"unknown hub {hub!r}")
        alts = plan["hubs"][hub].setdefault("alternatives", {"oss": [], "commercial": []})
        lst = alts.setdefault(kind, [])
        if add:
            if name not in lst:
                lst.append(name)
        else:
            alts[kind] = [a for a in lst if a != name]
        _write(plan)
        return alts


def set_hub_boundary(hub: str, boundary: str) -> dict:
    """Edit a hub's boundary statement (the scope rule fed to the LLM)."""
    with _LOCK:
        plan = _load()
        if hub not in plan.get("hubs", {}):
            raise ValueError(f"unknown hub {hub!r}")
        plan["hubs"][hub]["boundary"] = boundary
        _write(plan)
        return {"hub": hub, "boundary": boundary}


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
