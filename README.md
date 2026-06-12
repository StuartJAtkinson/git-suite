# git-suite

**Canonical home:** https://github.com/StuartJAtkinson/git-suite

A self-hosted web app for **consolidating a sprawling GitHub portfolio into a small set
of maintained "hubs."** It scans your owned repos (public *and* private), helps you
decide each one's fate — **absorb** into a hub, **archive**, or **keep** — and then
executes those decisions back against GitHub.

The portfolio target (which hubs exist, what they absorb, the layer structure) lives in
[PLAN.md](./PLAN.md). This README is about the *tool* that gets you there.

---

## Core idea

Planning is **cheap, local, and reversible**; execution is a **separate, deliberate**
step that touches GitHub.

- **Plan is data, not code.** The canonical plan lives in `~/.git-suite/plan.json`
  (seeded once from `plan.py`). Every verdict, hub, and boundary is an edit to that
  file — never a code change.
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
| **Setup** | First step — GitHub connection (PAT or `gh auth`); configure LLM and embedding providers (API key + call URL + model, with failover priority). Shows where each chain is actually used. |
| **Scan** | Pulls every owned repo (public + private) over a live WebSocket, capturing topics, stars, fork/archived flags, `pushed_at`. |
| **Cluster** | Embeds unassigned repos and union-find clusters them over a cosine threshold (tightness slider); suggests a theme so you can form a new hub or grow an existing one. |
| **Hubs** | Create/define hubs (name, layer, priority, description, boundary rule) and see each hub's absorb/archive status. |
| **Overlap** | Semantic venn — scores repos against hub profiles to surface boundary cases and a hub×hub overlap matrix; edit per-hub boundaries here. |
| **Replan** | Iterative two-phase loop: *incremental* (fill orphans / prune ghosts) until fully planned, then *structural* (split / new-hub advisories). Proposes verdicts you accept or reject. |
| **Triage** | Keyboard-fast verdict queue over remaining repos (absorb / keep / archive / orphan). |
| **Execute** | Dry-run preview diffed against **live** GitHub state, then idempotent batch actions: archive repos, create missing hubs, push composed hub READMEs + MIGRATION.md. |
| **Layers** | Layer audit — repos rolled up by layer, surfacing cross-layer conflicts. |
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

- **Backend** (`ui/backend`) — FastAPI. Routers under `/api` (`scan`, `cluster`, `hubs`,
  `plan`, `replan`, `overlap`, `reconcile`, `execute`, `migration`, `readme`,
  `commercial`, `config`) and `/auth`. Services: `github`, `llm`, `embeddings`,
  `cluster`, `replan`, `migration`, `scraper`, `claude_ai`. Plan persistence in
  `plan_store.py`; provider registry in `llm_providers.py`.
- **Frontend** (`ui/frontend`) — SvelteKit, one route per workflow stage.
- **Config** — no env files for app config; everything is set through the Setup page and
  stored in `~/.git-suite/config.json`.

### Standalone scripts

Predate the web app; still useful for offline analysis:

- `generate_github_index.py` — flat CSV/Excel of all repos for pivot analysis (`--no-sbom` to skip the stack fetch).
- `portfolio_review.py` — iterative portfolio health check (hub targets, archive queue, absorptions, layer audit).

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
cd ui/backend && python -m pytest        # 61 tests
```

---

## Documentation

- [PLAN.md](./PLAN.md) — the canonical portfolio roadmap (layers, hubs, archive/create lists).
- [ISSUES.md](./ISSUES.md) — running open/resolved issue log.

---

*Last updated: June 2026*
