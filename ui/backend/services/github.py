import asyncio
import base64
import time
import httpx
from typing import AsyncIterator

GH_API = "https://api.github.com"


class GitHubAuthError(Exception):
    """A genuine 401/403 (bad token or missing scope) — NOT throttling."""


class GitHubRateLimitError(Exception):
    """The token is valid but GitHub is throttling right now (primary or
    secondary rate limit) — wait and retry, do NOT report as 'invalid token'."""


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "git-suite/1.0",
    }


# ── rate-limit handling (ported from homelab-designer/backend/scrapers/base.py)

def _rate_limit_wait(resp: httpx.Response) -> float | None:
    """Seconds to sleep if `resp` is a rate-limit response, else None.

      429                              → Retry-After (secondary) or 60s
      403 + Retry-After               → secondary rate limit
      403 + X-RateLimit-Remaining: 0  → primary rate limit → until reset
      403 + body mentions rate limit  → same
      403 otherwise                   → None (genuine auth/permission failure)
    """
    if resp.status_code == 429:
        retry = resp.headers.get("Retry-After")
        return (max(1, int(retry)) + 1) if retry else 60.0
    if resp.status_code != 403:
        return None
    retry = resp.headers.get("Retry-After")
    if retry:
        return max(1, int(retry)) + 1
    if resp.headers.get("X-RateLimit-Remaining") == "0":
        reset = int(resp.headers.get("X-RateLimit-Reset", 0))
        return max(5.0, reset - time.time() + 2)
    try:
        msg = (resp.json().get("message") or "").lower()
        if "rate limit" in msg or "secondary" in msg or "api rate" in msg:
            reset = int(resp.headers.get("X-RateLimit-Reset", 0))
            return max(5.0, reset - time.time() + 2) if reset else 60.0
    except Exception:
        pass
    return None


def _quota_sleep(resp: httpx.Response) -> float:
    """Pre-emptive sleep (capped) when the remaining quota is getting low, so a
    burst tapers off before it trips the primary limit."""
    try:
        remaining = int(resp.headers.get("X-RateLimit-Remaining", 999))
    except ValueError:
        return 0.0
    if remaining < 50:
        reset = int(resp.headers.get("X-RateLimit-Reset", 0))
        return max(0.0, min(120.0, reset - time.time() + 2))
    return 0.0


async def gh_get(client: httpx.AsyncClient, url: str, token: str,
                 params: dict | None = None) -> httpx.Response:
    """Rate-aware GitHub GET. Backs off on 403/429 (primary + secondary) and
    5xx, raises GitHubAuthError on a real 401/403, and pre-emptively slows near
    the quota. Returns the successful response."""
    for attempt in range(6):
        try:
            resp = await client.get(url, headers=_headers(token),
                                    params=params, timeout=30)
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt >= 5:
                raise
            await asyncio.sleep(2 ** min(attempt, 4))
            continue
        if resp.status_code in (403, 429):
            wait = _rate_limit_wait(resp)
            if wait is not None:
                await asyncio.sleep(min(wait, 300))
                continue
            raise GitHubAuthError(
                f"GitHub denied access (HTTP {resp.status_code}) — check the "
                f"token's scopes (needs repo + read:user).")
        if resp.status_code == 401:
            raise GitHubAuthError("GitHub token invalid or expired (HTTP 401).")
        if resp.status_code in (500, 502, 503, 504):
            await asyncio.sleep(2 ** min(attempt, 4))
            continue
        resp.raise_for_status()
        s = _quota_sleep(resp)
        if s:
            await asyncio.sleep(s)
        return resp
    raise GitHubAuthError("GitHub kept rate-limiting after retries — try again "
                          "in a minute.")


async def validate_token(token: str) -> dict:
    """Return the /user dict. Distinguishes a real auth failure (401, or 403
    with no rate-limit signal) from GitHub throttling (raises
    GitHubRateLimitError) — so a rate limit never masquerades as 'invalid token'."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{GH_API}/user", headers=_headers(token))
    if r.status_code in (403, 429) and _rate_limit_wait(r) is not None:
        raise GitHubRateLimitError(
            "GitHub is rate-limiting this token right now — wait a few minutes "
            "and try again. The token itself is fine.")
    if r.status_code == 401:
        raise GitHubAuthError("Invalid or expired GitHub token.")
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
            r = await gh_get(client, f"{GH_API}/user/repos", token,
                             params={"per_page": 100, "page": page,
                                     "affiliation": "owner", "visibility": "all"})
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
            r = await gh_get(client, f"{GH_API}/user/starred", token,
                             params={"per_page": 100, "page": page})
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
