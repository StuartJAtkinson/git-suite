# Grouping — git-suite

The pre-plan working state that turns clustering from a one-shot render into a
**checkpointed, human-in-the-loop refinement**. This is the method: the LLM does
the semantic checks (merge / split / move / rename / ask), the human approves,
and every repo carries a durable mark so the walk resumes exactly where it stopped.

See `MCP.md` for the server this is meant to be operated through. This doc is the
method; `routers/grouping.py` + `grouping_store.py` are the first slice of it.

---

## Why the ledger, not a re-cluster

The older Cluster page handed the human merge/split/move buttons; the one-shot
"re-cluster everything" loop re-litigates the whole portfolio each round and
remembers nothing. Both are the same disease from opposite sides — *no durable
record of what's already decided.*

The fix: a **ledger** with one row per repo, four marks, and a loop that only
touches the unsettled. Settled repos are frozen, so the work converges instead of
thrashing, and the state resists app restarts.

## The ledger

`~/.git-suite/grouping.json` (portfolio-scoped, not session-scoped), beside
`plan.json`:

```
statuses:  repo_key -> { status, clump, confidence, why }
clumps:    slug -> { name, description, confidence }
answers:   [ { question, answer } ]      # semantic decisions already made
pending:   [ deltas awaiting approval ]  # step 2
round:     int
floor:     float  (default 0.85)
```

Per-repo marks:

| status | meaning | set by |
|---|---|---|
| `unsettled` | not placed yet | round 0 |
| `proposed(X)` | LLM placed it, awaiting confirmation | LLM |
| `settled(X)` | human confirmed → frozen | human |
| `ambiguous` | parked until a semantic answer resolves it | LLM |

## The loop

One fixed three-step round, no buttons in the UI:

1. **Propose** — the LLM reads the ledger (settled frozen) and emits *only*
   unresolved changes as typed deltas with a rationale + confidence:
   `merge(A,B→name)` · `split(X,members→name)` · `move(repo,X→Y)` ·
   `rename(X→name)`, or `question(repos,text,options)` when it can't decide.
2. **Approve** — the human approves/edits/rejects deltas; a `question` needs an
   answer. Approving commits the coin to the ledger (repo → `settled`).
3. **Repeat** until nothing remains above the floor and no questions → *settled*.

**The propose step runs in chunks.** One call per group of clumps (8 at a
time), not one call over the whole ledger: at round 0 the ledger is every repo
in the portfolio — ~24.5K tokens — which no local model answers inside any
sane timeout, and a provider that is down would otherwise be waited on once
per clump. Each call sees its clumps' members in full and the rest by name and
size; the deltas merge into one pending list (10 at a time, de-duplicated).

Confidence gates the human out of the boring work: deltas above `floor` apply
automatically; only below-floor deltas and `question`s reach the human.

`rename` is how a clump becomes the user's "software ideal" project name. The walk
*ends* at the ledger; promotion to a hub stays on Own / `plan.json`.

## MCP surface

Operated over the same read + propose + record philosophy as `MCP.md` — nothing
here ever pushes to GitHub.

| Primitive | Name | Backs onto |
|---|---|---|
| Resource | `git-suite://ledger` | `GET /api/grouping` |
| Resource | `git-suite://clumps/{slug}` · `git-suite://repos/{key}` | ledger subset |
| Tool | `propose_next` | LLM → deltas (long-running via Tasks) |
| Tool | `apply_delta(id, approve\|reject, edits?)` | commit a delta |
| Tool | `answer_question(id, answer)` | record a semantic answer |
| Tool | `set_floor(x)` · `settle(repo, clump?)` | tune / override |
| Elicitation | — | surface a `question` / below-floor delta to the human |

Destructive actions (promote, execute) stay out of the tool surface.

## Status

- [x] **Step 1 — the ledger.** `grouping_store.py` (persist/seed/summary),
      `routers/grouping.py` (`GET /api/grouping`, `POST /api/grouping/reset`),
      seeded on every Cluster group/import. Marks are `proposed`/`unsettled`.
- [x] **Step 2 — deltas.** `topic_llm.propose_deltas` emits targeted
      `merge/split/move/rename/question` deltas over the ledger;
      `grouping_store.apply_delta` commits them and settles the repos they
      place; settled repos freeze (rejected from move/split). Routed at
      `POST /api/cluster/{sid}/propose` + `/apply`.
- [x] **Step 3 — the MCP adapter.** `mcp_server.py` (stdio, `mcp>=2`) exposes
      the ledger as `gitsuite://ledger` / `gitsuite://summary` /
      `gitsuite://clumps/{slug}` resources and `propose_next` / `apply_delta` /
      `answer_question` / `set_floor` / `settle` tools — thin adapters over
      `grouping_store` + `topic_llm`, no grouping logic of their own. Run with
      `python -m mcp_server`.
