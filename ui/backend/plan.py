"""
plan.py — hub plan data for the backend API.
Keep in sync with portfolio_review.py and init_hub_readmes.py in the repo root.
"""

HUB_ABSORBS: dict[str, list[str]] = {
    "personal-ai-os": [
        "quivr", "EMailParseAI", "heart-on-a-sleeve", "gsd-work",
        "LangFlowProject", "Multi-agent-DataAnalysis", "MultiCoT", "STTScrape",
    ],
    "ontology-align": [
        "place-time", "ontologiesUK", "CommonCoreOntologies", "federated-api-model",
        "IAO", "Sagex3-Script-Parser", "UKPoliticsData", "neo4J-SQL-Graphs",
    ],
    "homelab-core": [
        "homelab-designer", "homelab-discovery", "infisical", "orchestration-stack",
        "ai-work-orchestration", "winutil", "linutil", "fusio",
    ],
    "work-hub": [
        "guided-tickets", "jira-dependency-graph", "ZohoAPI", "Jira-Lens",
    ],
    "media-hub": [
        "socialMediaArchiver", "YouTubeCommunityPosts", "simklExporter",
        "CBL-ReadingLists", "marvel-comics-api", "EXIF-SpaceTime", "tweetext",
        "comictagger", "linkedin-api", "TagStudio", "ClipsReview",
        "autoEdit_2", "intelli-video", "AIPhotoRestore",
    ],
    "map-suite": [
        "qgis-mcp", "Fantasy-Map-Generator", "planetiler", "OSM2World",
        "streets-gl", "openindoor6", "OsmGo", "worldengine",
    ],
    "game-hub": [
        "FFXIVQuestMap", "FFXIVAPI", "AllaganTools", "Lumina", "XIVSlothCombo",
        "PokeManager", "Pokedex-RL", "ZeldaRecipes", "BOTW-Recipes",
        "BlossomsPokemonGoManager", "Pogo-Account-Checker", "GoDex", "PokemonGo-Bot",
        "botw-tools", "d4buildsAPI", "gwSkills", "DungeonGeneration",
        "Chronicle-Keeper", "foundryvtt-session-scheduler", "dnd-aMagaAdventure", "Armoria",
    ],
    "code-suite": [
        "DoIHaveEverything", "Coding-Cheatsheets", "CodeAtlasVsix", "SQLFluffParsing",
        "ClickTheseThings", "Page-Manipulator", "RepoReader", "bytebytego-grabber",
        "bloop", "all-repos", "astral",
    ],
}

HUB_META: dict[str, dict] = {
    "personal-ai-os":  {"layer": 3, "priority": 2, "description": "Unified local AI OS — RAG, memory, email ingestion, emotional events"},
    "ontology-align":  {"layer": 1, "priority": 1, "description": "Validates and aligns ontological schemas across repos"},
    "homelab-core":    {"layer": 8, "priority": 1, "description": "Self-hosted infrastructure control plane — service discovery, secrets, stack deployment and homelab orchestration"},
    "work-hub":        {"layer": 2, "priority": 2, "description": "Self-hosted professional work management — tickets, CRM and project tools"},
    "media-hub":       {"layer": 4, "priority": 3, "description": "Unified media ingestion — social archives, comics, photos and video"},
    "map-suite":       {"layer": 5, "priority": 2, "description": "OSM-based unified mapping — indoor, outdoor, 3D and procedural fantasy"},
    "game-hub":        {"layer": 6, "priority": 3, "description": "Unified gaming platform — FFXIV toolkit, Pokemon, Zelda, Steam and TTRPG"},
    "code-suite":      {"layer": 7, "priority": 4, "description": "Unified code management — bulk ops, semantic search, code graph and cheatsheets"},
}

ARCHIVE_HUB: dict[str, str | None] = {
    "belzona-tickets": "work-hub",       "JiraApp": "work-hub",
    "FFXIV-Scraping": "game-hub",        "FFXIVPlugin": "game-hub",
    "InteractiveMaps": "game-hub",       "Tetra-Master-Clone": "game-hub",
    "TownGeneratorOS": "game-hub",       "botwr": "game-hub",
    "donjonrp": "game-hub",              "dummy-sheet": "game-hub",
    "ClipsReview": "media-hub",          "TagStudio": "media-hub",
    "restorePhotos": "media-hub",        "twitterscraper": "media-hub",
    "mRemoteNG": "homelab-core",         "linutil": "homelab-core",
    "Ontologies": "ontology-align",      "opencyc": "ontology-align",
    "html-tree-generator__chrome-extension": "code-suite",
    "UsefulCodeToMakeGists": "code-suite",
    # No hub — retire whenever (superseded, abandoned, or out of scope).
    "Newtonian-Particle-Simulator": None, "MarvelGraph": None,
    "prettymaps": None,                   "webmapper": None,
    "FreshView": None,                    "ReverseYoutubePlaylist": None,
    "infranodus": None,                   "John-Watson-Guides": None,
    "MTGScrape": None,                    "SteamScrape": None,
    "ChronoZoom": None,                   "chromeos-apk": None,
    "windows95": None,                    "esoteric-streamer": None,
    "nouns-ai-sd-server": None,           "pc-part-dataset": None,
    "ai-demos": None,
}

HUB_ALTERNATIVES: dict[str, dict[str, list[str]]] = {
    "personal-ai-os":  {"oss": ["Jan", "anything-llm", "open-webui", "kotaemon", "LangFlow", "n8n", "Flowise", "mem0"],        "commercial": ["ChatGPT", "Notion AI", "mem.ai", "Superhuman", "Replika", "Woebot", "Perplexity"]},
    "ontology-align":  {"oss": ["Protege", "RDFLib", "ROBOT", "Apache Jena", "ThesauRex", "Skosmos", "VocBench"],              "commercial": ["TopBraid Composer", "PoolParty", "Palantir Ontology", "Stardog", "Ontotext GraphDB"]},
    "homelab-core":    {"oss": ["Portainer", "Coolify", "Runtipi", "Umbrel", "Ansible", "Terraform", "Pulumi", "Consul"],      "commercial": ["Portainer Business", "Replicated", "Temporal Cloud", "HashiCorp Cloud", "Doppler"]},
    "work-hub":        {"oss": ["Vikunja", "Plane", "AppFlowy", "n8n", "Taiga", "tegon", "twenty"],                            "commercial": ["Jira", "Monday.com", "ClickUp", "Zoho CRM", "Linear", "Asana", "Salesforce"]},
    "media-hub":       {"oss": ["Immich", "Jellyfin", "Kavita", "Paperless-ngx", "ArchiveBox", "Suwayomi-Server"],             "commercial": ["Google Photos", "Adobe Lightroom", "Frame.io", "Simkl", "Marvel Unlimited", "Plex"]},
    "map-suite":       {"oss": ["QGIS", "OpenLayers", "Leaflet", "CesiumJS", "MapLibre GL", "OpenMapTiles"],                   "commercial": ["ESRI ArcGIS", "Mapbox", "HERE Maps", "Google Maps Platform", "Felt"]},
    "game-hub":        {"oss": ["Playnite", "Foundry VTT", "Universalis", "Garland Tools", "XIVAPI", "WoWAnalyzer"],           "commercial": ["DnDBeyond", "WorldAnvil", "Steam", "Battle.net", "SquareEnix Companion App"]},
    "code-suite":      {"oss": ["Sourcegraph OSS", "Gitea", "aider", "OpenGrok", "code2flow"],                                 "commercial": ["GitHub", "Sourcegraph Enterprise", "JetBrains Fleet", "CodeMR", "SciTools Understand"]},
}

LAYER_NAMES: dict[int, str] = {
    0: "Event Bus & Dispatch",   1: "Ontological Backbone",
    2: "Automation & Workflow",  3: "Knowledge & RAG",
    4: "Media & Archiving",      5: "GIS & Maps",
    6: "Game & Entertainment",   7: "Dev & Code Tools",
    8: "Homelab & Infra",        9: "Creative & Graphics",
}

KEEP_AS_IS: set[str] = {
    "xivapi.com", "VTuberLIVE",
    "AncestryBrowsableSchema", "FTAnalyzer", "wikitree-sourcer",
    "Archon", "OpenDevin", "agent-zero", "crewAI", "crewAI-examples",
    "crawl4ai", "portia", "headless-recorder", "langgraph-search-agents",
    "rag-from-scratch", "llm-answer-engine", "kg_llm",
    "aw-import-ical", "aw-watcher-ask",
    "GoJS", "jsoncrack.com", "venn.js", "segment-anything",
    "YouTubeExtension", "free-map-genie",
    "git-suite",
}
