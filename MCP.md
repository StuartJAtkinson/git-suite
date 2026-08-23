# MCP — git-suite

**Design spec.** No MCP server exists yet. This is the surface this repo should
expose, mapped to the routers that already implement it.

- **Proposed server:** `git-suite`
- **Transport:** stdio
- **Backs onto:** the FastAPI routers under `ui/backend/routers/`

## Why this repo wants one

git-suite is a *pipeline over your repos* — scan, triage, cluster, order,
absorb, promote, install — and every stage already produces a session-scoped
artefact the UI renders. An agent that could read those artefacts could answer
"which of my repos are orphans", "what does the absorb plan for this hub look
like", "is anything drifting" without a human clicking through six pages.

The stages that **decide** (triage verdicts, hub membership) are already
LLM-assisted inside git-suite. Exposing them as tools would mean an agent
driving an agent, which is the wrong shape. So this spec exposes the **reads and
the previews**, and keeps the acts behind the UI.

## Tools — reading the pipeline

| Tool | Params | Returns | Backs onto |
|---|---|---|---|
| `get_plan` | — | the current plan: hubs, members, forbids | `GET /plan` (`routers/plan.py:31`) |
| `list_hubs` | — | hub repos | `GET /hubs` (`routers/hubs.py:10`) |
| `list_forbids` | — | pairs explicitly barred from clustering | `GET /plan/forbids` (`routers/plan.py:135`) |
| `get_cluster` | `session_id` | the clustering result for a session | `GET /cluster/{session_id}` (`routers/cluster.py:316`) |
| `get_order` | `session_id`, `hub` | the absorb order for a hub | `GET /order/{session_id}/{hub}` (`routers/order.py:87`) |
| `get_absorb_plan` | `hub`, `repo`, `session_id` | how one repo folds into a hub | `GET /absorb/plan/{hub}/{repo}/{session_id}` (`routers/absorb.py:180`) |
| `get_migration_plan` | `hub`, `session_id` | the migration view for a hub | `GET /migration/hub/{hub}/{session_id}` (`routers/migration.py:64`) |
| `preview_execute` | `session_id` | what execution *would* do | `GET /execute/preview/{session_id}` (`routers/execute.py:60`) |
| `get_install_plan` | `session_id`, `format?` | install steps, text or compose | `GET /install/{session_id}[/text|/compose]` (`routers/installer.py:145`) |
| `get_promote` | `session_id` | promotion candidates | `GET /promote/{session_id}` (`routers/promote.py:51`) |

## Tools — drift and config

| Tool | Params | Returns | Backs onto |
|---|---|---|---|
| `drift_status` | — | current drift against the baseline | `GET /drift/status` (`routers/drift.py:15`) |
| `drift_history` | — | drift over time | `GET /drift/history` (`routers/drift.py:30`) |
| `llm_status` | — | which providers are configured and reachable | `GET /config/llm-status` (`routers/config.py:134`) |

`llm_status` is worth having: after the 2026-08-23 decision the provider chain
is `openrouter → ollama`, and "which one actually answered" is a real question
when a clustering run behaves oddly.

## Resources

| URI | Contents |
|---|---|
| `gitsuite://plan` | the current plan, as a cheap read |
| `gitsuite://drift` | latest drift status |
| `gitsuite://config` | active config — **LLM keys redacted** |

## What must NOT be a tool

- **`DELETE /plan/hub/{name}`, `DELETE /plan/forbid`, `DELETE /cluster/{id}`.**
  Destructive and session-scoped; an agent deleting a hub mid-review loses work
  that took an LLM run to produce.
- **Execution.** `preview_execute` is exposed; actually executing is not. The
  execute stage moves real repositories. Preview is the honest half.
- **`GET /gh-token`** (`routers/auth.py:61`) — never. That is a GitHub
  credential; a tool returning it puts it in a model's context.
- **Anything under `/config` that writes.** Provider keys are entered on the
  Setup page.

## Note on the push action

`Push ALIGNMENT.md` writes a file into a real repository. It now lives in a
footer under the align panel precisely because it is the one destructive-ish
control on that page (decided 2026-08-23). Same logic applies here: it should
not become a tool. `get_align_audit`-style **reads** are fine; the push is not.

## Implementation note

Every router is already session-scoped and returns JSON the UI renders, so the
MCP layer is an adapter with no logic of its own. The 195 backend tests cover
the routers; a server that only reads them needs no new test surface beyond
"the tool passes the session id through".
