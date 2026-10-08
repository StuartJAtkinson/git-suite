# Roadmap — git-suite

> **Auto Continue reads this file.** The `feature` phase takes the first unchecked
> `- [ ]` line below as its whole brief and ticks it by exact text, so milestones and
> phases are headings and every slice is one commit-sized, self-contained line.
> **Human-only** items carry no checkbox, so Auto never picks them up.

**Now:** no milestone queued — Phases 1–4 and Later are shipped (Phase 4 marked ✅
2026-09-29). Reviewed 2026-10-09: the next real work is a human taxonomy walk, not a feature.
Docker deployment was removed on purpose (2026-07-23), so no deploy milestone either.

**Human-only:** answer the 15 taxonomy questions in CONSIDERATIONS.md. They are numbered
(`1.`), which Auto's pause count and interview don't see yet — atelier-harness ROADMAP M2b
fixes that.

Self-hosted web app for consolidating a sprawling GitHub portfolio into a small
set of maintained "hubs" (absorb / archive / keep). Hubs are not predefined — they
emerge from the live GitHub scan (cluster → promote/create) and are processed
manually with assistance; planning is cheap/local/reversible, execution is a
separate deliberate step against GitHub.

> This file is the original high-level status summary, kept terse. For the
> live architecture, page-by-page behavior, and the detailed unbuilt-steps
> pipeline (5–8 below), see **[`ui/ROADMAP.md`](ui/ROADMAP.md)** — that doc is
> the one that gets updated as the app changes; this one just tracks phase
> completion.

## Phase 1 — Scan & plan ✅
- [x] Scan owned repos (public + private)
- [x] Per-repo decision: absorb / archive / keep
- [x] Local, reversible plan model

## Phase 2 — Execute ✅
- [x] Apply decisions back to GitHub (archive, create hub, push README)
- [x] Dry-run / diff before execution (Execute page preview)
- [x] Absorb flow: move a repo's *content* into a hub with history preserved —
      still manual (git detach checklist); no automated transfer/rename

## Phase 3 — Hubs ✅
- [x] Let hub structure emerge from the scan (LLM one-shot theme grouping →
      promote/create; k-means fallback removed 2026-07-23)
- [x] Track which repos each hub has absorbed (`plan.json` hubs[].absorbs)
- [x] Re-scan to verify portfolio matches target (Reconcile / Summary pages)

## Phase 4 — Feature-level pipeline ✅
The pipeline beyond repo-level absorb: analyse each repo's *features*,
recommend which features from stars/forks to fold into an owned repo (not
the whole repo into a hub), align design principles across a hub, and end as
a guided installer. All eight architecture steps are built — see `ui/ROADMAP.md`'s
"Architecture model" section for the per-step status. Open follow-on work
lives in `ISSUES.md`.

## Later
- [x] Scheduled portfolio drift checks
- [x] One-click "align docs" across a hub (this sweep, automated)

*Updated 2026-09-29 — Phase 4 marked ✅ (all eight architecture steps are built; see
`ui/ROADMAP.md`). Previously said "in progress" since 2026-09-06.*
