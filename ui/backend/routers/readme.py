"""
readme.py — compose and push each hub's "Integration Roadmap" README section.

Reads the LIVE plan via plan_store (not the static seed) so README content
reflects triage/replan edits. The compose/push/status functions are reusable
so the Execute router can batch-push READMEs for many hubs.
"""
import base64
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from services.github import get_file, push_file

log = logging.getLogger(__name__)
router = APIRouter()

_ROADMAP_START = "<!-- integration-roadmap-start -->"
_ROADMAP_END = "<!-- integration-roadmap-end -->"


def compose_section(hub: str, refs: list[dict], plan: dict | None = None) -> str:
    """Build the integration-roadmap section for a hub from the live plan."""
    plan = plan or plan_store.get_plan()
    meta = plan.get("hubs", {}).get(hub, {})
    absorbs = meta.get("absorbs", [])
    alts = meta.get("alternatives", {}) or {}

    oss_list = ". ".join(alts.get("oss", []))
    commercial_list = ". ".join(alts.get("commercial", []))

    scraped_names = [r["name"] for r in refs if r.get("name") and r["name"] != "Unknown"]
    if scraped_names:
        commercial_list = commercial_list + (". " if commercial_list else "") + ". ".join(scraped_names)

    absorbs_block = "\n".join(f"- {r}" for r in absorbs) if absorbs else "- (none yet)"

    feature_lines = []
    for ref in refs:
        if ref.get("features"):
            feature_lines.append(f"\n**{ref['name']}** ({ref['url']})")
            feature_lines.extend(f"- {f}" for f in ref["features"])
    scraped_block = "\n".join(feature_lines) if feature_lines else ""

    section = f"""{_ROADMAP_START}
## Integration Roadmap

**Layer {meta.get('layer', '?')} — {meta.get('description', hub)}**

### Repos to absorb
{absorbs_block}

### OSS alternatives
{oss_list or '(none documented)'}

### Commercial alternatives
{commercial_list or '(none documented)'}
"""
    if scraped_block:
        section += f"\n### Scraped feature benchmarks\n{scraped_block}\n"

    section += f"""
> Aim: pull functionality from the repos above and take further inspiration from the OSS and
> commercial alternatives. A future goal is to ensure 2-way sync compatibility with open-source
> and commercial alternatives where APIs permit.
{_ROADMAP_END}"""
    return section


def _inject(existing: str, section: str) -> str:
    if _ROADMAP_START in existing and _ROADMAP_END in existing:
        start = existing.index(_ROADMAP_START)
        end = existing.index(_ROADMAP_END) + len(_ROADMAP_END)
        return existing[:start] + section + existing[end:]
    return existing.rstrip() + "\n\n" + section + "\n"


async def _refs_for(hub: str) -> list[dict]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT url, name, features FROM commercial_refs WHERE hub = ?", (hub,)
        )
    return [{"url": r["url"], "name": r["name"], "features": json.loads(r["features"])} for r in rows]


async def readme_status(token: str, owner: str, hub: str, plan: dict | None = None) -> dict:
    """Whether the hub's README roadmap section is missing or out of date."""
    refs = await _refs_for(hub)
    section = compose_section(hub, refs, plan)
    existing = await get_file(token, owner, hub, "README.md")
    if existing is None:
        return {"hub": hub, "exists": False, "needs_update": True, "reason": "no README"}
    if section not in existing["content"]:
        return {"hub": hub, "exists": True, "needs_update": True, "reason": "roadmap missing/stale"}
    return {"hub": hub, "exists": True, "needs_update": False, "reason": "up to date"}


async def push_hub_readme(token: str, owner: str, hub: str, plan: dict | None = None) -> dict:
    """Compose + push the hub's README roadmap section. Reusable by Execute."""
    refs = await _refs_for(hub)
    section = compose_section(hub, refs, plan)
    existing = await get_file(token, owner, hub, "README.md")
    if existing is None:
        base, sha = f"# {hub}\n\n", None
    else:
        base, sha = existing["content"], existing["sha"]
    updated = _inject(base, section)
    content_b64 = base64.b64encode(updated.encode("utf-8")).decode("ascii")
    await push_file(token=token, owner=owner, repo=hub, path="README.md",
                    content_b64=content_b64,
                    message=f"chore: update integration roadmap [{hub}]", sha=sha)
    log.info("README pushed for %s (sha_was=%s)", hub, sha)
    return {"pushed": True, "hub": hub, "sha_was": sha}


async def _session(session_id: str) -> tuple[str, str]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (session_id,)
        )
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid session")
    return rows[0]["github_token"], rows[0]["github_user"]


class PushReadmeRequest(BaseModel):
    session_id: str
    hub: str


@router.post("/readme/push")
async def push_readme(body: PushReadmeRequest):
    token, owner = await _session(body.session_id)
    if body.hub not in plan_store.get_plan().get("hubs", {}):
        raise HTTPException(status_code=404, detail="Unknown hub")
    return await push_hub_readme(token, owner, body.hub)


@router.get("/readme/preview/{hub}")
async def preview_readme(hub: str, session_id: str):
    await _session(session_id)
    refs = await _refs_for(hub)
    return {"hub": hub, "section": compose_section(hub, refs)}
