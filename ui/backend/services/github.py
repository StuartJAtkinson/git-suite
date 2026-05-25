import httpx
from typing import AsyncIterator

GH_API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def validate_token(token: str) -> dict:
    """Return user dict from /user or raise httpx.HTTPStatusError."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GH_API}/user", headers=_headers(token))
        r.raise_for_status()
        return r.json()


async def list_repos(token: str, username: str) -> AsyncIterator[dict]:
    """Yield every repo for username, handling pagination."""
    async with httpx.AsyncClient() as client:
        page = 1
        while True:
            r = await client.get(
                f"{GH_API}/users/{username}/repos",
                headers=_headers(token),
                params={"per_page": 100, "page": page, "type": "all"},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for repo in batch:
                yield repo
            if len(batch) < 100:
                break
            page += 1


async def archive_repo(token: str, owner: str, repo: str) -> None:
    """Archive a repo via the GitHub API."""
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{GH_API}/repos/{owner}/{repo}",
            headers=_headers(token),
            json={"archived": True},
        )
        r.raise_for_status()


async def push_file(
    token: str,
    owner: str,
    repo: str,
    path: str,
    content_b64: str,
    message: str,
    sha: str | None = None,
) -> None:
    """Create or update a file in a repo via the Contents API."""
    payload: dict = {"message": message, "content": content_b64}
    if sha:
        payload["sha"] = sha
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{GH_API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(token),
            json=payload,
        )
        r.raise_for_status()


async def get_file_sha(token: str, owner: str, repo: str, path: str) -> str | None:
    """Return the current SHA of a file, or None if it doesn't exist."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GH_API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(token),
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()["sha"]
