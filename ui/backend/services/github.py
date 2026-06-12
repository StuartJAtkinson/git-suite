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


async def list_repos(token: str, username: str | None = None) -> AsyncIterator[dict]:
    """Yield every repo the authenticated user OWNS, including private ones.

    Uses /user/repos (not /users/{username}/repos, which returns public repos
    only) so the scan, reconcile, and execute see the full portfolio.
    """
    async with httpx.AsyncClient() as client:
        page = 1
        while True:
            r = await client.get(
                f"{GH_API}/user/repos",
                headers=_headers(token),
                params={"per_page": 100, "page": page,
                        "affiliation": "owner", "visibility": "all"},
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


async def list_starred(token: str) -> AsyncIterator[dict]:
    """Yield every repo the authenticated user has starred."""
    async with httpx.AsyncClient() as client:
        page = 1
        while True:
            r = await client.get(
                f"{GH_API}/user/starred",
                headers=_headers(token),
                params={"per_page": 100, "page": page},
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


async def unarchive_repo(token: str, owner: str, repo: str) -> None:
    """Un-archive ('return') a repo via the GitHub API."""
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{GH_API}/repos/{owner}/{repo}",
            headers=_headers(token),
            json={"archived": False},
        )
        r.raise_for_status()


async def delete_repo(token: str, owner: str, repo: str) -> None:
    """Delete a repo. Requires the PAT to have the `delete_repo` scope."""
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{GH_API}/repos/{owner}/{repo}",
            headers=_headers(token),
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


async def get_file(token: str, owner: str, repo: str, path: str) -> dict | None:
    """Return {'content': str, 'sha': str} for a file, or None if absent."""
    import base64
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GH_API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(token),
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        return {
            "content": base64.b64decode(data["content"]).decode("utf-8"),
            "sha": data["sha"],
        }


async def get_readme(token: str, owner: str, repo: str, limit: int = 2000) -> str | None:
    """Return the repo's README text (excerpt), or None. Uses the readme endpoint
    so it finds README.md / README.rst / etc. regardless of name."""
    import base64
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{GH_API}/repos/{owner}/{repo}/readme",
            headers=_headers(token),
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        try:
            text = base64.b64decode(r.json()["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None
        return text[:limit]


async def create_repo(token: str, name: str, private: bool = True, description: str = "") -> dict:
    """Create a repo under the authenticated user. auto_init gives it a first commit."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{GH_API}/user/repos",
            headers=_headers(token),
            json={"name": name, "private": private, "description": description, "auto_init": True},
        )
        r.raise_for_status()
        return r.json()
