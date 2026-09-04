# git-suite UI — Architecture & Usage

A guided cockpit for consolidating a sprawling GitHub portfolio into a small set
of hub platforms. It treats the plan as **data**, continuously **reconciles**
intent against live GitHub, and turns decisions into real, idempotent actions.

> Status: the staged plan (Setup → Scan → Cluster → Own → Order → Triage →
> Execute → Summary) is built and well past its original scope. This doc
> describes what actually exists.

---

## Run it

Local dev only — there is no Docker deployment (the `docker-compose.yml` /
`Dockerfile.*` / `nginx.conf` that used to live at the repo root were removed
2026-07-23; they'd drifted weeks stale and duplicated state a second running
copy of the app could silently diverge from). One source of truth: the two
processes below.

```powershell
# backend (port 2801) — 2800 is avoided, see ../PORTS.md
cd ui/backend
pip install -r requirements-dev.txt
python -m uvicorn main:app --reload --port 2801

# frontend (port 2173) — separate terminal, proxies /api + /auth to :2801
cd ui/frontend
npm install
npm run dev          # http://localhost:2173
```

### Tests

```bash
cd ui/backend && python -m pytest        # 195 tests
```

Health: `http://localhost:2801/health`. API docs: `/docs`.

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
   (cluster → own → triage), not inferred from a name or
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
5. ✅ **Feature-identify** — feed the ordered+typed context to an LLM to identify each
   repo's concrete features. *(the Order page's ✨ Features button)*
6. ✅ **Recommend absorbs** — per-orphan best-hub recommendation with two-tier
   confidence, folded into the **Triage** card stream: `💡` hint, `✅` one-click
   "Absorb into Z", or `⭐` copy-URL row for stars you unstar yourself on github.com.
7. ✅ **Align** — the **Order** page's align panel audits design principles
   (structure/docs/tests) across a hub's owned repos and pushes `ALIGNMENT.md`.
8. ✅ **Guided installer** — the **Install** page renders the hub DAG (Wikidata SPARQL
   over `P279`/`P361`, local `plan.json` fallback) as a per-hub d3-force bubble layout.
   git-suite is the planning/analysis/recommendation/install brain — it does **not**
   build the hub apps themselves (that's the portfolio's shape).

All eight steps are built. Remaining work is tracked in
[`../ISSUES.md`](../ISSUES.md).

---

## The loop

```
   Pull ──► Reconcile ──► Cluster ──► Own ──► Order ──► Triage ──► Execute
    │        (intent vs reality:                                      (archive /
    │         orphans, ghosts, stubs)                                  create hub /
    └──────────────────────── repeat ──────────────────────────────── push docs)
```

---

## Pages (nav order = workflow order)

| Page | What it does |
|------|--------------|
| **Setup** | First step — GitHub connection (PAT); LLM provider config (API key + failover priority; call URLs are hardcoded per provider, models are fetched live from each provider's own listing endpoint and filtered to completion-capable ones); embedding provider + live-listed embedding models; chain readout showing where each is used |
| **Scan** | Streams the live portfolio (incl. private repos) over a same-origin WebSocket; enriched fields (topics, stars, fork, pushed_at, archived, size); **Print preview** (`/scan/print`) renders every owned/fork/star repo as an A4-ready card grid (name, purpose, domain/hub tags, language, entities, stars) for printing/PDF |
| **Cluster** ("Themes") | An **iterative refinement surface**, not a one-shot render. **✨ Group by themes** bundles **owned repos AND starred repos** (every repo's distilled purpose/entities/domain + the full README, iteratively summarised to fit the active model's context budget) and asks the configured LLM chain to name each theme after the *human activity* the repos serve, never a tech-stack bucket (no "python", "data", "tools"). Stars are identified to the LLM by full `owner/repo` (owned repos by bare name) so same-named stars from different orgs never collide. **⬇ Download prompt (.txt)** exports the identical system+user prompt as a file for pasting into any external chat LLM; **↥ Import result** parses that LLM's JSON reply back into the same theme cards. Each theme card shows a **margin bar** (1 − Jaccard token overlap vs. its nearest neighbour; thin/ok/wide) and supports **merge with nearest**, **split** (checkbox-select members → peel into a new card), **move** a single member to another card or to unplaced, **rename** (click the title), and **delete** (members return to unplaced). All five mutate the saved `cluster_result` in place via `POST /cluster/{sid}/merge\|split\|move\|rename\|delete`. Themes are cached per-session; promoting a theme into a real hub happens on **Promote**/**Hubs**, not here |
| **Own** | Step 3 — owned forks with upstream status (parent, private-upstream flag), current verdict + cluster; per-fork decide promote (→ keep / absorb into a hub) or drop (→ archive), and generate a git detach checklist (GitHub has no de-fork API, so the move is yours to run) |
| **Order** | Per-hub Tree-of-Knowledge layout — one ordered list of a hub's members (foundational first, presentation last); three classification checkboxes (Gather / Analyse / Display) act as filters; per-row arrow reordering + per-row and per-hub LLM Suggest; **✨ Features** per row asks the LLM to identify the repo's concrete features (architecture Step 5), saved immediately into `feature_annotations`; per-hub compat-tag vocabulary override |
| **Triage** | Keyboard-fast verdict queue (1–N absorb, a/k/o/s); stub badges |
| **Execute** | Dry-run preview diffed against live GitHub, then idempotent batch actions: archive repos, create missing hubs, push composed hub READMEs (which include the ToK ordering subsection) + per-absorb migration checklists / MIGRATION.md; hub lifecycle (archive / return / delete) |
| **Summary** | Reconciliation dashboard: live / absorbed / archived / undecided / ghost / stub counts, per-hub progress, **hub members + orphan repos** (the former Hub Audit, merged in), next-action list |

---

## Concepts

- **Verdict** — a repo's fate: `absorb` (→ a hub), `archive`, `keep`, or
  `orphan` (undecided). Hubs are implicitly `keep`.
- **Ghost** — a planned repo no longer on GitHub. Treated as a conscious
  deletion: prune it from the plan.
- **Stub** — a low-signal repo (tiny, no description/stars/topics). Flagged as
  a drop candidate — archive it unless it's function-distinct.
- **Boundary** — each hub's scope rule (what's in, what's delegated elsewhere),
  stored per hub and fed to the LLM so it assigns repos correctly.
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
  distill.py       per-repo LLM record: purpose / entities / domain (cached)
  themes_bundle.py full-scan bundle builder: owned repos AND starred repos,
                   scan meta + distilled fields + full READMEs,
                   iter-fit-to-budget (summarise top-25%-largest READMEs per
                   pass, target 70% of the active model's context window),
                   persisted to ~/.git-suite/themes-bundle.json. Stars are
                   identified by full owner/repo, owned repos by bare name
                   (to_prompt_records() picks the right one per source)
  topic_llm.py     one-shot LLM theme discovery over the bundle; forbids
                   tech-stack theme names; parse_external_response() re-uses
                   the same extract/validate path for pasted-back JSON
  migration.py     absorb checklist + scaffold + MIGRATION.md
  promote.py       fork detach checklist (Step 3 "Own")
  stars.py         starred-repo snapshot (refresh / list)
  models.py        live model listing per provider dialect (no static lists)
  columns.py       Order-page column names + default compat tags
routers/
  auth            login (purges every OTHER session row for the same
                   github_user — one live session per user, always), gh-token,
                   session
  scan            start + WebSocket stream + results + latest + distill
  cluster         propose (saved_only or explicit recompute) / prompt (.txt
                   export) / import (external LLM JSON reply) / form hub
  promote         list forks / decide promote|drop / detach checklist
  stars           refresh starred snapshot / list
  order           per-hub ToK layout: get/save/suggest-order/suggest-column/
                  suggest-features (Step 5 — LLM feature-identify, persists
                  to feature_annotations)/compat-tags/annotate
  hubs            list hubs / mark absorbed
  readme          compose + push hub README helpers (no routes; used by execute)
  config          get/post config + provider registry + llm-status + live
                  model listing (POST /config/models/{provider})
  reconcile       intent vs reality (single source for every screen)
  plan            get / reset / blank / clear / hub upsert+remove / verdict / hub-boundary
  execute         preview / archive / create-hubs / push-readmes / archive-hubs / unarchive-hubs / delete-hubs
  migration       hub status / checklist (LLM or rule) / push MIGRATION.md
```

State: `~/.git-suite/plan.json` (plan), `~/.git-suite/config.json` (keys),
`~/.git-suite/state.db` (sessions, scans, forks, starred snapshot, repo_domain,
hub_actions, hub_order, migration checklists, embeddings cache, cluster_result),
`~/.git-suite/themes-bundle.json` (audit copy of the last full-scan bundle sent
to the LLM). `GIT_SUITE_HOME` overrides the directory. Session rows are
single-per-user — login purges any other session for the same `github_user`.

---

*Last updated: 2026-07-24 — Cluster page rewritten again, from a read-only
one-shot render into an **iterative refinement surface**: cards (not
columns) with a per-card margin bar (1 − Jaccard token overlap against the
nearest other cluster; thin/ok/wide), and five new mutation endpoints —
`POST /cluster/{sid}/merge|split|move|rename|delete` — that edit the saved
`cluster_result` in place (reused rather than adding a parallel
`cluster_proposal` table; it already held the exact shape needed). Clusters
now carry a stable `id` (assigned once, persisted) so edits survive
renames. The 843-repo live pool (150 owned + 693 stars) was clustered by
hand — the internal minimax-only LLM chain hung/rate-limited on two
consecutive attempts at the single 20-minute topic-discovery call with no
failover provider configured — via the existing external-LLM paste-back
path (export prompt → classify → `/import`), landing 33 themes, 153
repos in `misc-unsorted` (mostly banner-only READMEs with no real scan
signal). Previous entry (same day): clustering now covers starred repos,
not just owned (themes_bundle.build_raw_bundle and cluster.py's pool
builder both hardcoded "owned" and never touched starred_repo; stars are
identified to the LLM by full owner/repo to avoid same-name collisions
across different starred orgs). Docker deployment removed (local dev is
the only supported path); dead k-means `services/cluster.py` deleted;
architecture Step 5 (Feature-identify) built — Order page's ✨ Features
button. **122 tests green.**
