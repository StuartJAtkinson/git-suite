import logging
import os
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_db
from services.github import validate_token

log = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    token: str
    repos_root: str


class LoginResponse(BaseModel):
    session_id: str
    github_user: str
    avatar_url: str


@router.get("/find-path")
async def find_path(name: str, hint: str = ""):
    """Resolve a folder name to a full path. Called after showDirectoryPicker()."""
    import os, string

    candidates: list[Path] = []

    # 1. Relative to hint (user's current repos_root or its parent)
    if hint:
        h = Path(hint)
        candidates += [h / name, h.parent / name, h.parent.parent / name]

    # 2. Common home-relative locations
    home = Path.home()
    for parent in (home, home / "GitHub", home / "git", home / "repos", home / "code"):
        candidates.append(parent / name)

    # 3. Scan every drive root on Windows — catches H:\GitHub, D:\projects etc.
    if os.name == "nt":
        for d in string.ascii_uppercase:
            candidates.append(Path(f"{d}:/{name}"))

    for c in candidates:
        try:
            if c.exists() and c.is_dir():
                log.info("find-path: resolved '%s' -> %s", name, c)
                return {"path": str(c)}
        except OSError:
            pass

    log.warning("find-path: could not resolve '%s' (hint=%s)", name, hint)
    return {"path": None}


@router.get("/defaults")
async def get_defaults():
    """Return server-side detected defaults so the login form can pre-fill."""
    # Check env first (covers infisical run / .env injection)
    gh_token = os.environ.get("GH_TOKEN", "")

    # Detect repos root: walk common locations, return first that exists
    candidates = [
        Path("H:/GitHub"),
        Path("C:/GitHub"),
        Path.home() / "GitHub",
        Path.home() / "git",
        Path.home() / "repos",
        Path.home() / "code",
    ]
    repos_root = str(Path.home() / "GitHub")  # sensible fallback
    for c in candidates:
        if c.exists():
            repos_root = str(c)
            break

    return {"repos_root": repos_root, "has_env_token": bool(gh_token)}


@router.get("/gh-token")
async def get_gh_token():
    """Return the token from `gh auth token` if the gh CLI is authenticated."""
    # Also accept GH_TOKEN env var (set by infisical or .env)
    env_token = os.environ.get("GH_TOKEN", "")
    if env_token:
        log.info("gh-token: returning GH_TOKEN from environment")
        return {"token": env_token, "source": "env"}

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5,
        )
        token = result.stdout.strip()
        if not token:
            raise HTTPException(status_code=404, detail="gh CLI is not authenticated — run: gh auth login")
        log.info("gh-token: returning token from gh CLI")
        return {"token": token, "source": "gh-cli"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="gh CLI not found and GH_TOKEN env var not set")
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
        await db.execute(
            "INSERT INTO session (id, github_token, github_user, repos_root) VALUES (?, ?, ?, ?)",
            (session_id, body.token, user["login"], body.repos_root),
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
            "SELECT github_user, repos_root FROM session WHERE id = ?", (session_id,)
        )
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        r = row[0]
        return {"github_user": r["github_user"], "repos_root": r["repos_root"]}
