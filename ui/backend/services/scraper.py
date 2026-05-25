import httpx
from bs4 import BeautifulSoup

# crawl4ai is the preferred scraper but requires a playwright install.
# This module tries crawl4ai first and falls back to httpx + BeautifulSoup.

_crawl4ai_available: bool | None = None


def _check_crawl4ai() -> bool:
    global _crawl4ai_available
    if _crawl4ai_available is None:
        try:
            import crawl4ai  # noqa: F401
            _crawl4ai_available = True
        except ImportError:
            _crawl4ai_available = False
    return _crawl4ai_available


async def _scrape_crawl4ai(url: str) -> str:
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        return result.markdown or result.cleaned_html or ""


async def _scrape_simple(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        r = await client.get(url, headers={"User-Agent": "git-suite-bot/1.0"})
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


async def scrape(url: str) -> str:
    """Return cleaned text content from url."""
    if _check_crawl4ai():
        try:
            return await _scrape_crawl4ai(url)
        except Exception:
            pass
    return await _scrape_simple(url)
