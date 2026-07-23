import asyncio
import json
import logging
import uuid

import httpx as _httpx
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.auth import require_session
from services import distill as distill_svc
from services.github import GH_API, _headers as _gh_headers, list_repos, _rate_limit_wait

log = logging.getLogger(__name__)

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
    owner = (repo.get("owner") or {}).get("login", "")

    return {
        "name": name,
        "full_name": repo.get("full_name") or (f"{owner}/{name}" if owner else name),
        "super_cat": super_cat,
        "mid_cat": hub or "",
        "aim": repo.get("description") or "",
        "url": repo.get("html_url", ""),
        "visibility": "private" if repo.get("private") else "public",
        # enriched signal (all come free in the repos list response)
        "stars": repo.get("stargazers_count") or 0,
        "is_fork": 1 if repo.get("fork") else 0,
        "pushed_at": repo.get("pushed_at") or "",
        "topics": json.dumps(repo.get("topics") or []),
        "archived": 1 if repo.get("archived") else 0,
        "size": repo.get("size") or 0,
    }


class ScanRequest(BaseModel):
    session_id: str


@router.post("/scan/start")
async def start_scan(body: ScanRequest):
    await require_session(body.session_id)

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
               (scan_id, name, full_name, super_cat, mid_cat, aim, url, visibility,
                stars, is_fork, pushed_at, topics, archived, size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    scan_id, r["name"], r.get("full_name"), r["super_cat"], r["mid_cat"],
                    r["aim"], r["url"], r["visibility"],
                    r["stars"], r["is_fork"], r["pushed_at"], r["topics"], r["archived"], r["size"],
                )
                for r in repos
            ],
        )
        # Snapshot forks straight from the scan rows — no second /user/repos
        # pull (which is what tripped GitHub's secondary rate limit). The list
        # response has no `parent`, so parent_full_name is "" (same as before).
        forks = [r for r in repos if r.get("is_fork")]
        await db.execute("DELETE FROM fork")
        if forks:
            await db.executemany(
                """INSERT OR REPLACE INTO fork
                   (full_name, name, owner, description, topics,
                    parent_full_name, pushed_at, archived, url)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [(r.get("full_name") or "", r["name"], username, r.get("aim") or "",
                  r["topics"], "", r.get("pushed_at") or "",
                  r.get("archived") or 0, r.get("url") or "") for r in forks],
            )
        await db.execute(
            "UPDATE scan_meta SET repo_count = ?, finished_at = datetime('now') WHERE scan_id = ?",
            (len(repos), scan_id),
        )
        await db.commit()

    log.info("scan %s complete — %d repos saved", scan_id, len(repos))
    await websocket.send_json({"type": "done", "total": len(repos)})
    await websocket.close()


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


# ── distill loop ───────────────────────────────────────────────────────────────


async def _head_one(token: str, full_name: str) -> dict:
    """Cheap GET /repos/{owner}/{repo} → accessibility + readme URL.

    Kept as a module-level helper because Promote's checklist LLM prompt needs
    the same shape (default_branch, parent visibility, archive flag). The
    standalone /scan/heads/{sid} endpoint that wrapped this for the Scan page
    was removed — that page now composes README URLs from full_name directly.
    """
    try:
        owner, repo = full_name.split("/", 1)
    except ValueError:
        return {"full_name": full_name, "error": "bad full_name"}
    url = f"{GH_API}/repos/{owner}/{repo}"
    r = None
    for attempt in range(4):
        try:
            async with _httpx.AsyncClient(timeout=20) as c:
                r = await c.get(url, headers=_gh_headers(token))
        except Exception as exc:
            return {"full_name": full_name, "error": f"network: {exc}"}
        # A 403/429 may be a rate limit (back off + retry) rather than a private
        # fork — only fall through to the 403 branch for a *genuine* forbidden.
        if r.status_code in (403, 429):
            wait = _rate_limit_wait(r)
            if wait is not None and attempt < 3:
                await asyncio.sleep(min(wait, 120))
                continue
        break
    if r.status_code == 404:
        return {"full_name": full_name, "status": 404,
                "issue": "not_found",
                "message": "Repo missing (deleted or renamed)."}
    if r.status_code == 403:
        return {"full_name": full_name, "status": 403,
                "issue": "forbidden",
                "message": "403 — likely a private upstream on a fork, or the "
                           "owner revoked access. Click to inspect on GitHub."}
    if r.status_code >= 400:
        return {"full_name": full_name, "status": r.status_code,
                "issue": "other", "message": f"HTTP {r.status_code}"}
    j = r.json()
    default_branch = j.get("default_branch") or "main"
    parent = (j.get("parent") or {})
    parent_priv = parent.get("private") if isinstance(parent, dict) else None
    return {
        "full_name": full_name,
        "name": j.get("name"),
        "url": j.get("html_url"),
        "private": bool(j.get("private")),
        "fork": bool(j.get("fork")),
        "archived": bool(j.get("archived")),
        "default_branch": default_branch,
        "readme_url": (f"https://github.com/{owner}/{repo}/blob/"
                       f"{default_branch}/README.md"),
        "parent_full_name": parent.get("full_name") if parent else None,
        "parent_private": parent_priv,
        "issue": ("private_parent_fork" if (j.get("fork") and parent_priv)
                  else None),
        "message": ("Fork whose upstream is private — the fork is yours, "
                    "but the parent is now hidden. README fetch may 404."
                    if (j.get("fork") and parent_priv) else ""),
    }

async def _repos_for_distill(session_id: str) -> list[dict]:
    """Owned repos + stars, each enriched with readme_url + url + topics."""
    latest = await latest_scan(session_id)
    out: list[dict] = []
    for r in latest["repos"]:
        out.append({
            "name": r["name"],
            "full_name": r.get("full_name"),
            "aim": r.get("aim") or "",
            "topics": json.loads(r.get("topics") or "[]"),
            "url": r.get("url") or "",
            "readme_url": None,
        })
    async for db in get_db():
        star_rows = await db.execute_fetchall(
            "SELECT full_name, name, description, topics FROM starred_repo")
    for s in star_rows:
        if not s["full_name"]:
            continue
        try:
            topics = json.loads(s["topics"] or "[]")
        except Exception:
            topics = []
        out.append({
            "name": s["name"] or s["full_name"].split("/", 1)[-1],
            "full_name": s["full_name"],
            "aim": s["description"] or "",
            "topics": topics,
            "url": f"https://github.com/{s['full_name']}",
            "readme_url": (f"https://github.com/{s['full_name']}/blob/main/"
                           "README.md"),
        })
    return out


@router.post("/scan/distill/{session_id}")
async def distill(session_id: str, limit: int = 0):
    """Distil ONE batch of up to `limit` not-yet-cached repos (limit=0 = all),
    then report progress so the UI can loop until done. Cached by src_hash, so
    it resumes where it left off. `stop_on_error=False` — a transient failure on
    one repo skips it (retried next batch); only a hard credit/quota stop sets
    `stop_reason`."""
    await require_session(session_id)
    repos = await _repos_for_distill(session_id)
    total = len(repos)
    if not repos:
        return {"done": 0, "total": 0, "cached": 0, "remaining": 0, "stop_reason": ""}

    todo = await distill_svc.uncached(repos)
    already = total - len(todo)
    batch = todo[:limit] if limit and limit > 0 else todo
    recs, stop_reason = await distill_svc.records(batch, stop_on_error=False)
    done = sum(1 for r in recs.values() if r.get("purpose"))
    # The repos finished this batch (name + domain) so the UI can show progress.
    done_repos = [{"repo": k, "domain": v.get("domain", "")}
                  for k, v in recs.items() if v.get("purpose")]
    return {
        "done": done,                          # newly distilled this batch
        "total": total,
        "cached": already + done,              # total with a record now
        "remaining": max(0, len(todo) - done),  # still to do
        "stop_reason": stop_reason,
        "done_repos": done_repos,
    }


@router.get("/scan/distill/{session_id}/records")
async def distill_records(session_id: str):
    """Cached structured records (purpose/entities/domain) for the Scan table."""
    await require_session(session_id)
    repos = await _repos_for_distill(session_id)
    keys = [distill_svc._key(r) for r in repos]   # ponytail: re-use the cache key fn
    async for db in get_db():
        rows = await db.execute_fetchall(
            f"SELECT repo, record FROM repo_domain "
            f"WHERE repo IN ({','.join('?' * len(keys))})",
            tuple(keys),
        )
    out = {}
    for r in rows:
        try:
            out[r["repo"]] = json.loads(r["record"])
        except Exception:
            out[r["repo"]] = {"purpose": "", "entities": [], "domain": ""}
    return out


