# Roadmap — git-suite

Self-hosted web app for consolidating a sprawling GitHub portfolio into a small
set of maintained "hubs" (absorb / archive / keep). The portfolio target lives in
[`PLAN.md`](PLAN.md); planning is cheap/local/reversible, execution is a separate
deliberate step against GitHub.

## Phase 1 — Scan & plan ✅
- [x] Scan owned repos (public + private)
- [x] Per-repo decision: absorb / archive / keep
- [x] Local, reversible plan model

## Phase 2 — Execute
- [ ] Apply decisions back to GitHub (archive, transfer, rename)
- [ ] Absorb flow: move a repo's content into a hub with history preserved
- [ ] Dry-run / diff before execution

## Phase 3 — Hubs
- [ ] Define hub/layer structure from PLAN.md
- [ ] Track which repos each hub has absorbed
- [ ] Re-scan to verify portfolio matches target

## Later
- [ ] Scheduled portfolio drift checks
- [ ] One-click "align docs" across a hub (this sweep, automated)
