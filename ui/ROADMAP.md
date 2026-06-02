# git-suite UI — Roadmap

## Vision

A staged web interface for managing the hub-based portfolio review cycle:
scan GitHub → review hub status → absorb/archive repos → add commercial benchmarks → push updated READMEs.

---

## Phase 0 — CLI Tooling (DONE)

- `generate_github_index.py` — fetch repos → CSV + Excel
- `build_prompts.py` — group repos into themed Claude prompt files
- `portfolio_review.py` — 4-phase review cycle (hub status, archive queue, absorptions, layer audit)
- `init_hub_readmes.py` — write integration roadmap to each hub README
- All 8 hub repos created, roadmap READMEs pushed, 17 dead repos archived

---

## Phase 1 — Backend API (CURRENT)

**Stack:** FastAPI + SQLite (aiosqlite) + httpx

### Routes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/validate` | Validate GitHub PAT, open session |
| GET | `/auth/me` | Current user info |
| POST | `/api/scan` | Start portfolio scan (returns job_id) |
| WS | `/api/scan/{job_id}/progress` | Stream scan progress |
| GET | `/api/repos` | Cached scan results |
| GET | `/api/hubs` | All hubs with status |
| GET | `/api/hub/{name}` | Hub detail (absorbs, archives, commercials) |
| POST | `/api/hub/{name}/archive/{repo}` | Archive a repo via GitHub API |
| POST | `/api/hub/{name}/absorb/{repo}` | Mark repo absorbed in local state |
| POST | `/api/commercial/scrape` | Scrape URL, extract features via Claude |
| POST | `/api/commercial/{hub}` | Save commercial ref to hub |
| GET | `/api/commercial/{hub}` | List commercial refs for hub |
| DELETE | `/api/commercial/{hub}/{id}` | Remove commercial ref |
| POST | `/api/readme/{hub}` | Regenerate + push hub README |

### Database schema

```sql
session (id, github_token, github_user, repos_root, created_at)
repos   (scan_id, name, super_cat, mid_cat, fine_cat, aim, url, visibility, language)
commercial_refs (id, hub, url, name, features_json, added_at)
hub_actions     (hub, repo, action, done_at)   -- action: absorbed | archived
```

---

## Phase 2 — SvelteKit Frontend

**Stack:** SvelteKit + Tailwind CSS

### Screens

```
[1. Login] → [2. Scan] → [3. Hub Grid] → [4. Hub Detail] ←→ [5. Commercial URL Drawer]
                                 ↓
                          [6. Archive Queue]
                                 ↓
                          [7. Layer Audit]
                                 ↓
                          [8. Cycle Summary]
```

**1. Login**
- GitHub PAT input (personal tool, no OAuth complexity)
- Suite root path input with directory browse
- Remembers last session in localStorage

**2. Scan**
- WebSocket progress bar
- Shows repo count, categorisation stage, prompt rebuild

**3. Hub Grid**
- 8 cards, green/red status
- Absorption % bar on each card
- Click → Hub Detail

**4. Hub Detail**
- Absorption list with [Clone] buttons
- Archive-alongside list with [Archive] buttons
- Commercial benchmarks list with [+ Add URL] button
- Split signal warning if 4+ categories

**5. Commercial URL Drawer** (slide-in)
- URL input → [Scrape + Extract]
- Displays extracted name + feature bullets
- [Add to hub] saves + triggers README update

**6. Archive Queue**
- Accordion per hub
- [Archive All for hub] batch button

**7. Layer Audit**
- Layer 0-9 diagram
- Each layer shows its hub(s)
- Orphan list with [Assign] dropdown

**8. Cycle Summary**
- What changed this cycle
- Next recommended action
- [Start New Cycle] button

---

## Phase 3 — Deployment (DONE)

- `docker-compose.yml` — backend + frontend + nginx
- `Dockerfile.backend` — FastAPI container
- `Dockerfile.frontend` — SvelteKit static build
- `nginx.conf` — reverse proxy (HTTP on :8080, /api + /auth → backend, /* → frontend)
- `.env.docker` — template for secrets (ANTHROPIC_API_KEY, GH_TOKEN)
- Optional: Traefik integration with homelab-core

---

## Commercial URL Feature — Detail

1. User pastes a URL (e.g. `https://dndbeyond.com/features`)
2. Backend scrapes with `crawl4ai` → clean markdown content
3. Sends to Claude API with extraction prompt
4. Returns: `{ name: "D&D Beyond", features: ["Character builder", ...] }`
5. User confirms, clicks [Add to hub]
6. Saved to `commercial_refs` table
7. `readme.py` router regenerates hub README section
8. Git commit + push to hub repo

---

*Last updated: May 2026*
