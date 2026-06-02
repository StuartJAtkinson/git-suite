import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

log = logging.getLogger(__name__)

import plan_store
from database import get_db
from services.github import list_repos

router = APIRouter()


def _categorise(repo: dict, placement: dict[str, dict]) -> dict:
    """Categorise one repo against the live plan placement.

    Placement is computed fresh from plan_store per scan, so a scan always
    reflects the current plan rather than a snapshot frozen at import time.
    """
    name = repo["name"]
    place = placement.get(name)
    super_cat = place["verdict"] if place else "orphan"
    hub = place["hub"] if place else None

    return {
        "name": name,
        "super_cat": super_cat,
        "mid_cat": hub or "",
        "fine_cat": "",
        "aim": repo.get("description") or "",
        "url": repo.get("html_url", ""),
        "visibility": "private" if repo.get("private") else "public",
        "language": repo.get("language") or "",
        # enriched signal (all come free in the repos list response)
        "stars": repo.get("stargazers_count") or 0,
        "is_fork": 1 if repo.get("fork") else 0,
        "pushed_at": repo.get("pushed_at") or "",
        "topics": json.dumps(repo.get("topics") or []),
        "archived": 1 if repo.get("archived") else 0,
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

    log.info("scan %s starting for user=%s", scan_id, username)
    placement = plan_store.repo_placement()
    repos: list[dict] = []
    try:
        async for repo in list_repos(token, username):
            row = _categorise(repo, placement)
            repos.append(row)
            await websocket.send_json({"type": "repo", "data": row})
    except WebSocketDisconnect:
        log.info("scan %s — client disconnected after %d repos", scan_id, len(repos))
        return
    except Exception as exc:
        log.error("scan %s error: %s", scan_id, exc)
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    async for db in get_db():
        await db.executemany(
            """INSERT OR REPLACE INTO repos
               (scan_id, name, super_cat, mid_cat, fine_cat, aim, url, visibility, language,
                stars, is_fork, pushed_at, topics, archived)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    scan_id, r["name"], r["super_cat"], r["mid_cat"],
                    r["fine_cat"], r["aim"], r["url"], r["visibility"], r["language"],
                    r["stars"], r["is_fork"], r["pushed_at"], r["topics"], r["archived"],
                )
                for r in repos
            ],
        )
        await db.execute(
            "UPDATE scan_meta SET repo_count = ?, finished_at = datetime('now') WHERE scan_id = ?",
            (len(repos), scan_id),
        )
        await db.commit()

    log.info("scan %s complete — %d repos saved", scan_id, len(repos))
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


@router.get("/scan/latest/{session_id}")
async def latest_scan(session_id: str):
    """Return the most recent scan_id and full results for a session."""
    scan_id: str | None = None
    repo_count: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    rows_out: list[dict] = []

    async for db in get_db():
        meta_rows = await db.execute_fetchall(
            """SELECT scan_id, repo_count, started_at, finished_at
               FROM scan_meta
               WHERE session_id = ?
               ORDER BY started_at DESC
               LIMIT 1""",
            (session_id,),
        )
        if not meta_rows:
            raise HTTPException(status_code=404, detail="No scan found for session")

        scan_id = meta_rows[0]["scan_id"]
        repo_count = meta_rows[0]["repo_count"]
        started_at = meta_rows[0]["started_at"]
        finished_at = meta_rows[0]["finished_at"]

        repos_rows = await db.execute_fetchall(
            "SELECT * FROM repos WHERE scan_id = ?", (scan_id,)
        )
        rows_out = [dict(r) for r in repos_rows]

    return {
        "scan_id": scan_id,
        "repo_count": repo_count,
        "started_at": started_at,
        "finished_at": finished_at,
        "repos": rows_out,
    }