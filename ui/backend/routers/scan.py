import asyncio
import hashlib
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
from services.github import GH_API, _headers as _gh_headers, list_repos

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
        "language": repo.get("language") or "",
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
                language, stars, is_fork, pushed_at, topics, archived, size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    scan_id, r["name"], r.get("full_name"), r["super_cat"], r["mid_cat"],
                    r["aim"], r["url"], r["visibility"], r["language"],
                    r["stars"], r["is_fork"], r["pushed_at"], r["topics"], r["archived"], r["size"],
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


# ── heads: per-repo accessibility check + README URL builder ────────────────
# We don't fetch the README contents — we build the URL (and read the
# /repos/{owner}/{repo} head: 200 / 404 / 403 / private) so the LLM can name
# the README in its prompt and the user can click through to it. Archived or
# private-upstream repos show up in the "Need attention" panel on Scan.


async def _head_one(token: str, full_name: str) -> dict:
    """Cheap GET /repos/{owner}/{repo} → accessibility + readme URL."""
    try:
        owner, repo = full_name.split("/", 1)
    except ValueError:
        return {"full_name": full_name, "error": "bad full_name"}
    url = f"{GH_API}/repos/{owner}/{repo}"
    try:
        async with _httpx.AsyncClient(timeout=20) as c:
            r = await c.get(url, headers=_gh_headers(token))
    except Exception as exc:
        return {"full_name": full_name, "error": f"network: {exc}"}
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
        # The "this needs attention" flag
        "issue": ("private_parent_fork" if (j.get("fork") and parent_priv)
                  else None),
        "message": ("Fork whose upstream is private — the fork is yours, "
                    "but the parent is now hidden. README fetch may 404."
                    if (j.get("fork") and parent_priv) else ""),
    }


@router.get("/scan/heads/{session_id}")
async def heads(session_id: str):
    """Per-repo heads for the latest scan + the stars snapshot, in parallel.

    Each row carries accessibility (200/404/403), archived/private/fork flags,
    the default README URL, and a `message` for any issue that needs your
    attention (private-upstream forks, archived stars, 403s, etc)."""
    sess = await require_session(session_id)
    latest = await latest_scan(session_id)
    rows = latest["repos"]
    # full_name is what GitHub URLs want; the scan rows only have `name`, but
    # the stars snapshot has `full_name` on its own. Build one set of full_names
    # by joining the names against the github_user from the session.
    user = sess["github_user"]
    full_names = sorted({f"{user}/{r['name']}" for r in rows})
    # Stars live in starred_repo with their own full_name; include them too
    # (the user explicitly asked to flag 403 stars so they can unstar).
    async for db in get_db():
        star_rows = await db.execute_fetchall("SELECT full_name FROM starred_repo")
    for s in star_rows:
        if s["full_name"] and s["full_name"] not in full_names:
            full_names.append(s["full_name"])

    sem = asyncio.Semaphore(8)

    async def go(n: str) -> dict:
        async with sem:
            return await _head_one(sess["github_token"], n)

    results = await asyncio.gather(*[go(n) for n in full_names])
    return {"total": len(results), "heads": results}


# ── distill loop (uses the heads URLs as the LLM's variable) ────────────────

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
async def distill(session_id: str):
    """Run the LLM distillation loop over every repo in the latest scan +
    stars snapshot. Cached by src_hash. Stops on credit/quota exhaustion."""
    await require_session(session_id)
    repos = await _repos_for_distill(session_id)
    if not repos:
        return {"done": 0, "failed": 0, "total": 0, "stop_reason": ""}
    records, stop_reason = await distill_svc.records(repos, stop_on_error=True)
    return {
        "done": sum(1 for r in records.values() if r.get("purpose")),
        "failed": sum(1 for r in records.values() if not r.get("purpose")),
        "total": len(records),
        "stop_reason": stop_reason,
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


@router.post("/scan/distill/revalidate/{session_id}")
async def revalidate(session_id: str):
    """Second pass: re-ask the LLM whether each repo's purpose still fits the
    cluster it landed in. Reads the saved clustering from cluster_result,
    caches the verdicts in repo_verdict keyed by cluster_hash, returns the new
    counts so the UI can show drift badges."""
    await require_session(session_id)
    repos = await _repos_for_distill(session_id)

    cluster_map, cluster_hash = await _load_cluster_map(session_id)
    if not cluster_map:
        return {"verdicts": {}, "counts": {"fit": 0, "drift": 0,
                "mis-clustered": 0, "skipped": len(repos)},
                "cluster_hash": "", "stop_reason": "no clustering yet"}

    verdicts = await distill_svc.revalidate(repos, cluster_map, stop_on_error=True)
    # Persist (capped to repos that actually have a cluster assignment)
    cap = {k: v for k, v in verdicts.items() if k in cluster_map}
    async for db in get_db():
        await db.executemany(
            "INSERT OR REPLACE INTO repo_verdict (repo, cluster_hash, verdict, reason) "
            "VALUES (?, ?, ?, ?)",
            [(k, cluster_hash, v, "") for k, v in cap.items()],
        )
        await db.commit()
    return {"verdicts": verdicts, "cluster_hash": cluster_hash,
            "counts": _tally(verdicts, cluster_map)}


async def _load_cluster_map(session_id: str) -> tuple[dict[str, str], str]:
    """Return ({repo_name: cluster_label}, hash_of_result_json) from the saved
    cluster_result. Hash is what the verdict cache is keyed on."""
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT result FROM cluster_result WHERE session_id = ?",
            (session_id,))
    if not rows:
        return {}, ""
    raw = rows[0]["result"]
    try:
        payload = json.loads(raw)
    except Exception:
        return {}, ""
    out: dict[str, str] = {}
    for cl in payload.get("clusters", []):
        for m in cl.get("members", []):
            out[m.get("repo") or ""] = cl.get("suggested_name", "")
    return out, hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _tally(verdicts: dict[str, str], cluster_map: dict[str, str]) -> dict[str, int]:
    counts = {"fit": 0, "drift": 0, "mis-clustered": 0, "skipped": 0}
    for k in cluster_map:
        v = verdicts.get(k, "")
        if v in counts:
            counts[v] += 1
        else:
            counts["skipped"] += 1
    return counts


@router.get("/scan/distill/verdicts/{session_id}")
async def verdicts_for(session_id: str):
    """Return cached verdicts for the CURRENT cluster hash, plus the hash so
    the UI can tell when it's stale (clustering was re-run, verdicts gone)."""
    await require_session(session_id)
    cluster_map, cluster_hash = await _load_cluster_map(session_id)
    if not cluster_hash:
        return {"cluster_hash": "", "verdicts": {}}
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT repo, verdict FROM repo_verdict WHERE cluster_hash = ?",
            (cluster_hash,))
    return {"cluster_hash": cluster_hash,
            "verdicts": {r["repo"]: r["verdict"] for r in rows}}