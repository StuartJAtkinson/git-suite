"""Shared fixtures. Tests isolate plan.json and state.db into tmp dirs so they
never touch the real ~/.git-suite or the live state.db."""
import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# Test-only sample plan. Production has NO seed (plan_store._seed_plan() is empty
# and hubs come only from the live GitHub scan); this realistic plan lives here
# purely so tests have hubs/absorbs to exercise the logic against. It is not
# wired into the app.
_SAMPLE_HUBS = {
    "personal-ai-os": {"description": "Unified local AI OS",
                       "boundary": "Personal AI: RAG, memory, agents. Excludes work tooling.",
                       "absorbs": ["quivr", "EMailParseAI", "heart-on-a-sleeve", "gsd-work",
                                   "LangFlowProject", "Multi-agent-DataAnalysis", "MultiCoT", "STTScrape"],
                       "alternatives": {"oss": ["Jan", "anything-llm"], "commercial": ["ChatGPT"]}},
    "ontology-align": {"description": "Aligns ontological schemas",
                       "boundary": "Formal ontologies and semantic alignment. Excludes map rendering.",
                       "absorbs": ["place-time", "ontologiesUK", "CommonCoreOntologies", "federated-api-model",
                                   "IAO", "Sagex3-Script-Parser", "UKPoliticsData", "neo4J-SQL-Graphs"],
                       "alternatives": {"oss": ["Protege", "RDFLib"], "commercial": ["Stardog"]}},
    "homelab-core": {"description": "Self-hosted infrastructure control plane",
                     "boundary": "Deployment & infrastructure. Excludes work management.",
                     "absorbs": ["homelab-designer", "homelab-discovery", "infisical", "orchestration-stack",
                                 "ai-work-orchestration", "winutil", "linutil", "fusio"],
                     "alternatives": {"oss": ["Portainer", "Coolify"], "commercial": ["Doppler"]}},
    "work-hub": {"description": "Self-hosted professional work management",
                 "boundary": "Professional work: tickets, CRM, projects. Excludes personal GTD.",
                 "absorbs": ["guided-tickets", "jira-dependency-graph", "ZohoAPI", "Jira-Lens"],
                 "alternatives": {"oss": ["Vikunja", "Plane"], "commercial": ["Jira"]}},
    "media-hub": {"description": "Unified media ingestion",
                  "boundary": "Media content ingestion. Excludes game-specific data.",
                  "absorbs": ["socialMediaArchiver", "YouTubeCommunityPosts", "simklExporter",
                              "CBL-ReadingLists", "marvel-comics-api", "EXIF-SpaceTime", "tweetext",
                              "comictagger", "linkedin-api", "TagStudio", "ClipsReview",
                              "autoEdit_2", "intelli-video", "AIPhotoRestore"],
                  "alternatives": {"oss": ["Immich", "Jellyfin"], "commercial": ["Plex"]}},
    "map-suite": {"description": "OSM-based unified mapping",
                  "boundary": "Spatial rendering & map platforms. Excludes spatial ontology.",
                  "absorbs": ["qgis-mcp", "Fantasy-Map-Generator", "planetiler", "OSM2World",
                              "streets-gl", "openindoor6", "OsmGo", "worldengine"],
                  "alternatives": {"oss": ["QGIS", "Leaflet"], "commercial": ["Mapbox"]}},
    "game-hub": {"description": "Unified gaming platform",
                 "boundary": "Game-specific data and toolkits. Excludes general media.",
                 "absorbs": ["FFXIVQuestMap", "FFXIVAPI", "AllaganTools", "Lumina", "XIVSlothCombo",
                             "PokeManager", "Pokedex-RL", "ZeldaRecipes", "BOTW-Recipes",
                             "BlossomsPokemonGoManager", "Pogo-Account-Checker", "GoDex", "PokemonGo-Bot",
                             "botw-tools", "d4buildsAPI", "gwSkills", "DungeonGeneration",
                             "Chronicle-Keeper", "foundryvtt-session-scheduler", "dnd-aMagaAdventure", "Armoria"],
                 "alternatives": {"oss": ["Playnite", "Foundry VTT"], "commercial": ["Steam"]}},
    "code-suite": {"description": "Unified code management",
                   "boundary": "Developer/code tooling. Excludes AI agent frameworks.",
                   "absorbs": ["DoIHaveEverything", "Coding-Cheatsheets", "CodeAtlasVsix", "SQLFluffParsing",
                               "ClickTheseThings", "Page-Manipulator", "RepoReader", "bytebytego-grabber",
                               "bloop", "all-repos", "astral"],
                   "alternatives": {"oss": ["Gitea", "aider"], "commercial": ["GitHub"]}},
    "creative-hub": {"description": "Generative & live visual creative tools",
                     "boundary": "Creative/generative visual work. Excludes media archiving.",
                     "absorbs": ["VTuberLIVE"],
                     "alternatives": {"oss": [], "commercial": []}},
}
_SAMPLE_ARCHIVES = {
    "belzona-tickets": "work-hub", "JiraApp": "work-hub", "FFXIV-Scraping": "game-hub",
    "FFXIVPlugin": "game-hub", "InteractiveMaps": "game-hub", "Tetra-Master-Clone": "game-hub",
    "TownGeneratorOS": "game-hub", "botwr": "game-hub", "donjonrp": "game-hub",
    "dummy-sheet": "game-hub", "ClipsReview": "media-hub", "TagStudio": "media-hub",
    "restorePhotos": "media-hub", "twitterscraper": "media-hub", "mRemoteNG": "homelab-core",
    "linutil": "homelab-core", "Ontologies": "ontology-align", "opencyc": "ontology-align",
    "html-tree-generator__chrome-extension": "code-suite", "UsefulCodeToMakeGists": "code-suite",
    "Newtonian-Particle-Simulator": None, "MarvelGraph": None, "prettymaps": None,
    "webmapper": None, "FreshView": None, "ReverseYoutubePlaylist": None, "infranodus": None,
    "John-Watson-Guides": None, "MTGScrape": None, "SteamScrape": None, "ChronoZoom": None,
    "chromeos-apk": None, "windows95": None, "esoteric-streamer": None, "nouns-ai-sd-server": None,
    "pc-part-dataset": None, "ai-demos": None,
}
_SAMPLE_KEEPS = sorted({
    "xivapi.com", "AncestryBrowsableSchema", "FTAnalyzer", "wikitree-sourcer", "Archon",
    "OpenDevin", "crawl4ai", "portia", "headless-recorder", "rag-from-scratch",
    "aw-import-ical", "aw-watcher-ask", "GoJS", "jsoncrack.com", "venn.js",
    "segment-anything", "YouTubeExtension", "free-map-genie", "git-suite",
})


def _sample_plan() -> dict:
    """A fresh deep-ish copy of the test sample plan (priority unset = emergent)."""
    return {
        "hubs": {name: {"priority": None, **{k: (list(v) if isinstance(v, list) else
                  ({"oss": list(v["oss"]), "commercial": list(v["commercial"])}
                   if isinstance(v, dict) else v))
                  for k, v in meta.items()}}
                 for name, meta in _SAMPLE_HUBS.items()},
        "archives": dict(_SAMPLE_ARCHIVES),
        "keeps": list(_SAMPLE_KEEPS),
    }


@pytest.fixture
def isolated_plan(tmp_path, monkeypatch):
    """plan_store backed by a throwaway plan.json, pre-loaded with the test
    sample plan (see _sample_plan). Production seeds nothing — these hubs are
    test data so the logic has something to operate on."""
    import plan_store
    monkeypatch.setattr(plan_store, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(plan_store, "_PLAN_FILE", tmp_path / "plan.json")
    plan_store.save_plan(_sample_plan())
    return plan_store


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """database backed by a throwaway sqlite file with the schema applied."""
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "state.db")
    asyncio.run(database.init_db())
    return database


def insert_scan(database, session_id="s1", scan_id="sc1", repos=None):
    """Helper: write a session + scan + repo rows into the temp DB."""
    repos = repos or []

    async def _go():
        async for db in database.get_db():
            await db.execute(
                "INSERT INTO session (id, github_token, github_user, repos_root) VALUES (?,?,?,?)",
                (session_id, "tok", "tester", "/tmp"),
            )
            await db.execute(
                "INSERT INTO scan_meta (scan_id, session_id, repo_count) VALUES (?,?,?)",
                (scan_id, session_id, len(repos)),
            )
            for r in repos:
                await db.execute(
                    """INSERT INTO repos (scan_id, name, super_cat, mid_cat,
                       aim, url, visibility, language, stars, is_fork, pushed_at, topics, archived)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (scan_id, r["name"], "", "", r.get("aim", ""), "", "public",
                     r.get("language", ""), r.get("stars", 0), 0, "", "[]", 0),
                )
            await db.commit()

    asyncio.run(_go())
    return session_id, scan_id
