import json
import os
from anthropic import AsyncAnthropic

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


async def extract_features(url: str, content: str) -> tuple[str, list[str]]:
    """
    Send scraped page content to Claude and return (product_name, [features]).
    """
    prompt = f"""You are extracting structured product information from a webpage.

URL: {url}

Scraped content (truncated to first 6000 chars):
{content[:6000]}

Return ONLY a JSON object with exactly this structure — no markdown, no explanation:
{{
  "name": "Product or company name",
  "features": [
    "concrete feature or capability",
    "another feature"
  ]
}}

Rules:
- Max 12 features
- Each feature is one short sentence describing a concrete capability
- No marketing fluff ("best-in-class", "powerful", etc.)
- If the page is not a product page, return {{"name": "Unknown", "features": []}}
"""
    client = _get_client()
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)
    return data["name"], data.get("features", [])
