"""
installer.py — Step 8 (Guided installer).

The plan as a DAG of hubs, each hub composed of the absorbed repos it
groups. This router is read-only and produces both a UI rendering (the
`/install` page) and a machine-readable manifest (JSON / docker-compose
fragment) that a downstream agent — or the user — can consume and act on.

git-suite does NOT build, download, or modify the hubs; it exports the
shape. Composition lives in the hub's own repo. The Plan/DAG is the
hand-off.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Iterable

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import plan_store
from routers.auth import require_session

log = logging.getLogger(__name__)
router = APIRouter()


# -- DAG construction ------------------------------------------------------


def _hub_node(hub_name: str, hub: dict) -> dict:
    """A hub as a DAG node: its own repo (when the hub IS a repo) plus
    the absorbed repos it groups. Description / boundary are surfaced so
    a downstream installer can decide what optional tools belong here."""
    return {
        "name": hub_name,
        "description": hub.get("description", "") or "",
        "boundary": hub.get("boundary", "") or "",
        "priority": hub.get("priority"),
        "url": f"https://github.com/{hub_name}" if "/" not in hub_name else f"https://github.com/{hub_name}",
        "absorbs": list(hub.get("absorbs", []) or []),
    }


def _repo_url(repo: str) -> str:
    if "/" in repo:
        return f"https://github.com/{repo}"
    return f"https://github.com/{repo}"


def _build_dag() -> dict:
    """Turn plan.json hubs into a sorted top-down DAG (priority asc, then
    alphabetical) with each hub's repo list and an 'install order' that
    respects hub-on-hub absorption if a hub name contains '/'.

    Order stable: deterministic across calls with the same plan.
    """
    plan = plan_store.get_plan()
    hubs = plan.get("hubs", {})

    # Hubs ordered by (priority first, then alphabetical). Treat None as
    # "later than any numbered priority" — emergent ordering.
    def _sort_key(nh: tuple[str, dict]) -> tuple[int, str]:
        _, meta = nh
        pr = meta.get("priority")
        return (0, pr) if isinstance(pr, int) else (1, 0), nh[0].lower()

    nodes: list[dict] = [_hub_node(n, m) for n, m in sorted(hubs.items(), key=_sort_key)]

    # Edges only when one hub's name is itself an absorbed repo of another.
    # Edge {from: prerequisite, to: dependent}: hub `to` is installed after
    # hub `from` — the dependent presupposes the prerequisite.
    id_for_name = {n["name"]: n["name"] for n in nodes}

    edges: list[dict] = []
    # For each hub, the set of prerequisite hubs it must wait on.
    prereqs: dict[str, set[str]] = {n["name"]: set() for n in nodes}
    # Reverse: a hub is a prereq for anyone who absorbs its name.
    absorbs_targets: dict[str, set[str]] = {n["name"]: set() for n in nodes}
    for hub_node in nodes:
        for absorbed in hub_node["absorbs"]:
            if absorbed in id_for_name:
                edges.append({"from": absorbed, "to": hub_node["name"]})
                prereqs[hub_node["name"]].add(absorbed)
                absorbs_targets[absorbed].add(hub_node["name"])

    # Kahn's algorithm: a hub is ready when its set of prereqs is empty
    # (every prereq either already installed or there were none).
    installed: set[str] = set()
    install_order: list[str] = []
    while True:
        ready = sorted(n for n, pqs in prereqs.items()
                       if n not in installed and not (pqs - installed))
        if not ready:
            break
        name = ready[0]
        installed.add(name)
        install_order.append(name)

    leftover = sorted(n for n in nodes if n["name"] not in installed)
    if leftover:
        log.warning("installer: cycle detected among hubs %s — appending tail", leftover)
        install_order.extend(leftover)

    return {
        "nodes": nodes,
        "edges": edges,
        "install_order": install_order,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "version": 1,
    }


# -- routes ----------------------------------------------------------------


@router.get("/install/{session_id}")
async def installer_manifest(session_id: str):
    """JSON manifest — the machine-readable install plan. Designed to be
    fetched by a downstream hub-standards agent, or saved by the user,
    never acted upon by git-suite directly."""
    await require_session(session_id)
    dag = _build_dag()
    return dag


@router.get("/install/{session_id}/text")
async def installer_text_route(session_id: str):
    """A human-readable install order, suitable for saving as a checklist
    or pasting into a hub-standards runbook."""
    await require_session(session_id)
    dag = _build_dag()
    lines: list[str] = []
    lines.append("# git-suite install plan")
    lines.append(f"# generated {dag['generated_at']} — version {dag['version']}")
    lines.append("# git-suite emits this; the hubs themselves are owned by their repos.")
    lines.append("")
    if not dag["nodes"]:
        lines.append("(no hubs in plan.json — form one on the Cluster page first)")
        return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")

    lines.append("## Install order (topologically sorted)")
    for i, name in enumerate(dag["install_order"], 1):
        node = next(n for n in dag["nodes"] if n["name"] == name)
        deps = sorted(set(e["to"] for e in dag["edges"] if e["from"] == name))
        suffix = f"   (after: {', '.join(deps)})" if deps else ""
        lines.append(f"{i:3d}. {name}{suffix}")
        if node["description"]:
            lines.append(f"      — {node['description']}")
    lines.append("")
    lines.append("## Hubs")
    for node in dag["nodes"]:
        lines.append(f"### {node['name']}")
        lines.append(f"    url: {node['url']}")
        if node["boundary"]:
            lines.append(f"    boundary: {node['boundary']}")
        lines.append(f"    absorbs ({len(node['absorbs'])}):")
        for r in node["absorbs"]:
            lines.append(f"      - {r}")
        lines.append("")
    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")


@router.get("/install/{session_id}/compose")
async def installer_compose(session_id: str):
    """A docker-compose-style fragment. git-suite is the install BRAIN,
    not the build system — this fragment is hand-off only. Each `services`
    entry is a hub + its absorbed repos as comment-documented volume
    mounts. The user (or a downstream agent) decides whether to actually
    run the file."""
    await require_session(session_id)
    dag = _build_dag()
    out: list[str] = ["# Hand-off only — git-suite did not write this file to disk.",
                      "# Generated by POST/GET /api/install/compose. Verify before applying.",
                      ""]
    if not dag["nodes"]:
        out.append("# (no hubs in plan.json)")
        return PlainTextResponse("\n".join(out), media_type="text/x-yaml; charset=utf-8")

    out.append("services:")
    for node in dag["nodes"]:
        anchor = node["name"].replace("/", "-").replace(" ", "-").lower()
        out.append(f"  {anchor}:")
        out.append(f"    # hub: {node['name']}")
        out.append(f"    # url: {node['url']}")
        out.append(f"    # absorbs: {len(node['absorbs'])}")
        out.append("    # image: <set by downstream installer — hub standards pick the image>")
        out.append("    # volumes:")
        if node["absorbs"]:
            for r in node["absorbs"]:
                out.append(f"      # - ./{r}    # {_repo_url(r)}")
        else:
            out.append("      # (no absorbed members)")
        out.append("")
    return PlainTextResponse("\n".join(out), media_type="text/x-yaml; charset=utf-8")


# -- validation body (used by tests and any external agent) ----------------


class ValidateManifestRequest(BaseModel):
    manifest: dict


@router.post("/install/{session_id}/validate")
async def installer_validate_route(session_id: str, body: ValidateManifestRequest):
    """Confirm a manifest received from a downstream agent matches the
    current plan. Edge cases: unknown hub name (added since the manifest
    was generated) is non-fatal — the agent will see the diff on its next
    fetch. A hub absent from the manifest is fatal — the agent must have
    re-fetched before running."""
    await require_session(session_id)
    live = _build_dag()
    live_names = {n["name"] for n in live["nodes"]}
    manifest_hubs = {n["name"] for n in (body.manifest.get("nodes") or [])}
    missing = sorted(live_names - manifest_hubs)
    added = sorted(manifest_hubs - live_names)
    return {"live_hub_count": len(live_names),
            "manifest_hub_count": len(manifest_hubs),
            "missing_from_manifest": missing,
            "added_in_manifest": added,
            "in_sync": not missing and not added}
