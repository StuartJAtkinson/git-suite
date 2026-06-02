"""
portfolio_review.py
Iterative portfolio health check — run after create/archive/absorb actions.

Modes:
    python portfolio_review.py                  # full review (reads github_index.csv)
    python portfolio_review.py --refresh        # re-fetches GitHub data first
    python portfolio_review.py --hub game-hub   # focused per-hub review (stdout)
    python portfolio_review.py --check-hubs     # query GitHub directly for hub existence

Phases (full mode):
  1. Hub targets    — which of the 8 hubs exist on GitHub
  2. Archive queue  — archives grouped by hub (do hub-by-hub)
  3. Absorptions    — per-hub gaps + category spread (flags potential splits)
  4. Layer audit    — cross-layer conflicts and orphan repos
"""

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_HERE       = Path(__file__).parent
CSV_IN      = _HERE / "github_index.csv"
GITHUB_USER = "StuartJAtkinson"

# ---------------------------------------------------------------------------
# Plan data — single source of truth is the web app's seed (ui/backend/plan.py),
# which feeds plan_store / ~/.git-suite/plan.json. This CLI derives its view
# from that seed so the two can never drift again. Edit the plan there, not here.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(_HERE / "ui" / "backend"))
import plan as _seed  # noqa: E402

NEW_REPOS = {
    name: {
        "layer":       meta["layer"],
        "priority":    meta["priority"],
        "description": meta["description"],
        "absorbs":     list(_seed.HUB_ABSORBS.get(name, [])),
    }
    for name, meta in _seed.HUB_META.items()
}

# Archive targets: repo → hub they belong to (None = retire regardless).
ARCHIVE_HUB: dict[str, str | None] = dict(_seed.ARCHIVE_HUB)
ARCHIVE_TARGETS = set(ARCHIVE_HUB.keys())

# Repos that stay standalone — working tools, libraries, reference forks.
KEEP_AS_IS = set(_seed.KEEP_AS_IS)

LAYER_NAMES = dict(_seed.LAYER_NAMES)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_csv():
    if not CSV_IN.exists():
        print(f"[!!] {CSV_IN} not found — run: python generate_github_index.py --no-sbom")
        sys.exit(1)
    with open(CSV_IN, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def repo_names(rows):
    return {r["Name"].strip() for r in rows}


def cat_map(rows):
    return {
        r["Name"].strip(): (r.get("Super", ""), r.get("Mid", ""), r.get("Fine", ""))
        for r in rows
    }


def _gh(*args):
    r = subprocess.run(
        ["cmd.exe", "/c", "gh", *args],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    return r.stdout.strip() if r.returncode == 0 else None


def sep(title="", width=72):
    if title:
        pad = max(2, width - len(title) - 4)
        print(f"\n== {title} {'=' * pad}")
    else:
        print("=" * width)


def pbar(done, total, width=12):
    if total == 0:
        return "[" + "#" * width + "]  100%"
    pct  = int(100 * done / total)
    fill = int(width * done / total)
    return f"[{'#' * fill}{'-' * (width - fill)}]  {pct:3d}%"


def run_refresh():
    print("[>>] Refreshing GitHub index (fast, no SBOM)...")
    subprocess.run([sys.executable, str(_HERE / "generate_github_index.py"), "--no-sbom"], check=True)
    print("[>>] Rebuilding prompt groups...")
    subprocess.run([sys.executable, str(_HERE / "build_prompts.py"), "--prompts-only"], check=True)

# ---------------------------------------------------------------------------
# Hub existence — direct GitHub query
# ---------------------------------------------------------------------------

def check_hubs_live():
    print("Querying GitHub for hub repos...")
    out = _gh("repo", "list", GITHUB_USER, "--limit", "300", "--json", "name")
    if not out:
        print("[!!] GitHub query failed — is gh authenticated?")
        return set()
    names = {r["name"] for r in json.loads(out)}
    created, missing = [], []
    for name in sorted(NEW_REPOS):
        exists = name in names
        print(f"  {'[OK]' if exists else '[--]'} {name}")
        (created if exists else missing).append(name)
    print(f"\n  {len(created)}/8 hubs exist on GitHub")
    return set(created)

# ---------------------------------------------------------------------------
# Phase 1 — Hub status
# ---------------------------------------------------------------------------

def phase_new_repos(live):
    sep("PHASE 1 — Hub Repo Targets")
    created, missing = [], []
    for name, info in sorted(NEW_REPOS.items(), key=lambda x: x[1]["priority"]):
        exists = name in live
        layer  = f"L{info['layer']}"
        print(f"  {'[OK]' if exists else '[--]'} {name:<22} {layer}  P{info['priority']}  {info['description'][:45]}")
        (created if exists else missing).append(name)
    nxt = NEW_REPOS[missing[0]]["description"] if missing else "all done"
    print(f"\n  {len(created)}/8 created  |  next: {nxt}")
    return set(created)

# ---------------------------------------------------------------------------
# Phase 2 — Archive queue, grouped by hub
# ---------------------------------------------------------------------------

def phase_archive(live):
    sep("PHASE 2 — Archive Queue (hub-by-hub)")

    by_hub: dict[str | None, list[str]] = defaultdict(list)
    for repo, hub in ARCHIVE_HUB.items():
        by_hub[hub].append(repo)

    total_done = 0

    for hub in sorted(h for h in by_hub if h is not None):
        targets = sorted(by_hub[hub])
        live_t  = [r for r in targets if r in live]
        done_n  = len(targets) - len(live_t)
        total_done += done_n
        print(f"\n  {hub}  {pbar(done_n, len(targets), 8)}  ({done_n}/{len(targets)})")
        for r in live_t:
            print(f"    [--] {r}")
        if not live_t:
            print(f"    [OK] clean")

    orphan = sorted(by_hub[None])
    live_o  = [r for r in orphan if r in live]
    done_o  = len(orphan) - len(live_o)
    total_done += done_o
    print(f"\n  (no hub — retire anytime)  {pbar(done_o, len(orphan), 8)}  ({done_o}/{len(orphan)})")
    for r in live_o:
        print(f"    [--] {r}")
    if not live_o:
        print(f"    [OK] clean")

    print(f"\n  Overall: {total_done}/{len(ARCHIVE_TARGETS)} archived")
    return {r for r in ARCHIVE_TARGETS if r in live}

# ---------------------------------------------------------------------------
# Phase 3 — Absorptions per hub + split signals
# ---------------------------------------------------------------------------

def _split_signal(absorb_cats):
    counts = defaultdict(int)
    for s, _, _ in absorb_cats.values():
        if s:
            counts[s] += 1
    return sorted(counts.items(), key=lambda x: -x[1])


def phase_absorptions(live, created, cats):
    sep("PHASE 3 — Absorptions + Split Signals")

    if not created:
        print("  No hub repos exist yet.")
        return {}

    all_gaps = {}
    for name in sorted(created, key=lambda n: NEW_REPOS[n]["priority"]):
        info      = NEW_REPOS[name]
        targets   = info["absorbs"]
        still_sep = [r for r in targets if r in live]
        absorbed_n = len(targets) - len(still_sep)

        print(f"\n  {name}")
        print(f"    {pbar(absorbed_n, len(targets))}")

        absorb_cats = {r: cats.get(r, ("?", "?", "?")) for r in targets}
        supers = _split_signal(absorb_cats)
        if len(supers) > 1:
            spread = "  ".join(f"{s}({n})" for s, n in supers)
            flag   = "  [!!] SPLIT?" if len(supers) >= 4 else ""
            print(f"    categories: {spread}{flag}")

        for r in sorted(still_sep):
            sup = absorb_cats.get(r, ("?",))[0]
            print(f"    [--] {r:<32}  ({sup})")
        if not still_sep:
            print(f"    [OK] all absorbs gone")

        all_gaps[name] = set(still_sep)

    return all_gaps

# ---------------------------------------------------------------------------
# Phase 4 — Layer audit
# ---------------------------------------------------------------------------

def phase_layer_audit(live):
    sep("PHASE 4 — Layer Separation Audit")

    claim_map: dict[str, list[str]] = defaultdict(list)
    for hub, info in NEW_REPOS.items():
        for r in info["absorbs"]:
            claim_map[r].append(hub)
    cross = {r: hubs for r, hubs in claim_map.items() if len(hubs) > 1}

    if cross:
        print("  Cross-layer conflicts:")
        for r, hubs in sorted(cross.items()):
            print(f"    [!!] {r:<32} <- {', '.join(hubs)}")
    else:
        print("  [OK] No cross-layer conflicts.")

    all_known = (
        set(NEW_REPOS.keys())
        | ARCHIVE_TARGETS
        | KEEP_AS_IS
        | {r for info in NEW_REPOS.values() for r in info["absorbs"]}
    )
    orphans = sorted(live - all_known)
    if orphans:
        print(f"\n  Unplanned repos ({len(orphans)}) — assign to a hub, keep-as-is, or archive:")
        for r in orphans:
            print(f"    [??] {r}")
    else:
        print("\n  [OK] All live repos accounted for.")

    return cross, set(orphans)

# ---------------------------------------------------------------------------
# --hub mode: focused single-hub review for in-session use
# ---------------------------------------------------------------------------

def hub_review(hub_name, live, cats):
    if hub_name not in NEW_REPOS:
        print(f"[!!] Unknown hub '{hub_name}'. Valid: {', '.join(sorted(NEW_REPOS))}")
        sys.exit(1)

    info      = NEW_REPOS[hub_name]
    targets   = info["absorbs"]
    still_sep = [r for r in targets if r in live]
    arch_list = sorted(r for r, h in ARCHIVE_HUB.items() if h == hub_name and r in live)

    sep(f"HUB REVIEW — {hub_name}")
    print(f"  Layer    : L{info['layer']} — {LAYER_NAMES.get(info['layer'], '')}")
    print(f"  Priority : P{info['priority']}")
    print(f"  Purpose  : {info['description']}")
    print(f"  Exists   : {'YES' if hub_name in live else 'NO — create this repo first'}")

    sep("Absorb targets")
    absorb_cats = {r: cats.get(r, ("?", "?", "?")) for r in targets}
    for r in targets:
        sup, mid, _ = absorb_cats[r]
        status = "[--] still live" if r in live else "[OK] gone    "
        print(f"  {status}  {r:<32}  {sup} / {mid}")

    supers = _split_signal(absorb_cats)
    print(f"\n  Category spread: {', '.join(f'{s}({n})' for s,n in supers)}")
    if len(supers) >= 4:
        print("  [!!] Wide spread — consider splitting:")
        for s, n in supers:
            members = [r for r in targets if absorb_cats.get(r, ("",))[0] == s]
            print(f"       {s}: {', '.join(members)}")

    if arch_list:
        sep("Archive alongside this hub")
        for r in arch_list:
            print(f"  [--] {r}")

    sep("Summary")
    print(f"  Absorb  ({len(still_sep)} remaining): {', '.join(still_sep) or 'none'}")
    print(f"  Archive ({len(arch_list)} remaining): {', '.join(arch_list) or 'none'}")
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--refresh",     action="store_true",
                        help="Re-fetch GitHub data before reviewing")
    parser.add_argument("--check-hubs",  action="store_true",
                        help="Query GitHub directly for hub repo existence")
    parser.add_argument("--hub",         metavar="NAME",
                        help="Focused review of one hub (stdout, for in-session use)")
    args = parser.parse_args()

    if args.check_hubs:
        check_hubs_live()
        return

    if args.refresh:
        run_refresh()

    rows = load_csv()
    live = repo_names(rows)
    cats = cat_map(rows)
    print(f"Loaded {len(live)} repos from {CSV_IN.name}")

    if args.hub:
        hub_review(args.hub, live, cats)
        return

    sep()
    created        = phase_new_repos(live)
    still_archive  = phase_archive(live)
    gaps           = phase_absorptions(live, created, cats)
    cross, orphans = phase_layer_audit(live)

    sep()
    print("\nCYCLE COMPLETE — take actions, then re-run:")
    print("  python portfolio_review.py                  # re-check")
    print("  python portfolio_review.py --refresh        # re-fetch + re-check")
    print("  python portfolio_review.py --hub <name>     # focused hub review")
    print("  python portfolio_review.py --check-hubs     # query GitHub directly")
    print()


if __name__ == "__main__":
    main()
