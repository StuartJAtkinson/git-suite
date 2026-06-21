import httpx
from bs4 import BeautifulSoup


async def scrape(url: str) -> str:
    """Return cleaned text content from url."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        r = await client.get(url, headers={"User-Agent": "git-suite-bot/1.0"})
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)
