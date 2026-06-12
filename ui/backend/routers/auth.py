import logging
import os
import shutil
import string
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
    # Optional by design: stored only as a future clone/migration target —
    # it never sources, qualifies, or classifies a repo.
    repos_root: str = ""


class LoginResponse(BaseModel):
    session_id: str
    github_user: str
    avatar_url: str


# tkinter must own the main thread, so run the dialog in a throwaway
# subprocess rather than inside the async event loop (which 502s).
_PICKER_SCRIPT = (
    "import tkinter as tk\n"
    "from tkinter.filedialog import askdirectory\n"
    "r = tk.Tk(); r.withdraw(); r.wm_attributes('-topmost', True)\n"
    "p = askdirectory(title='Select repos folder')\n"
    "r.destroy()\n"
    "print(p or '')\n"
)


@router.post("/pick-folder")
async def pick_folder():
    """Open the native OS folder dialog on the server and return the selected path.

    Runs tkinter in a separate Python process so it has its own main thread and
    never blocks/crashes the uvicorn event loop.
    """
    import asyncio
    import sys
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", _PICKER_SCRIPT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Folder dialog unavailable: {exc}")
    if proc.returncode != 0:
        raise HTTPException(status_code=500,
                            detail=f"Folder dialog failed: {err.decode(errors='replace')[:200]}")
    return {"path": out.decode(errors="replace").strip()}  # "" if cancelled


@router.get("/browse")
async def browse(path: str = ""):
    """List subdirectories at path. Called by the folder picker modal."""
    if not path:
        if os.name == "nt":
            entries = []
            for d in string.ascii_uppercase:
                p = Path(f"{d}:\\")
                try:
                    if p.exists():
                        entries.append({"name": f"{d}:\\", "path": f"{d}\\"})
                except OSError:
                    pass
            return {"path": "", "parent": None, "entries": entries}
        path = str(Path.home())

    p = Path(path)
    try:
        if not p.is_dir():
            raise HTTPException(status_code=404, detail=f"Not a directory: {path}")
        entries = sorted(
            [{"name": d.name, "path": str(d)} for d in p.iterdir()
             if d.is_dir() and not d.name.startswith(".")],
            key=lambda x: x["name"].lower(),
        )
        parent = str(p.parent) if str(p.parent) != str(p) else None
        return {"path": str(p), "parent": parent, "entries": entries}
    except HTTPException:
        raise
    except OSError:
        parent = str(p.parent) if str(p.parent) != str(p) else None
        return {"path": str(p), "parent": parent, "entries": []}


@router.get("/search-folder")
async def search_folder(name: str):
    """Find a folder by exact name — called after the browser file picker."""
    candidates: list[Path] = []
    if os.name == "nt":
        for d in string.ascii_uppercase:
            candidates.append(Path(f"{d}:/{name}"))
    home = Path.home()
    candidates += [home / name, home / "GitHub" / name, home / "git" / name]
    for c in candidates:
        try:
            if c.exists() and c.is_dir():
                log.info("search-folder: found '%s' at %s", name, c)
                return {"path": str(c)}
        except OSError:
            pass
    return {"path": None}


@router.get("/path-complete")
async def path_complete(prefix: str = ""):
    """Return up to 20 directory completions for the path input datalist."""
    if not prefix:
        if os.name == "nt":
            return [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
        return [str(Path.home())]

    p = Path(prefix)
    try:
        # If prefix ends with a separator (or is an existing dir), list children
        if p.is_dir() and (prefix.endswith("/") or prefix.endswith("\\")):
            entries = sorted(p.iterdir())
            return [str(p / d.name) for d in entries if d.is_dir() and not d.name.startswith(".")][:20]
        # Otherwise list siblings whose name starts with the typed stem
        if p.parent.is_dir():
            stem = p.name.lower()
            entries = sorted(p.parent.iterdir())
            return [
                str(p.parent / d.name)
                for d in entries
                if d.is_dir() and not d.name.startswith(".") and d.name.lower().startswith(stem)
            ][:20]
    except (PermissionError, OSError):
        pass
    return []


@router.get("/defaults")
async def get_defaults():
    """Return server-side detected defaults so the login form can pre-fill."""
    gh_token = os.environ.get("GH_TOKEN", "")

    candidates = [
        Path("H:/GitHub"),
        Path("C:/GitHub"),
        Path.home() / "GitHub",
        Path.home() / "git",
        Path.home() / "repos",
        Path.home() / "code",
    ]
    repos_root = str(Path.home() / "GitHub")
    for c in candidates:
        if c.exists():
            repos_root = str(c)
            break

    return {"repos_root": repos_root, "has_env_token": bool(gh_token)}


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
