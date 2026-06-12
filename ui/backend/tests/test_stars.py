"""stars: token-overlap dedup, semantic path gating, snapshot endpoints."""
import asyncio
import json

from services import stars as stars_svc


def _star(full_name, description="", topics=None, **kw):
    name = full_name.split("/")[-1]
    return {"full_name": full_name, "name": name, "description": description,
            "topics": topics or [], "language": kw.get("language", ""),
            "stars": kw.get("stars", 0), "url": f"https://github.com/{full_name}"}


def test_kw_score_overlap():
    a = stars_svc._tokens("photo manager self-hosted gallery")
    b = stars_svc._tokens("self-hosted photo gallery backup")
    assert stars_svc._kw_score(a, b) > 0.5
    assert stars_svc._kw_score(a, set()) == 0.0


def test_keyword_dedup_flags_duplicate():
    owned = [{"name": "restorePhotos", "aim": "AI photo restoration tool",
              "topics": ["photos", "restoration"], "verdict": "keep", "hub": None}]
    stars = [
        _star("upscayl/upscayl", "AI photo restoration and upscaling",
              topics=["photos", "restoration", "upscaling"], stars=30000),
        _star("traefik/traefik", "Cloud native reverse proxy", topics=["proxy"]),
    ]
    dups, _ = stars_svc._keyword(owned, stars, {})
    assert len(dups) == 1
    assert dups[0]["repo"] == "restorePhotos"
    names = [m["full_name"] for m in dups[0]["matches"]]
    assert "upscayl/upscayl" in names
    assert "traefik/traefik" not in names


def test_keyword_hub_suggestions():
    hubs = {"media-hub": {"description": "Unified media ingestion — photos and video",
                          "boundary": "Media content management: photos, video, archives."}}
    stars = [
        _star("immich-app/immich", "Self-hosted photo and video management",
              topics=["photos", "video", "media"], stars=40000),
        _star("rust-lang/rust", "The Rust language", topics=["compiler"]),
    ]
    _, sugg = stars_svc._keyword([], stars, hubs)
    assert "media-hub" in sugg
    names = [m["full_name"] for m in sugg["media-hub"]]
    assert "immich-app/immich" in names
    assert "rust-lang/rust" not in names


def test_dedup_falls_back_to_keyword(monkeypatch):
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: False)
    res = asyncio.run(stars_svc.dedup(
        [{"name": "x", "aim": "", "topics": [], "verdict": "keep", "hub": None}],
        [_star("a/b", "something")], {},
    ))
    assert res["method"] == "keyword"


def test_dedup_empty_without_snapshot():
    res = asyncio.run(stars_svc.dedup([{"name": "x"}], [], {}))
    assert res == {"method": None, "duplicates": [], "hub_suggestions": {}}


def test_dedup_sorted_strongest_first(monkeypatch):
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: False)
    owned = [
        {"name": "weak-overlap", "aim": "photo tool extras misc",
         "topics": ["photos"], "verdict": "keep", "hub": None},
        {"name": "photo-gallery", "aim": "self-hosted photo gallery",
         "topics": ["photos", "gallery"], "verdict": "keep", "hub": None},
    ]
    stars = [_star("immich-app/immich", "self-hosted photo gallery",
                   topics=["photos", "gallery"])]
    res = asyncio.run(stars_svc.dedup(owned, stars, {}))
    if len(res["duplicates"]) > 1:
        scores = [d["matches"][0]["score"] for d in res["duplicates"]]
        assert scores == sorted(scores, reverse=True)
    assert res["duplicates"][0]["repo"] == "photo-gallery"


def test_stars_endpoints_snapshot_and_dedup(temp_db, isolated_plan, monkeypatch):
    """starred_repo rows round-trip through /stars and /stars/dedup (keyword)."""
    from routers import stars as stars_router
    from services import embeddings
    from tests.conftest import insert_scan

    monkeypatch.setattr(embeddings, "has_embeddings", lambda: False)
    session_id, _ = insert_scan(temp_db, repos=[
        {"name": "photo-gallery", "aim": "self-hosted photo gallery"},
    ])

    async def _seed_stars():
        async for db in temp_db.get_db():
            await db.execute(
                """INSERT INTO starred_repo
                   (full_name, name, owner, description, topics, language,
                    stars, pushed_at, archived, url)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                ("immich-app/immich", "immich", "immich-app",
                 "self-hosted photo gallery", json.dumps(["photos", "gallery"]),
                 "TypeScript", 40000, "", 0, "https://github.com/immich-app/immich"),
            )
            await db.commit()

    asyncio.run(_seed_stars())

    listing = asyncio.run(stars_router.get_stars())
    assert listing["count"] == 1
    assert listing["stars"][0]["topics"] == ["photos", "gallery"]

    res = asyncio.run(stars_router.stars_dedup(session_id))
    assert res["available"] is True
    assert res["method"] == "keyword"
    assert any(d["repo"] == "photo-gallery" for d in res["duplicates"])


def test_dedup_unavailable_without_snapshot(temp_db, isolated_plan):
    from routers import stars as stars_router
    res = asyncio.run(stars_router.stars_dedup("nope"))
    assert res["available"] is False
