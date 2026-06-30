# git-suite UI — Architecture & Usage

A guided cockpit for consolidating a sprawling GitHub portfolio into a small set
of hub platforms. It treats the plan as **data**, continuously **reconciles**
intent against live GitHub, and turns decisions into real, idempotent actions.

> Status: the staged plan (Setup → Scan → Cluster → Own → Order → Overlap →
> Replan → Triage → Execute → Hubs → Summary) is built and well past its
> original scope. This doc describes what actually exists.

---

## Run it

### Docker (production)

```bash
docker compose up -d            # frontend + backend + nginx, served on :8080
```

Then open `http://localhost:8080` and configure everything from the **Setup**
page. (`HTTP_PORT` overrides the host port.)

### Local development

```powershell
# backend (port 2800)
cd ui/backend
pip install -r requirements-dev.txt
python -m uvicorn main:app --reload --port 2800

# frontend (port 2173) — separate terminal
cd ui/frontend
npm install
npm run dev          # http://localhost:2173
```

### Tests

```bash
cd ui/backend && python -m pytest        # 99 tests
```

Health: `http://localhost:2800/health`. API docs: `/docs`.

---

## Core design principles

1. **Plan as data, no seed** — the canonical plan lives in `~/.git-suite/plan.json`
   and starts empty; nothing is ever assumed to be a hub. Hubs emerge only from
   the actual GitHub scan (clustering → promote/create) and are edited via the
   API. One source of truth for hubs, absorbs, archives, keeps, boundaries.
2. **Reconciliation engine** — every screen answers "where does reality
   (live GitHub) disagree with the plan, and what's the next action?"
3. **Decision-first** — the atomic unit is one repo needing a verdict.
4. **Planning is cheap, execution is deliberate** — verdicts/edits are local
   and reversible; outward GitHub actions are previewed, confirmed, batched,
   idempotent, and audited.
5. **Remote-only.** Portfolio is sourced entirely from the GitHub API
   (`/user/repos` with `visibility=all` — public *and* private). Local
   checkouts carry no meaning and are never read; there is no local path
   configuration.
6. **No repo is assumed a hub.** Hub membership is *derived* through the plan
   (cluster → triage → replan → overlap), not inferred from a name or
   an existing checkout.
7. **Hybrid intelligence with failover** — deterministic rules for the obvious,
   LLM for the ambiguous, across a multi-provider failover chain; degrades to
   rules-only with no API key. Same for embeddings.

---

## Architecture model — directed grouping → analysis → promotion → planning

git-suite is not a "sort repos into buckets" tool. It is a directed pipeline that ends
as a **guided installer**, where the *hub* is a **DAG** from git-suite to a set of
modular apps/info it can read. Two terms that are easy to conflate:

- **Hub membership** = *standardise + group*. A hub never vendors a member's code —
  "hubs standardise, they don't contain."
- **Absorb** = pulling a *feature* (from a star or fork) **into an owned repo** — not
  swallowing a whole repo into a hub.

The full pipeline (✅ built · ◻ not yet):

1. ✅ **Analyse nodes** — each repo node carries a feature analysis (entities, types,
   purpose). *(the distill step)*
2. ✅ **Group & standardise** — cluster repos into hubs; membership standardises +
   groups, no ingestion.
3. ✅ **Own** — the **Own** stage (Cluster → Own → Order): review owned forks with
   upstream status, decide promote (→ keep / absorb into a hub) or drop (→ archive)
   as a plain plan verdict, and generate a git detach checklist (GitHub has no
   de-fork API, so the actual move is the user's to run).
4. ✅ **Order & type** — within a hub, order + type repos by **read / analyse /
   visualise** *(the Order page's Gather/Analyse/Display ToK layout)*.
5. ◻ **Feature-identify** — feed the ordered+typed context to an LLM to identify each
   repo's features.
6. ◻ **Recommend absorbs** — recommend which *features* (from stars/forks) to absorb
   into the owned repos; own-the-fork-and-delete; **unstar** stars whose features are
   unwanted or already covered more fully by an owned repo.
7. ◻ **Align** — align the projects' design principles across the owned library.
8. ◻ **Guided installer** — git-suite becomes a guided installer; the hub DAG points at
   modular hub apps/info. git-suite is the planning/analysis/recommendation/install
   brain — it does **not** build the hub apps themselves (that's the portfolio's shape).

Steps 3 and 5–8 are the unbuilt half; they're tracked as Open items in
[`../ISSUES.md`](../ISSUES.md).

---

## The loop

```
        Start fresh (blank plan)
                 │
   Scan ──► Reconcile ──► Cluster ──► Triage / Replan ──► Execute
   (live    (intent vs    (group     (give each repo      (archive /
    repos,   reality:      orphans    a verdict;          create hub /
    enriched orphans,      into       replan proposes      push README/
    fields)  ghosts,       hubs)      changes)            MIGRATION.md)
             stubs,                                │
             overlap)         ◄─────── repeat ─────┘
```

---

## Pages (nav order = workflow order)

| Page | What it does |
|------|--------------|
| **Setup** | First step — GitHub connection (PAT); LLM provider config (API key + failover priority; call URLs are hardcoded per provider, models are fetched live from each provider's own listing endpoint and filtered to completion-capable ones); embedding provider + live-listed embedding models; chain readout showing where each is used |
| **Scan** | Streams the live portfolio (incl. private repos) over a same-origin WebSocket; enriched fields (topics, stars, fork, pushed_at, archived, size) |
| **Cluster** | Assisted group formation — embeds **owned + forks + stars in one space** (mixed-source, default) or owned-only (legacy), groups them with spherical k-means (# clusters slider), suggests a theme, user names a new hub / promotes a member / adds to existing; per-member `[O]/[F]/[S]` prefix symbols show source at a glance. Stars double as a dedup signal (a starred project that already covers an owned repo) |
| **Own** | Step 3 — owned forks with upstream status (parent, private-upstream flag), current verdict + cluster; per-fork decide promote (→ keep / absorb into a hub) or drop (→ archive), and generate a git detach checklist (GitHub has no de-fork API, so the move is yours to run) |
| **Order** | Per-hub Tree-of-Knowledge layout — one ordered list of a hub's members (foundational first, presentation last); three classification checkboxes (Gather / Analyse / Display) act as filters; per-row arrow reordering + per-row and per-hub LLM Suggest; per-hub compat-tag vocabulary override |
| **Overlap** | Hub×hub overlap matrix (semantic when embeddings configured, keyword fallback), boundary-case repos, editable hub boundaries |
| **Replan** | Two-phase proposal loop (incremental → structural); accept/reject proposals; prune ghosts; blank/reset plan; history |
| **Triage** | Keyboard-fast verdict queue (1–N absorb, a/k/o/s); stub badges |
| **Execute** | Dry-run preview diffed against live GitHub, then idempotent batch actions: archive repos, create missing hubs, push composed hub READMEs (which include the ToK ordering subsection) + per-absorb migration checklists / MIGRATION.md; hub lifecycle (archive / return / delete) |
| **Hubs** | Hub Audit — orphan repos plus each hub's members, ordered by hub size |
| **Summary** | Reconciliation dashboard: live / absorbed / archived / undecided / ghost / stub counts, per-hub progress, next-action list |

---

## Concepts

- **Verdict** — a repo's fate: `absorb` (→ a hub), `archive`, `keep`, or
  `orphan` (undecided). Hubs are implicitly `keep`.
- **Ghost** — a planned repo no longer on GitHub. Treated as a conscious
  deletion: prune it from the plan.
- **Stub** — a low-signal repo (tiny, no description/stars/topics). Flagged as
  a drop candidate; replan proposes archiving it unless it's function-distinct.
- **Boundary** — each hub's scope rule (what's in, what's delegated elsewhere),
  fed to the LLM so it assigns repos correctly and flags cross-boundary cases.
- **Two-phase replan** — *incremental* (fill orphans / prune ghosts) until
  nothing is undecided, then *replan* (structural: splits, new hubs).
- **Tree-of-Knowledge ordering** — per-hub ontological layout. Each
  hub's absorbs are arranged in a single global rank from foundational
  (what reality is — Gather) through transformation (Analyse) to
  presentation (Display). The three checkboxes are classification
  filters, not slots: a repo can belong to more than one column.
  Order + column flags + compat tags + feature annotations live in
  `state.db` (the `hub_order` table); plan.json is untouched. The hub
  README's `compose_section` renders the ordering as a
  `### Tree-of-Knowledge ordering` subsection when rows exist.
- **Hub lifecycle** — archive empty hub stubs now; later *return* the one
  that becomes the real hub, or *delete* once absorbed (delete requires the
  hub to be archived first; needs the `delete_repo` PAT scope).

---

## Backend layout (`ui/backend`)

```
plan_store.py      canonical plan.json: load/heal (empty default), verdicts, blank/reset
database.py        aiosqlite schema + column migrations
llm_providers.py   provider registry (api_type, base_url, exhaust patterns)
services/
  llm.py           async failover chain (complete)
  embeddings.py    async failover chain + DB cache (cosine)
  github.py        REST: list/archive/unarchive/delete/create, files, readme
  replan.py        proposal engine (rules + LLM + embedding, two-phase)
  migration.py     checklist + scaffold + MIGRATION.md
  cluster.py       spherical k-means over embeddings (# clusters) + theme suggest
  stars.py         owned-vs-starred dedup + per-hub suggestions (semantic / keyword)
  models.py        live model listing per provider dialect (no static lists)
  overlap.py       boundary cases + hub×hub matrix (semantic / keyword)
  claude_ai.py     commercial feature extraction (via llm)
  scraper.py       URL scrape (crawl4ai or httpx+bs4)
routers/
  auth            login, gh-token, session
  scan            start + WebSocket stream + results + latest
  cluster         propose clusters (mixed: owned+fork+star) / form hub / refresh forks
  stars           refresh starred snapshot / list / dedup vs scan + hubs
  order           per-hub ToK layout: get/save/suggest-order/suggest-column/
                  compat-tags/annotate
  hubs            list / status / per-repo archive+absorb
  commercial      scrape + list + delete commercial refs
  readme          preview + push composed hub README
  config          get/post config + provider registry + llm-status + live
                  model listing (POST /config/models/{provider})
  reconcile       intent vs reality (single source for every screen)
  plan            get / reset / blank / clear / hub upsert+remove / verdict / hub-boundary
  replan          state / pass / proposals / accept / reject / prune-ghosts / history
  execute         preview / archive / create-hubs / push-readmes / archive-hubs / unarchive-hubs / delete-hubs
  migration       hub status / checklist (LLM or rule) / push MIGRATION.md
  overlap         hub×hub matrix + boundary cases (semantic / keyword)
```

State: `~/.git-suite/plan.json` (plan), `~/.git-suite/config.json` (keys),
`ui/backend/state.db` (sessions, scans, starred snapshot, actions, proposals,
history, checklists, embeddings cache).

---

*Last updated: 2026-06-18 — cross-source cluster (owned + forks + stars
in one embedding space) + new Order page (per-hub Tree-of-Knowledge
layout with three classification columns and LLM Suggest). Hub README
compose_section now renders the ToK ordering subsection. 99 tests green.*
