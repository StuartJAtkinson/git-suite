import json
import uuid
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from database import get_db
from plan import HUB_ABSORBS, ARCHIVE_HUB, KEEP_AS_IS
from services.github import list_repos

router = APIRouter()

# Build a flat lookup: repo_name -> hub (from absorbs + archive targets)
def _repo_to_hub() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for hub, repos in HUB_ABSORBS.items():
        for r in repos:
            mapping[r] = hub
    for repo, hub in ARCHIVE_HUB.items():
        if hub and repo not in mapping:
            mapping[repo] = hub
    return mapping


_REPO_HUB = _repo_to_hub()


def _categorise(repo: dict) -> dict:
    name = repo["name"]
    hub = _REPO_HUB.get(name)
    if name in KEEP_AS_IS:
        super_cat = "keep"
    elif name in ARCHIVE_HUB:
        super_cat = "archive"
    elif hub:
        super_cat = "absorb"
    else:
        super_cat = "orphan"

    return {
        "name": name,
        "super_cat": super_cat,
        "mid_cat": hub or "",
        "fine_cat": "",
        "aim": repo.get("description") or "",
        "url": repo.get("html_url", ""),
        "visibility": "private" if repo.get("private") else "public",
        "language": repo.get("language") or "",
    }


class ScanRequest(BaseModel):
    session_id: str


@router.post("/scan/start")
async def start_scan(body: ScanRequest):
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (body.session_id,)
        )
        if not row:
            raise HTTPException(status_code=401, detail="Invalid session")

    scan_id = str(uuid.uuid4())
    async for db in get_db():
        await db.execute(
            "INSERT INTO scan_meta (scan_id, session_id) VALUES (?, ?)",
            (scan_id, body.session_id),
        )
        await db.commit()

    return {"scan_id": scan_id}


@router.websocket("/scan/{scan_id}/ws")
async def scan_ws(websocket: WebSocket, scan_id: str):
    await websocket.accept()

    async for db in get_db():
        meta = await db.execute_fetchall(
            "SELECT session_id FROM scan_meta WHERE scan_id = ?", (scan_id,)
        )
        if not meta:
            await websocket.close(code=4004)
            return
        session_id = meta[0]["session_id"]

        session = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (session_id,)
        )
        if not session:
            await websocket.close(code=4001)
            return

    token = session[0]["github_token"]
    username = session[0]["github_user"]

    repos: list[dict] = []
    try:
        async for repo in list_repos(token, username):
            row = _categorise(repo)
            repos.append(row)
            await websocket.send_json({"type": "repo", "data": row})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    async for db in get_db():
        await db.executemany(
            """INSERT OR REPLACE INTO repos
               (scan_id, name, super_cat, mid_cat, fine_cat, aim, url, visibility, language)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    scan_id, r["name"], r["super_cat"], r["mid_cat"],
                    r["fine_cat"], r["aim"], r["url"], r["visibility"], r["language"],
                )
                for r in repos
            ],
        )
        await db.execute(
            "UPDATE scan_meta SET repo_count = ?, finished_at = datetime('now') WHERE scan_id = ?",
            (len(repos), scan_id),
        )
        await db.commit()

    await websocket.send_json({"type": "done", "total": len(repos)})
    await websocket.close()


@router.get("/scan/{scan_id}/results")
async def scan_results(scan_id: str, super_cat: str | None = None):
    async for db in get_db():
        if super_cat:
            rows = await db.execute_fetchall(
                "SELECT * FROM repos WHERE scan_id = ? AND super_cat = ?",
                (scan_id, super_cat),
            )
        else:
            rows = await db.execute_fetchall(
                "SELECT * FROM repos WHERE scan_id = ?", (scan_id,)
            )
    return [dict(r) for r in rows]
