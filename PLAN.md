# git-suite Roadmap

**Last updated:** 2026-06-30 | **Owner:** Stuart Atkinson
*(2026-06-30: reconciled against the 14 aligned local repos — fixed the heart-on-a-sleeve→map-suite misfile, added `genealogy-hub`, surfaced `organised-commons` as a standalone, flagged the atelier-harness/Pane duplicate, recorded the SQLFluffParsing→sql-schema-miner and heart-on-a-sleeve→map-merch renames.)*

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
- **No local paths.** There is no repos-root or folder configuration anywhere;
  the portfolio is read and acted on entirely through the GitHub API.

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

## ARCHITECTURE MODEL — hubs standardise, they don't contain (2026-06-30 reframe)

Earlier drafts read as "absorb repo X **into** hub Y" — the hub swallows the code.
**That is no longer the model.** The shift, in four parts:

### 1. Own every tool (the repo library)
Each tool a hub could use must exist as *my own* first-class repo:
- **Forks → owned repos.** A fork I actually rely on is promoted to a real owned
  repo (de-forked / re-homed), not left as a dependency on someone else's tree.
- **Starred features → owned repos.** When I use a *feature* of a starred project,
  that capability is extracted/reimplemented into an appropriate owned repo — the
  star is inspiration; the capability lives in something I control.
- The portfolio becomes a **curated library of owned, single-purpose tool repos**,
  each standardised (the doc/branch alignment sweep is step one of "standardised").

### 2. Hubs are modular apps over the library — never containers
A domain hub (`map-suite`, `media-hub`, …) is **not** a repo that vendors its members'
code. It is (eventually) a **modular web app or Electron app** that:
- **Standardises** its member repos to one best-practice dev baseline (structure,
  docs, tests — what the alignment sweep produces),
- Gives each an **environment-independent install** (Docker) so any member runs the
  same anywhere,
- Presents the domain as one coherent surface (orchestration/launcher), while the
  tool code stays in its own repo.

> So "**Absorbs:**" in the hub list below now reads "**member repos this hub
> standardises and can compose**" — membership and orchestration, *not* code ingestion.

### 3. Meta-Hub — above the domain hubs
One layer up, a **Meta-Hub** ties the domain hubs together. Two forms (build the second):
- *(a) Installer / orchestrator* — connects to each domain hub and installs them all
  (one command brings up the whole stack).
- *(b) Recommendation MCP (preferred — the AI-forward form).* It knows every hub's
  **domain** and every tool's **features**, so a natural-language intent composes a
  cross-domain tool set on demand:
  > "Since you're using **maps** + **political data** and want to **create videos** →
  > take these 2 from `map-suite`, this 1 from the political set, these 3 from
  > media-creation, these 2 from social-media."
  >
  The MCP recommends and provisions; it doesn't own the tools.

### 4. Meta-Hub owns the data / infra source of truth
The Meta-Hub also manages the **stack's database + container tech as one source of
truth**, so individual projects don't each spin up their own:
- **One unified DB install** all project backends route to (per-project
  schemas/namespaces on a shared engine), and/or
- **One canonical Docker/config layer** the hubs and tools read from — single source
  of truth for connection strings, secrets, ports, volumes.

This is the sibling of `homelab-core` (infra control plane): the Meta-Hub is where
portfolio-level **data + infra config converges**.

**Net:** git-suite's job widens from "absorb/archive/keep + push hub READMEs" to
**(i)** curate an owned, standardised repo library (promote forks, extract starred
features), **(ii)** stand up domain hubs as modular standardising apps with Docker
installs, and **(iii)** stand up a Meta-Hub that recommends/installs across hubs and
centralises DB + Docker config.

---

## REPOS TO ARCHIVE (37 repos — remove from active work)

> **Reframe note (2026-06-30):** under the model above, an "archive" verdict is not
> always a death sentence. A fork I depend on becomes **promote → owned repo**; a
> starred project whose *feature* I use becomes **extract feature → owned repo**.
> Only genuine dead-ends (no path to production, superseded duplicates) are truly
> archived. Re-triage this list through that lens.

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
**Absorbs:** `quivr` (RAG), `EMailParseAI` (email parsing), `multitudes` (identity/footprint clustering)
**What it does:** Unified local AI operating system — RAG + memory + email ingestion + identity-facet clustering in one self-hosted platform. One binary, one API, privacy-first.
> **2026-06-30 correction:** `heart-on-a-sleeve` was previously listed here as "emotional events" — that was a name-association error. It is an OSM map-to-merch renderer and belongs in `map-suite` (see §I). Renamed to `map-merch`.
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
**Absorbs:** `planetiler`, `OSM2World`, `streets-gl`, `openindoor6`, `OsmGo`, `Fantasy-Map-Generator`, `place-time` (as H3 spatial index backend), `map-merch` (OSM→SVG/STL merch renderer; formerly `heart-on-a-sleeve`)
**What it does:** Unified OSM-based mapping platform — indoor, outdoor, procedural fantasy, 3D, political/geospatial all in one. `Fantasy-Map-Generator` + `OsmGo` + `openindoor6` + `streets-gl` become one platform with different renderers/views.
**Stack:** TypeScript/Node + CesiumJS/Leaflet + OSM data + vector tiles

### 7. `game-hub`
**Inspired by:** `Playnite` (game library), `Dwarf-Therapist` (Dwarf Fortress management), `PathOfBuilding` (PoE planner), `xivresources`
**Absorbs:** `AllaganTools`, `Lumina`, `XIVSlothCombo`, `FFXIVQuestMap`, `FFXIVAPI`, `xivapi.com`, `PokeManager`, `Pokedex-RL`, `ZeldaRecipes`, `BOTW-Recipes`, `d4buildsAPI`, `gwSkills`, `Chronicle-Keeper`, `foundryvtt-session-scheduler`, `dnd-aMagaAdventure`
**What it does:** Unified gaming platform — FFXIV toolkit, Pokémon, Zelda, Steam library, TTRPG in one plugin-based system. FFXIV tools become one coherent platform with shared data layer via XIVAPI as canonical source.
**Stack:** C# (FFXIV Dalamud), Python (general), shared data layer via XIVAPI

### 8. `code-suite`
**Inspired by:** `bloop` (semantic code search), `all-repos` (bulk clone/sweep), `Sourcegraph` (code intelligence)
**Absorbs:** `bloop`, `all-repos`, `CodeAtlasVsix`, `Coding-Cheatsheets`, `DoIHaveEverything`, `astral`, `sql-schema-miner` (SQL corpus → schema/ER miner; formerly `SQLFluffParsing`), `Sagex3-Script-Parser`, `neo4J-SQL-Graphs`
**What it does:** Unified code management — bulk repo operations, semantic code search, code graph visualisation. `Coding-Cheatsheets` becomes a searchable web app. Share common API/data layer across all tools.
**Stack:** Rust (bloop core), Python (all-repos), TypeScript (web UI)

### 9. `genealogy-hub`  *(added 2026-06-30 — the PLAN previously had no genealogy home)*
**Inspired by:** `Gramps`, `gedcom-rdf`, FTAnalyzer
**Absorbs:** `Genealogy` (the Ancestry→FTAnalyzer→Gramps→GEDCOM/WikiTree pipeline), `FTAnalyzer`, `wikitree-sourcer`, `AncestryBrowsableSchema`
**What it does:** Self-hosted, Docker-free genealogy workspace — import (Ancestry/scrape) → error-fix (FTAnalyzer) → source-of-truth (Gramps) → GEDCOM MCP for queries + WikiTree MCP for online research. Personal data stays local; the tooling is the reusable part.
**Stack:** Python + GEDCOM/RDF + Gramps SQLite + MCP servers
**Note:** the three "keep as-is" genealogy repos below are this hub's members, not standalones.

---

## STANDALONE PLATFORMS (not a hub member, not archived)

| Repo | Notes |
|------|-------|
| `organised-commons` | **Was absent from this plan.** Federated "places"/commons platform (FastAPI + SvelteKit + ActivityPub) — de-atomise/localise the means of production. Its own platform; LAYER 2 (automation/workflow) federation, but does not fold into `work-hub`. Keep standalone. |

---

## AGENT-MANAGER DUPLICATE — resolve before either ships

`atelier-harness` (Rust, 131 commits, 14.4k LoC, active) and `Pane` (TypeScript, 30
commits, mostly `.claude/` scaffolding, stale since early June) are **the same product
vision** — a terminal-first AI agent *client* (switch/resume sessions, "assist not
scale"). `atelier-harness` is the canonical implementation; `Pane` has the cleaner
public name/positioning ("agent client, not provider"). **Action:** keep
`atelier-harness` as the codebase, archive `Pane`, optionally adopt Pane's name/framing.
`Archon` (harness *builder* for deterministic AI coding) is a different, framework-level
thing — do **not** merge it in.

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

*Last updated: 2026-06-12*

### What changed since May 2026

- Each of the 8 hubs now carries a **boundary** rule (scope + what it excludes),
  stored in `HUB_META[*].boundary`. The LLM is fed these so it assigns repos to
  the correct hub and Overlap can flag cross-boundary cases. The boundary text
  here in PLAN.md is the intent; `ui/backend/plan.py` is the runtime source.
- The `Cluster` stage is now in the workflow loop (between Scan and Hubs). It
  embeds unassigned repos, union-finds them at a cosine threshold, and
  suggests a theme + per-cluster assignments. Use it to form a brand-new hub
  before promoting cluster members into it.
- `init_hub_readmes.py` (standalone README writer) keeps its own copy of the
  hub list. Drift risk — if you edit a hub here, regenerate the README and
  cross-check `ui/backend/plan.py` against `init_hub_readmes.py`.

### Source-of-truth pointers

- Runtime canonical plan: `~/.git-suite/plan.json`, seeded from `ui/backend/plan.py`.
- UI architecture / workflow loop: `ui/ROADMAP.md`.
- LLM/embedding failover: `ui/backend/services/llm.py`, `ui/backend/services/embeddings.py`.
---

## Portfolio alignment — provider chain is the `personal-ai-os` seed (FEATURE-MATRIX §A)

git-suite's LLM + embedding failover is the **canonical provider-chain implementation**
across the whole GitHub portfolio. Source of truth:

- `H:\GitHub\git-suite\ui\backend\services\llm.py`
- `H:\GitHub\git-suite\ui\backend\services\embeddings.py`
- `H:\GitHub\git-suite\ui\backend\llm_providers.py`

The key insight other projects lack: **call URLs hardcoded per provider, model ids
fetched live** from each provider's own listing endpoint, with a deterministic
keyword/language fallback when no provider is configured. This is what stops model
ids from rotting (the failure mode that bit `belzona-tickets`).

**Roadmap implication:** when the planned `personal-ai-os` hub is built, this code +
`belzona-tickets`' battle-tested 7-provider catalogue
(`H:\GitHub\belzona-tickets\src\bt\llm_providers.py`) are the two pieces to absorb.
`multitudes` (`H:\GitHub\multitudes\server\src\ai\llm.ts`) and `place-time`
(`H:\GitHub\place-time\src\core\hexalog.ts`) are downstream consumers that should
adopt this model rather than maintain bespoke fallbacks. atelier-harness solves the
adjacent *credential governance / cross-provider routing* problem and is the superset
reference for that axis.

---

## Portfolio alignment — stars dedup is a special case of homelab-designer's merge (FEATURE-MATRIX §C)

git-suite's Stars stage (owned repo vs. starred alternative → build-vs-adopt) is a
narrow application of the portfolio's canonical entity-merge pipeline:
`H:\GitHub\homelab-designer\backend\normalizer\deduplicator.py` (7 ordered phases +
fuzzy prefix/URL guard) and `...\normalizer\name_rules.py`.

**Roadmap implication:** when `media-hub` / `work-hub` / `personal-ai-os` need to
dedup ingested records across sources, absorb `deduplicator.py` rather than extending
the stars-specific logic. The identity-model half ("one entity, many platform
identities") is canonical in `multitudes` (`H:\GitHub\multitudes\server\src\ai\cluster.ts`).

---

## Portfolio alignment — plan-is-data + separate-execute is the canonical safety pattern (FEATURE-MATRIX §F)

git-suite is the portfolio's reference for **staged tools that take irreversible
outbound actions**. The discipline: every stage reads the live scan + plan and writes
`plan.json` (`~/.git-suite/plan.json`, seeded from `ui/backend/plan.py`); **nothing
reaches GitHub until the separate Execute stage**, which dry-run-previews diffed
against live state before any idempotent batch action.

**Roadmap implication:** any planned hub that mutates external state (`homelab-core`
deploys, `work-hub` ticket writes, `media-hub` ingests) should adopt this two-phase
shape — cheap reversible planning, one deliberate execute with a live-diff preview —
rather than acting inline. The complementary canonical is homelab-designer's
**gating state-chain** (`H:\GitHub\homelab-designer\backend` + `data\*_state.json`):
stages unlock the next and survive restarts.

---

## Portfolio alignment — single source of truth; the hub-list duplicate is the live drift risk (FEATURE-MATRIX §G)

The portfolio's canonical anti-drift rule is bt's "one implementation, the UI shells
out / reads it, never reimplements" (`H:\GitHub\belzona-tickets\docs\ROADMAP.md`).
git-suite is a true client-server app (logic in the FastAPI backend, frontend is
view), so the CLI-spawn form doesn't apply — **but the underlying risk does, and there
is a live instance here:**

- `H:\GitHub\git-suite\ui\backend\init_hub_readmes.py` keeps its **own copy of the hub
  list**, separate from the runtime source `ui\backend\plan.py`. This PLAN.md already
  flags the drift risk ("if you edit a hub here, regenerate the README and cross-check
  plan.py against init_hub_readmes.py").

**Roadmap action:** make `init_hub_readmes.py` import the hub list from `plan.py`
instead of duplicating it — single source of truth, the exact failure bt's rule
prevents.

---

## Portfolio alignment — place-time + map-merch are the concrete map-suite seed (FEATURE-MATRIX §I)

The planned `map-suite` hub already has its two implementation seeds:

- **place-time** (`H:\GitHub\place-time`) — H3 spatial indexing, temporal layers,
  multi-source geo ingestion (Overpass/BGS/ONS). TypeScript.
- **map-merch** (`H:\GitHub\map-merch`, formerly `heart-on-a-sleeve`) — OSM→SVG/STL
  rendering, Cesium selection UI, cosLat projection. Python.

Both independently carry an Overpass client and cosLat projection math — the duplicate
that `map-suite` consolidation should resolve. **Caveat:** they are different runtimes,
so the first map-suite decision is *which runtime hosts the shared Overpass client +
cosLat helper*; until then they share those two pieces as a documented spec (recorded
in both repos' roadmaps under §I).

---

## Portfolio principle — self-hosted, read-only by default, credential stays local (FEATURE-MATRIX §J)

Stated once here (git-suite is the meta/consolidation project) rather than copied into
every repo. This is the **default posture for every planned hub** and every existing
project unless explicitly overridden:

- **Self-hosted / privacy-first** — state lives on the user's infra; no third-party
  service holds the data.
- **Read-only by default** — snapshot sources; never post, sync, or write back without
  explicit, deliberate action (git-suite's own plan-vs-execute split is this rule).
- **Credential stays local** — secrets never leave the box; if a third-party tool needs
  one, proxy it server-side.

Reference statements: ddb-bridge ("the credential never leaves your infrastructure",
`H:\GitHub\ddb-bridge`) and multitudes ("read-only against sources — snapshots, never
writes back", `H:\GitHub\multitudes`). New hubs (`personal-ai-os`, `work-hub`,
`media-hub`, `homelab-core`, `map-suite`) inherit this by default.
