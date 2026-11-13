"""
grouping_store.py — the durable grouping ledger.

Pre-plan working state that turns clustering into a checkpointed,
human-in-the-loop refinement: every repo carries a mark (unsettled /
proposed / settled / ambiguous) plus which clump it belongs to and a
confidence. Reads/writes ~/.git-suite/grouping.json beside plan.json.
Portfolio-scoped (not session-scoped) so the walk resumes across restarts.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_HOME = Path(os.environ.get("GIT_SUITE_HOME", str(Path.home() / ".git-suite")))
_FILE = _HOME / "grouping.json"
_LOCK = threading.Lock()

STATUSES = {"unsettled", "proposed", "settled", "ambiguous"}


def _seed() -> dict:
    return {
        "statuses": {},   # repo_key -> {status, clump, confidence, why}
        "clumps": {},     # slug -> {name, description, confidence}
        "answers": [],    # [{question, answer}]
        "pending": [],    # deltas awaiting approval (step 2)
        "round": 0,
        "floor": 0.85,
    }


def load() -> dict:
    """Return the ledger, healing any missing top-level keys. Never raises —
    a corrupt file falls back to the empty seed (like plan_store)."""
    with _LOCK:
        try:
            if _FILE.exists():
                d = json.loads(_FILE.read_text(encoding="utf-8"))
                for k, v in _seed().items():
                    d.setdefault(k, v)
                return d
        except Exception as exc:  # corrupt file — fall back to seed, don't crash
            log.warning("grouping.json unreadable (%s); using seed", exc)
        return _seed()


def save(ledger: dict) -> None:
    with _LOCK:
        _HOME.mkdir(exist_ok=True)
        _FILE.write_text(json.dumps(ledger, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    try:
        os.chmod(_FILE, 0o600)
    except OSError:
        pass  # no-op on Windows


def reset() -> dict:
    ledger = _seed()
    save(ledger)
    return ledger


def seed_from_clusters(payload: dict, floor: float = 0.85) -> dict:
    """Round-0 seed from a clustering payload (the shape `routers/cluster.py`
    produces): every cluster member -> proposed(slug) with the cluster's
    confidence; every orphan -> unsettled. Replaces any prior ledger wholesale —
    freezing previously-settled repos arrives with the delta model (step 2)."""
    ledger = _seed()
    ledger["floor"] = floor

    for c in payload.get("clusters") or []:
        slug = c.get("slug") or c.get("suggested_name") or "theme"
        conf = c.get("confidence")
        ledger["clumps"][slug] = {
            "name": c.get("suggested_name", slug),
            "description": c.get("suggested_description", ""),
            "confidence": conf,
        }
        for m in c.get("members") or []:
            key = m.get("full_name") or m.get("repo") or m.get("name") or ""
            if not key:
                continue
            ledger["statuses"][key] = {
                "status": "proposed",
                "clump": slug,
                "confidence": conf,
                "why": "",
            }

    for o in payload.get("orphans_returned") or []:
        key = o.get("full_name") or o.get("repo") or o.get("name") or ""
        if key:
            ledger["statuses"][key] = {
                "status": "unsettled",
                "clump": None,
                "confidence": None,
                "why": "",
            }

    ledger["round"] = payload.get("round") or 0
    ledger["answers"] = list(payload.get("answers") or [])
    save(ledger)
    return ledger


def summary(ledger: dict | None = None) -> dict:
    """Traffic-light rollup: how many repos are still moving vs settled."""
    ledger = ledger or load()
    counts = {s: 0 for s in STATUSES}
    for s in ledger["statuses"].values():
        counts[s.get("status", "unsettled")] += 1
    return {
        "counts": counts,
        "clumps": len(ledger["clumps"]),
        "round": ledger["round"],
        "floor": ledger["floor"],
    }


# ── delta application (step 2) ──────────────────────────────────────────────

def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "theme"


def members_of(ledger: dict, slug: str) -> list[str]:
    """Repo keys currently placed in `slug` (derived from statuses)."""
    return [k for k, s in ledger["statuses"].items() if s.get("clump") == slug]


def unsettled_keys(ledger: dict) -> list[str]:
    """Every repo that is still fair game for a delta (not settled)."""
    return [k for k, s in ledger["statuses"].items() if s.get("status") != "settled"]


def apply_delta(ledger: dict, delta: dict) -> dict:
    """Commit one delta in place. Returns {ok, changed, error}.

    Freeze rule: a settled repo is never moved, split out, or renamed away.
    merge and rename consolidate without relocating a repo, so they are always
    allowed. Approved deltas settle the repos they directly place."""
    dtype = delta.get("type")
    statuses = ledger["statuses"]
    clumps = ledger["clumps"]
    changed: list[str] = []
    conf = delta.get("confidence")

    def _settle(key: str, clump: str) -> None:
        statuses[key] = {"status": "settled", "clump": clump,
                         "confidence": conf, "why": ""}
        changed.append(key)

    if dtype == "merge":
        a, b = delta.get("a"), delta.get("b")
        if a not in clumps or b not in clumps or a == b:
            return {"ok": False, "changed": changed, "error": "merge needs two distinct clumps"}
        new_name = (delta.get("new_name") or "").strip() or clumps[a].get("name", a)
        for key in list(statuses):
            if statuses[key].get("clump") == b:
                statuses[key]["clump"] = a
        clumps[a]["name"] = new_name
        clumps.pop(b, None)
        for key in members_of(ledger, a):
            _settle(key, a)
        return {"ok": True, "changed": changed, "error": None}

    if dtype == "split":
        c = delta.get("cluster")
        if c not in clumps:
            return {"ok": False, "changed": changed, "error": "unknown source clump"}
        take = set(delta.get("members") or [])
        moved = [k for k in members_of(ledger, c) if k in take]
        if not moved:
            return {"ok": False, "changed": changed, "error": "split members not in clump"}
        for k in moved:
            if statuses[k].get("status") == "settled":
                return {"ok": False, "changed": changed,
                        "error": f"cannot split settled repo {k}"}
        new_slug = _slugify(delta.get("new_name")) or f"{c}-split"
        base = new_slug
        n = 2
        while new_slug in clumps:
            new_slug = f"{base}-{n}"
            n += 1
        clumps[new_slug] = {
            "name": (delta.get("new_name") or "").strip() or new_slug,
            "description": "",
            "confidence": conf,
        }
        for k in moved:
            _settle(k, new_slug)
        return {"ok": True, "changed": changed, "error": None}

    if dtype == "move":
        repo = delta.get("repo")
        if repo not in statuses:
            return {"ok": False, "changed": changed, "error": f"unknown repo {repo!r}"}
        if statuses[repo].get("status") == "settled":
            return {"ok": False, "changed": changed, "error": f"cannot move settled repo {repo}"}
        to = delta.get("to")
        if to == "unplaced":
            statuses[repo] = {"status": "unsettled", "clump": None,
                              "confidence": None, "why": ""}
            changed.append(repo)
        elif to in clumps:
            _settle(repo, to)
        else:
            return {"ok": False, "changed": changed, "error": f"unknown destination clump {to!r}"}
        return {"ok": True, "changed": changed, "error": None}

    if dtype == "rename":
        c = delta.get("cluster")
        if c not in clumps:
            return {"ok": False, "changed": changed, "error": "unknown clump to rename"}
        clumps[c]["name"] = (delta.get("new_name") or "").strip() or clumps[c].get("name", c)
        return {"ok": True, "changed": changed, "error": None}

    return {"ok": False, "changed": changed, "error": f"unknown delta type {dtype!r}"}
