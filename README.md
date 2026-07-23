# git-suite

**Canonical home:** https://github.com/StuartJAtkinson/git-suite

A self-hosted web app for turning a sprawling GitHub portfolio into a **curated library
of owned, standardised tool repos** organised under a small set of **domain hubs**. It
scans your owned repos (public *and* private) and helps you *plan* each one's role —
**standardise** it into a hub, **promote** a fork to an owned repo, **extract** a starred
project's feature into one, **keep**, or **archive** — then executes the consolidation
actions it can (archive, create a hub repo, push README/MIGRATION.md) back against GitHub.
The deeper roles (promote, extract) are decisions the tool records; the building happens
in the portfolio repos themselves.

> **Hubs standardise, they don't contain.** A hub never vendors its members' code; it is
> a modular web/Electron app that standardises, Docker-packages and composes the owned
> tool repos that belong to its domain. Above them sits a **Meta-Hub** — a recommendation
> MCP that composes cross-domain tool sets on demand and owns the unified DB + Docker
> config as one source of truth.
>
> *This describes the **portfolio's** target shape — what the hubs and Meta-Hub become as
> their own apps. git-suite does not build them; it is the planning tool that gets you
> there.*

This README is about the *tool* that gets you there.

---

## Core idea

The portfolio is a **library of owned, single-purpose tool repos**; **hubs are modular
apps that standardise and compose that library, never containers that swallow it**; and a
**Meta-Hub** recommends/installs across hubs and centralises data + infra config.

Operationally, planning is **cheap, local, and reversible**; execution is a **separate,
deliberate** step that touches GitHub.

- **Plan is data, not code.** The canonical plan lives in `plan.json` under
  `GIT_SUITE_HOME` (defaults to `~/.git-suite`). It starts empty — no hubs are
  seeded. Every verdict, hub, and boundary is an edit to that file — never a
  code change.
- **Remote-only.** The portfolio is sourced entirely from the GitHub API. A local
  checkout carries no meaning: presence in a folder never qualifies, classifies, or
  sources a repo, and there is no local path configuration.
- **No repo is assumed a hub.** Hub membership is *derived* through the plan (cluster →
  own → triage), not inferred from a name or an existing checkout.
- **Degrades cleanly.** LLM and embedding features run through failover chains and fall
  back to deterministic keyword/language rules when no provider is configured.

---

## The workflow

The nav is ordered as the workflow runs. Each stage reads the live scan + the plan and
writes back to `plan.json`; nothing reaches GitHub until **Execute**.

| Stage | What it does |
|-------|--------------|
| **Setup** | First step — GitHub connection (PAT); configure LLM and embedding providers (API key + model + failover priority — call URLs are hardcoded per provider and models are fetched live from each provider's own listing endpoint). Shows where each chain is actually used. |
| **Scan** | Pulls every owned repo (public + private) over a live WebSocket, capturing topics, stars, fork/archived flags, `pushed_at`. |
| **Cluster** ("Themes") | Read-only, one-shot LLM group formation. Bundles the whole enriched scan — every repo's distilled purpose/entities/domain plus its full README — and asks the LLM to name each theme after the *human activity* the repos serve, never a tech-stack bucket. Can't reach an LLM directly? Download the identical prompt as a `.txt` file, run it through any chat LLM, and paste the JSON reply back in. Promoting a theme into a real hub happens on **Own**/**Hubs**, not here. |
| **Own** | Step 3 — review owned forks (parent/upstream status), decide promote (→ keep / absorb into a hub) or drop (→ archive), and generate a git detach checklist. GitHub has no de-fork API, so the actual move is yours to run. |
| **Order** | Per-hub Tree-of-Knowledge layout — arranges a hub's members from foundational (Gather) through Analyse to Display; per-row reorder + LLM Suggest; feeds the hub README's ordering section. |
| **Triage** | Keyboard-fast verdict queue over remaining repos (absorb / keep / archive / orphan). |
| **Execute** | Dry-run preview diffed against **live** GitHub state, then idempotent batch actions: archive repos, create missing hubs, push composed hub READMEs + MIGRATION.md. |
| **Summary** | Reconciliation dashboard: live / absorbed / archived / undecided / ghost counts, per-hub progress, hub members + orphan repos (the former Hub Audit), and the next-action list. |

---

## Architecture

```
SvelteKit frontend (:2173) ──► FastAPI backend (:2801) ──► SQLite (state.db)
                                      │
                                      ├── GitHub API   (scan / archive / create / READMEs)
                                      ├── LLM chain     (failover: themes, migration)
                                      └── Embeddings    (failover: cache)
```

- **Backend** (`ui/backend`) — FastAPI. Routers under `/api` (`scan`, `stars`, `cluster`,
  `hubs`, `plan`, `order`, `reconcile`, `execute`, `migration`, `readme`, `promote`,
  `config`) and `/auth`. Services: `github`, `llm`, `embeddings`, `distill`,
  `themes_bundle`, `topic_llm`, `stars`, `migration`, `promote`, `models`, `columns`.
  Plan persistence in `plan_store.py`; provider registry in `llm_providers.py`.
- **Frontend** (`ui/frontend`) — SvelteKit, one route per workflow stage.
- **Config** — no env files for app config; everything is set through the Setup page and
  stored in `config.json` under `GIT_SUITE_HOME` (defaults to `~/.git-suite`). All
  persistent state (`state.db`, `config.json`, `plan.json`, `themes-bundle.json`)
  lives under that one directory.

---

## Running it

Local dev only — there is no Docker deployment. (A `docker-compose.yml` used to live
here; it duplicated state a second running copy could silently diverge from, went
weeks stale, and was removed 2026-07-23.)

```bash
# backend (port 2801)
cd ui/backend
pip install -r requirements-dev.txt
python -m uvicorn main:app --reload --port 2801

# frontend (port 2173, proxies /api and /auth to :2801)
cd ui/frontend
npm install
npm run dev
```

Open `http://localhost:2173` and configure everything from the **Setup** page.

### Tests

```bash
cd ui/backend && python -m pytest        # 111 tests
```

---

## Documentation

- [ISSUES.md](./ISSUES.md) — running open/resolved issue log.

---

*Last updated: 2026-07-23 — Cluster page rewritten as one-shot LLM theme grouping with
.txt prompt export + JSON re-import for external LLMs; Docker deployment removed (local
dev only); this doc's Architecture/Running-it sections were describing routers
(`replan`/`overlap`/`commercial`) removed in an earlier pass — corrected the doc and
deleted the last unused leftover, `services/cluster.py` (the pre-LLM k-means module,
imported nowhere).*
