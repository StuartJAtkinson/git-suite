# git-suite

**Canonical home:** https://github.com/StuartJAtkinson/git-suite

My personal software suite — tools, automations, and platforms I maintain and use daily, all self-hosted where possible. Built around an event-driven, layered architecture with a semantic knowledge backbone.

---

## Architecture Overview

```
LAYER 0 — EVENT BUS & DISPATCH
│   Orchestrates events across all systems
│
├── LAYER 1 — ONTOLOGICAL BACKBONE
│   │   Unified semantic model and knowledge graph
│   │
│   ├── place-time          — Spatial/temporal ontology (H3, SPARQL)
│   ├── ontologiesUK        — UK public sector ontology (Parliament, ONS)
│   ├── CommonCoreOntologies — Enterprise business ontology
│   ├── IAO                  — Information Artifact Ontology
│   └── federated-api-model  — Government API ontology
│
├── LAYER 2 — AUTOMATION & WORKFLOW
│   │   All operational tasks, tickets, and project management
│   │
│   ├── ai-work-orchestration  — Vikunja + Formbricks + AI planning
│   ├── guided-tickets          — Structured ticket resolution workflows
│   ├── belzona-tickets         — Belzona Sage X3 specific tickets
│   └── gsd-work                — Getting Things Done (GTD) system
│
├── LAYER 3 — KNOWLEDGE & RAG
│   │   Personal knowledge, RAG pipelines, semantic search
│   │
│   ├── quivr                 — RAG over personal documents (with MCP)
│   ├── heart-on-a-sleeve     — Emotional/memory event tracker
│   └── EMailParseAI          — Email ingestion and RAG indexing
│
├── LAYER 4 — MEDIA & ARCHIVING
│   │   Personal media management and social archiving
│   │
│   ├── socialMediaArchiver   — Social content archiver
│   ├── tweetext              — Twitter/X Wayback machine
│   ├── YouTubeCommunityPosts — YouTube community post scraper
│   ├── simklExporter         — TV/anime watch history exporter
│   ├── linkedin-api          — LinkedIn data tools
│   ├── CBL-ReadingLists      — Comic/graphic novel reading lists
│   └── intelli-video         — Intelligent video processing
│
├── LAYER 5 — GIS & MAPS
│   │   Geospatial data processing and map rendering
│   │
│   ├── Fantasy-Map-Generator — Procedural fantasy map generation
│   ├── planetiler            — Vector tile generation (Mapbox)
│   ├── OSM2World             — OSM → 3D world objects
│   ├── streets-gl            — WebGL OSM map renderer
│   ├── openindoor6           — Indoor mapping
│   └── OsmGo                 — OSM field data collection
│
├── LAYER 6 — GAME & ENTERTAINMENT
│   │   Gaming tools, data trackers, and entertainment platforms
│   │
│   ├── AllaganTools          — FFXIV data tools
│   ├── Lumina               — FFXIV overlay plugin (Dalamud)
│   ├── XIVSlothCombo         — FFXIV rotation helper
│   ├── FFXIVQuestMap         — FFXIV quest tracker
│   ├── XIVAPI                — FFXIV API client
│   ├── FFXIVAPI              — Alternative FFXIV client
│   ├── simklExporter         — TV/anime watch tracking (cross-layer)
│   ├── Lumina                — FFXIV overlay system
│   ├── PokeManager           — Pokémon game data manager
│   ├── ZeldaRecipes          — Zelda recipe/food planner
│   ├── BOTW-Recipes          — Breath of the Wild recipe browser
│   ├── d4buildsAPI           — Diablo 4 build planner API
│   ├── gwSkills              — Guild Wars skill database
│   ├── Chronicle-Keeper      — TTRPG campaign journal
│   ├── foundryvtt-session-scheduler — Foundry VTT scheduling
│   └── dnd-aMagaAdventure    — D&D adventure generator
│
├── LAYER 7 — DEV & CODE TOOLS
│   │   Development utilities and code management
│   │
│   ├── bloop                 — Semantic code search (Rust)
│   ├── all-repos            — Bulk git repo operations
│   ├── astral               — GitHub stars organiser
│   ├── Coding-Cheatsheets   — Publishable coding cheatsheets
│   └── DoIHaveEverything    — Repository inventory checker
│
├── LAYER 8 — HOMELAB & INFRA
│   │   Homelab management, secrets, and deployment
│   │
│   ├── infisical            — Secrets management vault
│   ├── homelab-designer     — Docker compose install planner
│   └── orchestration-stack  — Traefik, monitoring, and infra stack
│
└── LAYER 9 — CREATIVE & GRAPHICS
    │   Creative tools and generative graphics
    │
    ├── mapus                 — Collaborative map editor
    └── open3d                — 3D reconstruction and processing
```

---

## Key Principles

- **Self-hosted first** — Run everything on your own infrastructure where possible
- **Event-driven** — All systems communicate via event bus; no tight coupling
- **Ontology-backed** — Every domain has a formal ontology that describes its entities and relationships
- **Layered** — LAYER 0 (event bus) → LAYER 1 (semantic) → data layers, strict dependency direction
- **Privacy-first** — Personal data, genealogy, health, work — all stay local

---

## Documentation

- [ISSUES.md](./ISSUES.md) — Active tickets and project tracking

---

*Last updated: May 2026*