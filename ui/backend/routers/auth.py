import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db
from services.github import validate_token

log = logging.getLogger(__name__)
router = APIRouter()

# Common Windows install locations for the gh CLI
_GH_FALLBACKS = [
    r"C:\Program Files\GitHub CLI\gh.exe",
    r"C:\Program Files (x86)\GitHub CLI\gh.exe",
    Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "gh.exe",
    Path.home() / "scoop" / "shims" / "gh.exe",
    r"C:\ProgramData\chocolatey\bin\gh.exe",
]


def _find_gh() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    for p in _GH_FALLBACKS:
        if Path(p).exists():
            return str(p)
    return None


class LoginRequest(BaseModel):
    token: str


class LoginResponse(BaseModel):
    session_id: str
    github_user: str
    avatar_url: str


@router.get("/gh-token")
async def get_gh_token():
    """Return token from GH_TOKEN env or gh CLI."""
    env_token = os.environ.get("GH_TOKEN", "")
    if env_token:
        log.info("gh-token: returning GH_TOKEN from environment")
        return {"token": env_token, "source": "env"}

    gh = _find_gh()
    if not gh:
        log.warning("gh-token: gh CLI not found")
        raise HTTPException(
            status_code=404,
            detail="gh CLI not found. Install from https://cli.github.com or set GH_TOKEN env var.",
        )

    log.info("gh-token: running %s auth token", gh)
    try:
        result = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=5)
        token = result.stdout.strip()
        if not token:
            raise HTTPException(status_code=404, detail="gh CLI found but not authenticated — run: gh auth login")
        return {"token": token, "source": "gh-cli"}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="gh CLI timed out")


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    try:
        user = await validate_token(body.token)
    except Exception as exc:
        log.warning("login failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid GitHub token")

    session_id = str(uuid.uuid4())
    async for db in get_db():
        # repos_root is a dead column (app is remote-only) but stays NOT NULL on
        # existing DBs, so keep passing "" — dropping it breaks login on old DBs.
        await db.execute(
            "INSERT INTO session (id, github_token, github_user, repos_root) VALUES (?, ?, ?, ?)",
            (session_id, body.token, user["login"], ""),
        )
        await db.commit()

    log.info("session created for %s  id=%s", user["login"], session_id)
    return LoginResponse(
        session_id=session_id,
        github_user=user["login"],
        avatar_url=user.get("avatar_url", ""),
    )


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    async for db in get_db():
        row = await db.execute_fetchall(
            "SELECT github_user FROM session WHERE id = ?", (session_id,)
        )
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"github_user": row[0]["github_user"]}
