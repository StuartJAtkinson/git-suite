"""
readme.py — compose and push each hub's "Integration Roadmap" README section.

Reads the LIVE plan via plan_store (not the static seed) so README content
reflects triage/replan edits. The compose/push/status functions are reusable
so the Execute router can batch-push READMEs for many hubs.

Tree-of-Knowledge ordering and per-repo feature annotations come from the
`hub_order` table (populated by the Order page). When no ordering data
exists yet, the section falls back to the original alphabetical absorbs
list.
"""
import base64
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from services.columns import COLUMNS
from services.github import get_file, push_file

log = logging.getLogger(__name__)
router = APIRouter()

_ROADMAP_START = "<!-- integration-roadmap-start -->"
_ROADMAP_END = "<!-- integration-roadmap-end -->"


def _format_repo_block(repo: str, row: dict | None, *, is_hub: bool = False) -> str:
    """Render one repo's ToK ordering + annotation block.

    `row` is the hub_order row (or None if the repo hasn't been ordered yet).
    `is_hub=True` (caller-determined, not from the row) renders the repo as
    the hub header regardless of its stored position. Everything else is a
    bulleted block with the column flags as a tag prefix and feature
    annotations as sub-bullets.
    """
    if row is None:
        if is_hub:
            return f"- **{repo}** _(hub)_\n  - _(not yet ordered)_"
        return f"- {repo}\n  - _(not yet ordered)_"
    flags = " · ".join(c for c in COLUMNS if row.get(f"is_{c.lower()}"))
    tags = row.get("compat_tags") or []
    annotations = row.get("feature_annotations") or []
    if is_hub:
        # Hub repo itself
        lines = [f"- **{repo}** _(hub)_"]
    else:
        prefix = f"`#{row['position']}`"
        lines = [f"- {prefix} **{repo}**"]
    if flags:
        lines.append(f"  - _{flags}_")
    if tags:
        lines.append(f"  - compat: {', '.join(tags)}")
    for a in annotations:
        lines.append(f"  - {a}")
    return "\n".join(lines)


def compose_section(
    hub: str,
    refs: list[dict],
    plan: dict | None = None,
    hub_order_rows: list[dict] | None = None,
) -> str:
    """Build the integration-roadmap section for a hub from the live plan.

    `hub_order_rows` is the raw list of rows from the `hub_order` table
    (each dict has repo, position, is_gather/is_analyse/is_display,
    compat_tags, feature_annotations). When None or empty, the
    "Tree-of-Knowledge ordering" subsection is omitted and the original
    "Repos to absorb" alphabetical list is shown.
    """
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

    # Build the ToK ordering block. Re-order the absorbs by the position
    # stored in hub_order (with the hub repo pinned to position 0); any
    # repos without a row fall back to alphabetical at the tail so the
    # README never silently drops a member.
    tok_block = ""
    if hub_order_rows:
        by_repo = {r["repo"]: r for r in hub_order_rows}
        ordered = sorted(
            absorbs + [hub],
            key=lambda n: (by_repo.get(n, {}).get("position", 10**9), n),
        )
        # Pin the hub repo to the top regardless of its stored position.
        if hub in ordered:
            ordered.remove(hub)
            ordered = [hub] + ordered
        tok_lines = [
            _format_repo_block(n, by_repo.get(n), is_hub=(n == hub))
            for n in ordered
        ]
        tok_block = "\n".join(tok_lines)

    section = f"""{_ROADMAP_START}
## Integration Roadmap

**Layer {meta.get('layer', '?')} — {meta.get('description', hub)}**

### Repos to absorb
{absorbs_block}
"""
    if tok_block:
        columns_legend = " / ".join(COLUMNS)
        section += f"""
### Tree-of-Knowledge ordering
_Ordered from foundational ({COLUMNS[0]}) to presentation ({COLUMNS[-1]})._
_Columns: {columns_legend}._

{tok_block}
"""

    section += f"""
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


async def _hub_order_for(hub: str) -> list[dict]:
    """Read the hub_order rows for a hub. JSON columns are decoded."""
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT repo, position, is_gather, is_analyse, is_display, "
            "compat_tags, feature_annotations FROM hub_order WHERE hub = ?",
            (hub,),
        )
    out = []
    for r in rows:
        d = dict(r)
        for k in ("compat_tags", "feature_annotations"):
            v = d.get(k) or "[]"
            try:
                d[k] = json.loads(v)
            except Exception:
                d[k] = []
        out.append(d)
    return out


async def readme_status(token: str, owner: str, hub: str, plan: dict | None = None) -> dict:
    """Whether the hub's README roadmap section is missing or out of date."""
    refs = await _refs_for(hub)
    hub_order_rows = await _hub_order_for(hub)
    section = compose_section(hub, refs, plan, hub_order_rows)
    existing = await get_file(token, owner, hub, "README.md")
    if existing is None:
        return {"hub": hub, "exists": False, "needs_update": True, "reason": "no README"}
    if section not in existing["content"]:
        return {"hub": hub, "exists": True, "needs_update": True, "reason": "roadmap missing/stale"}
    return {"hub": hub, "exists": True, "needs_update": False, "reason": "up to date"}


async def push_hub_readme(token: str, owner: str, hub: str, plan: dict | None = None) -> dict:
    """Compose + push the hub's README roadmap section. Reusable by Execute."""
    refs = await _refs_for(hub)
    hub_order_rows = await _hub_order_for(hub)
    section = compose_section(hub, refs, plan, hub_order_rows)
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
    hub_order_rows = await _hub_order_for(hub)
    return {"hub": hub, "section": compose_section(hub, refs, None, hub_order_rows)}
