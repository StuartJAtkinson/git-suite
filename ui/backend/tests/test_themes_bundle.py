"""themes_bundle: owned + starred repos both flow into the raw bundle, and
the prompt-facing identifier is disambiguated (full_name for stars, bare
name for owned) so same-named stars from different owners never collide."""
import asyncio

from services import themes_bundle


def test_build_raw_bundle_includes_owned_and_stars(temp_db, monkeypatch):
    """The bundle covers BOTH sources, each correctly tagged — this is the
    actual bug that was fixed: build_raw_bundle used to hardcode
    source='owned' on everything and never looked at starred_repo at all."""
    async def fake_require_session(session_id):
        return {"github_token": "tok", "github_user": "tester"}
    monkeypatch.setattr(themes_bundle, "require_session", fake_require_session)

    async def fake_reconcile(session_id):
        return {"repos": [
            {"name": "owned-repo", "aim": "does a thing", "topics": [],
             "url": "https://github.com/tester/owned-repo", "stars": 3},
        ]}
    import routers.reconcile as reconcile_mod
    monkeypatch.setattr(reconcile_mod, "reconcile", fake_reconcile)

    async def fake_load_stars():
        return [{"full_name": "someorg/starred-thing", "name": "starred-thing",
                 "description": "a starred thing", "topics": [], "stars": 10,
                 "url": "https://github.com/someorg/starred-thing"}]
    import routers.stars as stars_mod
    monkeypatch.setattr(stars_mod, "_load_stars", fake_load_stars)

    async def fake_fetch_readme(token, owner, repo, max_chars=200_000):
        return f"README for {owner}/{repo}"
    monkeypatch.setattr(themes_bundle, "_fetch_full_readme", fake_fetch_readme)

    bundle = asyncio.run(themes_bundle.build_raw_bundle("s1"))
    by_name = {b["name"]: b for b in bundle}

    assert by_name["owned-repo"]["source"] == "owned"
    assert by_name["owned-repo"]["full_name"] == "tester/owned-repo"
    assert "README for tester/owned-repo" == by_name["owned-repo"]["readme"]

    assert by_name["starred-thing"]["source"] == "star"
    assert by_name["starred-thing"]["full_name"] == "someorg/starred-thing"
    assert "README for someorg/starred-thing" == by_name["starred-thing"]["readme"]


def test_to_prompt_records_disambiguates_star_identifier():
    """Owned repos keep their bare name as the LLM-facing id (unique within
    one account); stars use full_name (bare names collide across owners)."""
    artefact = {"bundle": [
        {"name": "owned-repo", "full_name": "tester/owned-repo", "source": "owned",
         "purpose": "", "entities": [], "domain": "", "topics": [], "stars": 0,
         "description": ""},
        {"name": "server", "full_name": "alice/server", "source": "star",
         "purpose": "", "entities": [], "domain": "", "topics": [], "stars": 0,
         "description": ""},
        {"name": "server", "full_name": "bob/server", "source": "star",
         "purpose": "", "entities": [], "domain": "", "topics": [], "stars": 0,
         "description": ""},
    ]}
    records = themes_bundle.to_prompt_records(artefact)
    ids = [r["name"] for r in records]
    assert ids == ["owned-repo", "alice/server", "bob/server"]
    assert len(set(ids)) == 3   # no collision between the two "server" stars
