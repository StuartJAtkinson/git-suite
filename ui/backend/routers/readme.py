import base64
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db
from plan import HUB_ABSORBS, HUB_META, HUB_ALTERNATIVES
from services.github import get_file_sha, push_file

router = APIRouter()

_ROADMAP_START = "<!-- integration-roadmap-start -->"
_ROADMAP_END = "<!-- integration-roadmap-end -->"


def _build_roadmap_section(hub: str, commercial_refs: list[dict]) -> str:
    meta = HUB_META.get(hub, {})
    absorbs = HUB_ABSORBS.get(hub, [])
    alts = HUB_ALTERNATIVES.get(hub, {})

    oss_list = ". ".join(alts.get("oss", []))
    commercial_list = ". ".join(alts.get("commercial", []))

    # Merge scraped commercial refs into the commercial list
    scraped_names = [r["name"] for r in commercial_refs if r.get("name") and r["name"] != "Unknown"]
    if scraped_names:
        commercial_list = commercial_list + (". " if commercial_list else "") + ". ".join(scraped_names)

    absorbs_block = "\n".join(f"- {r}" for r in absorbs) if absorbs else "- (none yet)"

    feature_lines = []
    for ref in commercial_refs:
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


def _inject_roadmap(existing_content: str, new_section: str) -> str:
    if _ROADMAP_START in existing_content:
        start = existing_content.index(_ROADMAP_START)
        end = existing_content.index(_ROADMAP_END) + len(_ROADMAP_END)
        return existing_content[:start] + new_section + existing_content[end:]
    return existing_content.rstrip() + "\n\n" + new_section + "\n"


class PushReadmeRequest(BaseModel):
    session_id: str
    hub: str


@router.post("/readme/push")
async def push_readme(body: PushReadmeRequest):
    async for db in get_db():
        session = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (body.session_id,)
        )
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")
        refs_rows = await db.execute_fetchall(
            "SELECT url, name, features FROM commercial_refs WHERE hub = ?", (body.hub,)
        )

    token = session[0]["github_token"]
    owner = session[0]["github_user"]

    commercial_refs = [
        {"url": r["url"], "name": r["name"], "features": json.loads(r["features"])}
        for r in refs_rows
    ]

    # Fetch existing README
    sha = await get_file_sha(token, owner, body.hub, "README.md")

    if sha is not None:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.github.com/repos/{owner}/{body.hub}/contents/README.md",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            r.raise_for_status()
            existing = base64.b64decode(r.json()["content"]).decode("utf-8")
    else:
        existing = f"# {body.hub}\n\n"

    new_section = _build_roadmap_section(body.hub, commercial_refs)
    updated = _inject_roadmap(existing, new_section)

    content_b64 = base64.b64encode(updated.encode("utf-8")).decode("ascii")
    await push_file(
        token=token,
        owner=owner,
        repo=body.hub,
        path="README.md",
        content_b64=content_b64,
        message=f"chore: update integration roadmap [{body.hub}]",
        sha=sha,
    )

    return {"pushed": True, "hub": body.hub, "sha_was": sha}


@router.get("/readme/preview/{hub}")
async def preview_readme(hub: str, session_id: str):
    async for db in get_db():
        session = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (session_id,)
        )
        if not session:
            raise HTTPException(status_code=401, detail="Invalid session")
        refs_rows = await db.execute_fetchall(
            "SELECT url, name, features FROM commercial_refs WHERE hub = ?", (hub,)
        )

    commercial_refs = [
        {"url": r["url"], "name": r["name"], "features": json.loads(r["features"])}
        for r in refs_rows
    ]

    section = _build_roadmap_section(hub, commercial_refs)
    return {"hub": hub, "section": section}
