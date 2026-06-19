from services import llm


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
    data = await llm.complete_json(prompt, max_tokens=1024)
    return data["name"], data.get("features", [])
