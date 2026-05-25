import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

from database import get_db
from services.github import validate_token

router = APIRouter()


class LoginRequest(BaseModel):
    token: str
    repos_root: str


class LoginResponse(BaseModel):
    session_id: str
    github_user: str
    avatar_url: str


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
