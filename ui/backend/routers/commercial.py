import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

from database import get_db
from services.scraper import scrape
from services.claude_ai import extract_features

router = APIRouter()


class ScrapeRequest(BaseModel):
    hub: str
    url: str


@router.post("/commercial/scrape")
async def scrape_and_extract(body: ScrapeRequest):
    log.info("scraping %s for hub=%s", body.url, body.hub)
    try:
        content = await scrape(body.url)
    except Exception as exc:
        log.error("scrape failed %s: %s", body.url, exc)
        raise HTTPException(status_code=502, detail=f"Scrape failed: {exc}")

    log.debug("scraped %d chars, extracting features via Claude", len(content))
    try:
        name, features = await extract_features(body.url, content)
    except Exception as exc:
        log.error("feature extraction failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Feature extraction failed: {exc}")

    log.info("extracted %d features for '%s'", len(features), name)

    async for db in get_db():
        await db.execute(
            "INSERT INTO commercial_refs (hub, url, name, features) VALUES (?, ?, ?, ?)",
            (body.hub, body.url, name, json.dumps(features)),
        )
        await db.commit()
        row = await db.execute_fetchall(
            "SELECT id FROM commercial_refs WHERE hub = ? AND url = ? ORDER BY id DESC LIMIT 1",
            (body.hub, body.url),
        )
        ref_id = row[0]["id"] if row else None

    return {"id": ref_id, "name": name, "features": features}


@router.get("/commercial/{hub}")
async def list_refs(hub: str):
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT id, url, name, features, added_at FROM commercial_refs WHERE hub = ? ORDER BY id",
            (hub,),
        )
    return [
        {
            "id": r["id"],
            "url": r["url"],
            "name": r["name"],
            "features": json.loads(r["features"]),
            "added_at": r["added_at"],
        }
        for r in rows
    ]


@router.delete("/commercial/{ref_id}")
async def delete_ref(ref_id: int):
    async for db in get_db():
        await db.execute("DELETE FROM commercial_refs WHERE id = ?", (ref_id,))
        await db.commit()
    return {"deleted": ref_id}
