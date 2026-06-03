# git-suite Roadmap

**Generated:** May 2026 | **Owner:** Stuart Atkinson

---

## Status: ACTIVE REFACTOR — ALL REPOS ARE CANDIDATES FOR REWRITE

This is a living document. Everything below is the current intent — some repos don't yet exist, some existing repos need to be retired, merged, or replaced.

---

## Principles — sourcing & hub membership

- **Remote-first, local-equal, no distinction.** The portfolio is sourced from
  the GitHub API (owned repos, public *and* private). A local checkout carries
  no special meaning: presence in a local folder neither qualifies nor
  disqualifies a repo, and is never used to source or classify it.
- **No repo is assumed a hub.** Hub membership is *derived* through the plan
  (triage / replan / overlap), not inferred from local presence, repo name, or
  any pre-existing checkout. Hubs are explicit plan definitions; everything
  else earns its verdict from the scan.
- **`repos_root` is optional.** The folder picked at login is stored only as a
  future target for local operations (clone / migration). It does not drive the
  scan, the plan, or hub assignment.

---

## LAYER STRUCTURE

```
LAYER 0 — EVENT BUS & DISPATCH
LAYER 1 — ONTOLOGICAL BACKBONE
LAYER 2 — AUTOMATION & WORKFLOW
LAYER 3 — KNOWLEDGE & RAG
LAYER 4 — MEDIA & ARCHIVING
LAYER 5 — GIS & MAPS
LAYER 6 — GAME & ENTERTAINMENT
LAYER 7 — DEV & CODE TOOLS
LAYER 8 — HOMELAB & INFRA
LAYER 9 — CREATIVE & GRAPHICS
```

---

## REPOS TO ARCHIVE (35 repos — remove from active work)

These have been superseded, are duplicates, or are hobby projects with no clear path to production.

| Repo | Reason |
|------|--------|
| `belzona-tickets` | Local checkout of `guided-tickets` — no diff, retire |
| `JiraApp` | Duplicate of `jira-dependency-graph` |
| `FFXIV-Scraping` | Fragile, superseded by `FFXIVAPI` |
| `FFXIVPlugin` | Experimental, superseded by `XIVSlothCombo` |
| `Newtonian-Particle-Simulator` | GPU physics sim with no export path to any game engine |
| `MarvelGraph` | Marvel API only, too narrow to justify standalone |
| `InteractiveMaps` | Abandoned fork, no clear maintenance path |
| `prettymaps` | Matplotlib static output, superseded by web alternatives |
| `webmapper` | Browsing history mapping, not GIS |
| `Ontologies` | Playground with no output |
| `mRemoteNG` | Niche fork of niche tool, Royal TSX dominates |
| `ClipsReview` | Sequential video review, Frame.io free tier beats it |
| `TagStudio` | Forked photo manager outclassed by Eagle/DigiKam |
| `FreshView` | YouTube enhancement, ImprovedTube bundles it + dozens more |
| `ReverseYoutubePlaylist` | Single function, ImprovedTube already does it |
| `html-tree-generator__chrome-extension` | DevTools already shows DOM tree |
| `restorePhotos` | MyHeritage Photo Enhancer does more, forked version adds nothing |
| `UsefulCodeToMakeGists` | Scratch repo, intent never fulfilled |
| `opencyc` | No description, likely abandoned |
| `infranodus` | No description, no commits visible |
| `John-Watson-Guides` | Empty placeholder |
| `MTGScrape` | Hobby Magic card scraper, no ongoing work |
| `SteamScrape` | Hobby Steam scraper, no ongoing work |
| `twitterscraper` | Social scraper, superseded by snscrape/reddit scrapers |
| `botwr` | BOTW cooking optimizer, hobby scope |
| `ChronoZoom` | Historical timeline, niche and stagnant |
| `donjonrp` | RPG tools, no recent signal |
| `dummy-sheet` | Generic character sheet, hobby |
| `TownGeneratorOS` | Medieval fantasy city generator, hobby |
| `Tetra-Master-Clone` | FFIX mini-game, hobby |
| `chromeos-apk` | Deprecated Android-in-Chrome niche |
| `windows95` | Abandoned Electron fork |
| `esoteric-streamer` | Streaming overlay toolkit, should merge into `VTuberLIVE` |
| `linutil` | Overlaps with `homelab-designer`, consolidate |
| `UsefulCodeToMakeGists` | Scratch repo, never used |

---

## NEW REPOS TO CREATE (8 repos — grounded in starred inspiration)

Each is directly inspired by patterns from 684 starred repos.

### 1. `personal-ai-os`
**Inspired by:** `jan` (open ChatGPT alt), `anything-llm`, `kotaemon` (RAG UI), `open-webui`
**Absorbs:** `quivr` (RAG), `EMailParseAI` (email parsing), `heart-on-a-sleeve` (emotional events)
**What it does:** Unified local AI operating system — RAG + memory + email ingestion + emotional event tracking in one self-hosted platform. One binary, one API, privacy-first.
**Stack:** Python/FastAPI + SQLite + embedding DB + MCP integration

### 2. `ontology-align`
**Inspired by:** `ThesauRex` (SKOS editor), `Skosmos` (thesaurus browser), `awesome-semantic-web`
**Absorbs:** `place-time`, `ontologiesUK`, `CommonCoreOntologies`, `federated-api-model`, `IAO`, `Sagex3-Script-Parser`
**What it does:** Validates and aligns ontological schemas across repos. Tests whether spatial, public sector, enterprise, and information artifact ontologies are interoperable. Visual diff, conflict reports, SPARQL alignment tests.
**Stack:** Python + RDFLib + SHACL + SPARQL endpoints

### 3. `homelab-core`
**Inspired by:** `homebutler` (chat-to-homelab), `Pulse` (AI monitoring), `homelab-mcp`, `glance`, `dockge`, `headscale`
**Absorbs:** `homelab-designer` (merge linutil into it), `homelab-discovery`, `infisical`, `orchestration-stack`, `winutil`
**What it does:** Unified homelab management CLI — discovers services, manages secrets, generates install plans, executes Docker/Traefik stack deployments. Single binary that ties together everything in LAYER 8.
**Stack:** Go or Python/CLI + Docker API + Traefik + MCP servers

### 4. `work-hub`
**Inspired by:** `n8n` (workflow automation), `tegon` (Jira alternative), `twenty` (Salesforce alt), `super-productivity`, `awesome-n8n`
**Absorbs:** `ai-work-orchestration` (Vikunja+Formbricks), `guided-tickets`, `gsd-work`, `jira-dependency-graph`, `ZohoAPI`, `Jira-Lens`
**What it does:** Unified self-hosted work management platform — tasks, projects, CRM, time tracking, and automation in one. Full lifecycle: task → project → CRM → support ticket, with n8n-style automation underneath.
**Stack:** Python + Vikunja API + Formbricks + n8n workflows + Zoho API bridge

### 5. `media-hub`
**Inspired by:** `anime-offline-database`, `Suwayomi-Server` (manga reader), `immich` (photo manager), `manyfold` (3D prints), `CBL-ReadingLists`
**Absorbs:** `socialMediaArchiver`, `tweetext`, `YouTubeCommunityPosts`, `simklExporter`, `linkedin-api`, `CBL-ReadingLists`, `comictagger`, `marvel-comics-api`, `TagStudio`, `EXIF-SpaceTime`, `ClipsReview`, `autoEdit_2`, `intelli-video`
**What it does:** Unified self-hosted media ingestion and management — anime, manga, comics, photos, social archives in one platform. Unified ingestion from any source, structured storage, clean API on top.
**Stack:** Python/FastAPI + PostgreSQL + SPARQL or GraphQL API

### 6. `map-suite`
**Inspired by:** `OSMBuildings` (3D buildings), `mapus` (collaborative maps), `anyplace` (indoor), `arnis` (Minecraft terrain), `streets-gl` (WebGL OSM)
**Absorbs:** `planetiler`, `OSM2World`, `streets-gl`, `openindoor6`, `OsmGo`, `Fantasy-Map-Generator`, `place-time` (as H3 spatial index backend)
**What it does:** Unified OSM-based mapping platform — indoor, outdoor, procedural fantasy, 3D, political/geospatial all in one. `Fantasy-Map-Generator` + `OsmGo` + `openindoor6` + `streets-gl` become one platform with different renderers/views.
**Stack:** TypeScript/Node + CesiumJS/Leaflet + OSM data + vector tiles

### 7. `game-hub`
**Inspired by:** `Playnite` (game library), `Dwarf-Therapist` (Dwarf Fortress management), `PathOfBuilding` (PoE planner), `xivresources`
**Absorbs:** `AllaganTools`, `Lumina`, `XIVSlothCombo`, `FFXIVQuestMap`, `FFXIVAPI`, `xivapi.com`, `PokeManager`, `Pokedex-RL`, `ZeldaRecipes`, `BOTW-Recipes`, `d4buildsAPI`, `gwSkills`, `Chronicle-Keeper`, `foundryvtt-session-scheduler`, `dnd-aMagaAdventure`
**What it does:** Unified gaming platform — FFXIV toolkit, Pokémon, Zelda, Steam library, TTRPG in one plugin-based system. FFXIV tools become one coherent platform with shared data layer via XIVAPI as canonical source.
**Stack:** C# (FFXIV Dalamud), Python (general), shared data layer via XIVAPI

### 8. `code-suite`
**Inspired by:** `bloop` (semantic code search), `all-repos` (bulk clone/sweep), `Sourcegraph` (code intelligence)
**Absorbs:** `bloop`, `all-repos`, `CodeAtlasVsix`, `Coding-Cheatsheets`, `DoIHaveEverything`, `astral`
**What it does:** Unified code management — bulk repo operations, semantic code search, code graph visualisation. `Coding-Cheatsheets` becomes a searchable web app. Share common API/data layer across all tools.
**Stack:** Rust (bloop core), Python (all-repos), TypeScript (web UI)

---

## EXISTING REPOS TO KEEP AS-IS

These are working, maintained, and in production use.

| Repo | Notes |
|------|-------|
| `segment-anything` | SAM model integration, actively used |
| `crawl4ai` | Active web scraping pipeline |
| `Archon` | Jira-like issue tracker, working |
| `OpenDevin` | AI coding agent, benchmark reference |
| `rag-from-scratch` | Educational, reference material |
| `langgraph-search-agents` | Research, kept for reference |
| `portia` | Web scraping tool, active |
| `headless-recorder` | Browser automation, active |
| `YouTubeExtension` | YouTube enhancement, working |
| `jsoncrack.com` | JSON visualisation, dependency/reference |
| `goJS` | Diagram library, dependency/reference |
| `venn.js` | Chart library, dependency/reference |
| `free-map-genie` | Web map tool, working |
| `aw-import-ical` | ActivityWatch integration, working |
| `aw-watcher-ask` | AI-assisted time tracking |
| `FTAnalyzer` | Family Tree analyser, working |
| `wikitree-sourcer` | Genealogy research tool |
| `AncestryBrowsableSchema` | Genealogy schema, working |
| `linkedin-api` | LinkedIn data tools, maintained |
| `XIVSlothCombo` | FFXIV rotation helper, actively used |
| `place-time` | To be absorbed into `map-suite` when that repo is created |

---

## IMPLEMENTATION PRIORITY

```
Priority 1 (Foundation — must do first):
├── ontology-align          # Without this, all layer 1 repos are in vacuum
└── homelab-core           # Without this, no reliable deployment pipeline

Priority 2 (Core functionality):
├── work-hub               # Consolidates all work/ticket/project management
├── personal-ai-os         # Core AI/RAG platform all other systems depend on
└── map-suite              # GIS backbone, spans layers 1 and 5

Priority 3 (Personal data):
├── media-hub              # All personal media in one place
└── game-hub               # All gaming tools in one place

Priority 4 (Polish):
├── code-suite             # Developer experience improvements
└── Archive all dead repos # Clean up the portfolio
```

---

## STARRED INSPIRATION REFERENCE

This roadmap is grounded in the following starred patterns (684 starred repos):

| Category | Count | Key Stars |
|----------|-------|-----------|
| AI Agent Frameworks | 62 | `OpenHands`, `MetaGPT`, `crewAI`, `LangGraph`, `browser-use`, `composio` |
| Homelab Infra | 47 | `Deployrr`, `Organizr`, `ProxmoxVE`, `headscale`, `dockge`, `glance` |
| Maps / GIS | 48 | `BlenderGIS`, `OSMBuildings`, `anyplace`, `Azgaar`, `mapus`, `streets-gl` |
| Media Pipeline | 42 | `Playnite`, `immich`, `Suwayomi-Server`, `anime-offline-database`, `CBL-ReadingLists` |
| RAG / Knowledge | 29 | `quivr`, `kotaemon`, `open-webui`, `anything-llm`, `jan` |
| Gaming Tools | 28 | `Playnite`, `foundryvtt`, `xivresources`, `WoWAnalyzer`, `PathOfBuilding` |
| Ontology / Semantic | 26 | `CommonCoreOntologies`, `IAO`, `ThesauRex`, `Skosmos`, `gedcom-rdf` |
| Dev Tools / Code | 21 | `bloop`, `aider`, `Fabric`, `codesandbox-client` |
| Productivity / Work | 18 | `AppFlowy`, `n8n`, `tegon`, `twenty`, `super-productivity` |
| Personal Data / Quantified Self | 9 | `activitywatch`, `habitica`, `super-productivity` |

---

*Last updated: May 2026*