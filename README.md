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
  `GIT_SUITE_HOME` (defaults to `~/.git-suite`; in Docker, `/app/data` so the
  existing host mount covers it). It starts empty — no hubs are seeded. Every
  verdict, hub, and boundary is an edit to that file — never a code change.
- **Remote-only.** The portfolio is sourced entirely from the GitHub API. A local
  checkout carries no meaning: presence in a folder never qualifies, classifies, or
  sources a repo, and there is no local path configuration.
- **No repo is assumed a hub.** Hub membership is *derived* through the plan (cluster →
  triage → replan → overlap), not inferred from a name or an existing checkout.
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
| **Cluster** | Embeds **owned repos + forks + stars in one space** and groups them with spherical k-means (# clusters slider); suggests a theme so you can promote a member into a hub or form a new one. Stars double as a dedup signal — a starred project that already covers an owned repo. |
| **Order** | Per-hub Tree-of-Knowledge layout — arranges a hub's members from foundational (Gather) through Analyse to Display; per-row reorder + LLM Suggest; feeds the hub README's ordering section. |
| **Overlap** | Semantic venn — scores repos against hub profiles to surface boundary cases and a hub×hub overlap matrix; edit per-hub boundaries here. |
| **Replan** | Iterative two-phase loop: *incremental* (fill orphans / prune ghosts) until fully planned, then *structural* (split / new-hub advisories). Proposes verdicts you accept or reject. |
| **Triage** | Keyboard-fast verdict queue over remaining repos (absorb / keep / archive / orphan). |
| **Execute** | Dry-run preview diffed against **live** GitHub state, then idempotent batch actions: archive repos, create missing hubs, push composed hub READMEs + MIGRATION.md. |
| **Hubs** | Hub Audit — orphan repos plus each hub's members, ordered by hub size. |
| **Summary** | Reconciliation dashboard: live / absorbed / archived / undecided / ghost counts, per-hub progress, and the next-action list. |

---

## Architecture

```
SvelteKit frontend ──► nginx ──► FastAPI backend ──► SQLite (state.db)
                                      │
                                      ├── GitHub API   (scan / archive / create / READMEs)
                                      ├── LLM chain     (failover: replan, migration, commercial)
                                      └── Embeddings    (failover: cluster, overlap, replan)
```

- **Backend** (`ui/backend`) — FastAPI. Routers under `/api` (`scan`, `stars`, `cluster`,
  `hubs`, `plan`, `replan`, `overlap`, `reconcile`, `execute`, `migration`, `readme`,
  `commercial`, `config`) and `/auth`. Services: `github`, `llm`, `embeddings`,
  `stars`, `cluster`, `replan`, `migration`, `scraper`, `claude_ai`. Plan persistence
  in `plan_store.py`; provider registry in `llm_providers.py`.
- **Frontend** (`ui/frontend`) — SvelteKit, one route per workflow stage.
- **Config** — no env files for app config; everything is set through the Setup page and
  stored in `config.json` under `GIT_SUITE_HOME`. All persistent state
  (`state.db`, `config.json`, `plan.json`) lives under that one directory so a
  single host volume covers everything.

---

## Running it

### Docker (production)

```bash
docker compose up -d            # frontend + backend + nginx, served on :8080
```

Then open `http://localhost:8080` and configure everything from the **Setup** page.
(`HTTP_PORT` overrides the host port.)

### Local development

```bash
# backend
cd ui/backend
pip install -r requirements.txt
uvicorn main:app --reload        # :8000

# frontend
cd ui/frontend
npm install
npm run dev                      # :5173, proxies /api and WS to :8000
```

### Tests

```bash
cd ui/backend && python -m pytest        # 99 tests
```

---

## Documentation

- [ISSUES.md](./ISSUES.md) — running open/resolved issue log.

---

*Last updated: 2026-06-30 — reframed around the "hubs standardise, don't contain" model:
owned-repo library, hubs as modular standardising apps, and a Meta-Hub (recommendation
MCP + unified DB/Docker source of truth).*
