# git-suite UI — Architecture & Usage

A guided cockpit for consolidating a sprawling GitHub portfolio into a small set
of hub platforms. It treats the plan as **data**, continuously **reconciles**
intent against live GitHub, and turns decisions into real, idempotent actions.

> Status: the staged plan (login → scan → … → summary) is built and well past
> its original scope. This doc describes what actually exists.

---

## Run it

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

Tests: `cd ui/backend && python -m pytest` (49 tests).
Health: `http://localhost:2800/health`. API docs: `/docs`.

---

## Core design principles

1. **Plan as data** — the canonical plan lives in `~/.git-suite/plan.json`
   (seeded from `plan.py`), edited via the API. One source of truth for hubs,
   absorbs, archives, keeps, boundaries.
2. **Reconciliation engine** — every screen answers "where does reality
   (live GitHub) disagree with the plan, and what's the next action?"
3. **Decision-first** — the atomic unit is one repo needing a verdict.
4. **Planning is cheap, execution is deliberate** — verdicts/edits are local
   and reversible; outward GitHub actions are previewed, confirmed, batched,
   idempotent, and audited.
5. **Hybrid intelligence with failover** — deterministic rules for the obvious,
   LLM for the ambiguous, across a multi-provider failover chain; degrades to
   rules-only with no API key.

---

## The loop

```
        Start fresh (blank plan)
                 │
   Scan ──► Reconcile ──► Triage / Replan ──► Execute ──► Migration plan
   (live    (intent vs    (give each repo    (archive /   (per-repo
    repos,   reality:      a verdict;         create hub / checklists +
    enriched orphans,      replan proposes    push README/ MIGRATION.md)
    fields)  ghosts,       changes)           hub lifecycle)
             stubs,                               │
             overlap)         ◄─────── repeat ────┘
```

---

## Pages

| Page | What it does |
|------|--------------|
| **Login** | GitHub PAT (or `gh auth`) + repos-root path |
| **Scan** | Streams the live portfolio (incl. private repos) with enriched fields (topics, stars, fork, last-push, size) |
| **Triage** | Keyboard-fast verdict queue (1–N absorb, a/k/o/s); stub badges |
| **Replan** | Two-phase proposal loop + history; Prune ghosts; Start fresh |
| **Overlap** | Hub×hub overlap matrix, boundary-case repos, editable hub boundaries |
| **Hubs / Hub detail** | Per-hub absorbs, alternatives, commercial scrape, README, Migration plan |
| **Execute** | Dry-run + confirm: archive repos · create hubs · push READMEs · hub lifecycle |
| **Layers** | Layer 0–9 view of hubs and their repos |
| **Summary** | Cycle stats + recommended next actions |
| **Setup** | LLM provider keys/models + failover-chain readout; Jira/Zoho |

---

## Concepts

- **Verdict** — a repo's fate: `absorb` (→ a hub), `archive`, `keep`, or
  `orphan` (undecided). Hubs are implicitly `keep`.
- **Ghost** — a planned repo no longer on GitHub. Treated as a conscious
  deletion: prune it from the plan.
- **Stub** — a low-signal repo (tiny, no description/stars/topics). Flagged as a
  drop candidate; replan proposes archiving it unless it's function-distinct.
- **Boundary** — each hub's scope rule (what's in, what's delegated elsewhere),
  fed to the LLM so it assigns repos correctly and flags cross-boundary cases.
- **Two-phase replan** — *incremental* (fill orphans / prune ghosts) until
  nothing is undecided, then *replan* (structural: splits, new hubs).
- **Hub lifecycle** — archive empty hub stubs now; later *return* the one that
  becomes the real hub, or *delete* once absorbed (delete requires archived
  first; needs the `delete_repo` PAT scope).

---

## Backend layout (`ui/backend`)

```
plan.py            seed defaults (hubs, absorbs, archives, keeps, boundaries)
plan_store.py      canonical plan.json: load/heal/seed, verdicts, blank/reset
database.py        aiosqlite schema + column migrations
llm_providers.py   provider registry (api_type, base_url, exhaust patterns)
services/
  llm.py           async failover chain (complete)
  github.py        REST: list/archive/unarchive/delete/create, files, readme
  replan.py        proposal engine (rules + LLM, two-phase)
  migration.py     checklist + scaffold + MIGRATION.md
  claude_ai.py     commercial feature extraction (via llm)
  scraper.py       URL scrape
routers/
  auth scan hubs reconcile plan replan execute migration overlap
  commercial readme config
```

State: `~/.git-suite/plan.json` (plan), `~/.git-suite/config.json` (keys),
`ui/backend/state.db` (sessions, scans, actions, proposals, history, checklists).

---

*Last updated: 2026-06 — reflects the reconcile/replan/execute/migration/overlap build.*
