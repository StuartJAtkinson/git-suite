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
# Plan data
# ---------------------------------------------------------------------------

NEW_REPOS = {
    "personal-ai-os": {
        "layer":       3,
        "priority":    2,
        "description": "Unified local AI OS — RAG, memory, email ingestion, emotional events",
        "absorbs": [
            "quivr",               # RAG over personal docs
            "EMailParseAI",        # email ingestion
            "heart-on-a-sleeve",   # emotional event tracker
            "gsd-work",            # personal GTD (moved from work-hub — personal scope)
            "LangFlowProject",     # agentic workflow experiments
            "Multi-agent-DataAnalysis",  # LangGraph research pipeline
            "MultiCoT",            # chain-of-table reasoning
            "STTScrape",           # speech-to-text transcript extraction
        ],
    },
    "ontology-align": {
        "layer":       1,
        "priority":    1,
        "description": "Validates and aligns ontological schemas across repos",
        "absorbs": [
            "place-time",              # H3 spatial-temporal ontology (L1 not L5 — classification system)
            "ontologiesUK",            # UK Parliament/ONS ontology
            "CommonCoreOntologies",    # enterprise knowledge ontology
            "federated-api-model",     # government API ontology
            "IAO",                     # Information Artifact Ontology
            "Sagex3-Script-Parser",    # formal grammar for Sage X3 ERP — schema/language tool
            "UKPoliticsData",          # UK open political data → graph DB
            "neo4J-SQL-Graphs",        # Neo4j + SQL graph unification
        ],
    },
    "homelab-core": {
        "layer":       8,
        "priority":    1,
        "description": "Self-hosted infrastructure control plane — service discovery, secrets, stack deployment and homelab orchestration",
        "absorbs": [
            "homelab-designer",        # scrapes app registries, generates install plans
            "homelab-discovery",       # service discovery and inventory
            "infisical",               # secrets and privileged access management
            "orchestration-stack",     # Traefik + monitoring + AI orchestration stack
            "ai-work-orchestration",   # Vikunja + Formbricks + AI infra (moved from work-hub — it's deployment)
            "winutil",                 # Windows tweaks/installs via PowerShell
            "linutil",                 # Linux toolbox for installs/tweaks
            "fusio",                   # API management gateway
        ],
    },
    "work-hub": {
        "layer":       2,
        "priority":    2,
        "description": "Self-hosted professional work management — tickets, CRM and project tools",
        # Trimmed to purely professional scope.
        # ai-work-orchestration → homelab-core (it's infra deployment, not work management)
        # gsd-work → personal-ai-os (personal GTD, not professional workflow)
        "absorbs": [
            "guided-tickets",          # Zoho-backed guided support ticketing
            "jira-dependency-graph",   # Jira project/issue graph visualisation
            "ZohoAPI",                 # Zoho CRM integration
            "Jira-Lens",               # Jira analysis tool
        ],
    },
    "media-hub": {
        "layer":       4,
        "priority":    3,
        "description": "Unified media ingestion — social archives, comics, photos and video",
        "absorbs": [
            "socialMediaArchiver",     # social content archiver
            "YouTubeCommunityPosts",   # YouTube community post scraper
            "simklExporter",           # TV/anime watch history export
            "CBL-ReadingLists",        # comic reading orders
            "marvel-comics-api",       # Marvel comics API client
            "EXIF-SpaceTime",          # photo EXIF geolocation/time editor
            "tweetext",                # Wayback Machine tweet recovery
            "comictagger",             # digital comic metadata tagger
            "linkedin-api",            # LinkedIn data tools
            "TagStudio",               # photo/file management with tagging
            "ClipsReview",             # video clip review tool
            "autoEdit_2",              # automated video editing
            "intelli-video",           # intelligent video processing
            "AIPhotoRestore",          # AI photo restoration
        ],
    },
    "map-suite": {
        "layer":       5,
        "priority":    2,
        "description": "OSM-based unified mapping — indoor, outdoor, 3D and procedural fantasy",
        # place-time removed — ontological system belongs in ontology-align (L1)
        "absorbs": [
            "qgis-mcp",                # QGIS + Claude AI via MCP (owned)
            "Fantasy-Map-Generator",   # procedural fantasy map generation
            "planetiler",              # planet-scale vector tile generator
            "OSM2World",               # OSM → 3D world models
            "streets-gl",              # WebGL OSM 3D renderer
            "openindoor6",             # indoor mapping and routing
            "OsmGo",                   # mobile OSM field editing
            "worldengine",             # procedural world simulation (plates, erosion)
        ],
    },
    "game-hub": {
        "layer":       6,
        "priority":    3,
        "description": "Unified gaming platform — FFXIV toolkit, Pokemon, Zelda, Steam and TTRPG",
        "absorbs": [
            # FFXIV
            "FFXIVQuestMap",           # FFXIV quest dependency map (owned)
            "FFXIVAPI",                # FFXIV data extraction scripts (owned)
            "AllaganTools",            # FFXIV inventory/market Dalamud plugin
            "Lumina",                  # FFXIV game data C# framework
            "XIVSlothCombo",           # FFXIV rotation helper plugin
            # Pokemon / Zelda
            "PokeManager",             # Pokemon Go mass-transfer tool (owned)
            "Pokedex-RL",              # real-life Pokedex via photo (owned)
            "ZeldaRecipes",            # Zelda ingredient recipe finder (owned)
            "BOTW-Recipes",            # BOTW recipe reference (owned)
            "BlossomsPokemonGoManager",# Pokemon Go manager (owned)
            "Pogo-Account-Checker",    # Pokemon Go PTC account checker (owned)
            "GoDex",                   # Go-based Pokedex (owned)
            "PokemonGo-Bot",           # Pokemon Go automation (owned)
            "botw-tools",              # BOTW tools (owned)
            # Other games
            "d4buildsAPI",             # Diablo 4 build data scraper (owned)
            "gwSkills",                # Guild Wars 2 skills reference (owned)
            "DungeonGeneration",       # procedural dungeon generation (owned)
            # TTRPG
            "Chronicle-Keeper",        # AI GM assistant for TTRPG campaigns (owned)
            "foundryvtt-session-scheduler", # Foundry VTT session scheduling (owned)
            "dnd-aMagaAdventure",      # D&D adventure content (owned)
            "Armoria",                 # heraldry generator — worldbuilding/creative
        ],
    },
    "code-suite": {
        "layer":       7,
        "priority":    4,
        "description": "Unified code management — bulk ops, semantic search, code graph and cheatsheets",
        "absorbs": [
            "DoIHaveEverything",       # repo inventory checker (owned)
            "Coding-Cheatsheets",      # personal coding cheatsheet notebooks (owned)
            "CodeAtlasVsix",           # graph-based code navigation VS plugin (owned)
            "SQLFluffParsing",         # SQL parsing/linting exploration (owned)
            "ClickTheseThings",        # UI element auto-clicker automation (owned)
            "Page-Manipulator",        # page/DOM manipulation tool (owned)
            "RepoReader",              # repo content reader (owned)
            "bytebytego-grabber",      # ByteByteGo content scraper (owned)
            "bloop",                   # semantic code search engine
            "all-repos",               # bulk git repo operations
            "astral",                  # GitHub stars organiser
        ],
    },
}

# Archive targets: repo → hub they belong to (None = retire regardless, no hub needed)
ARCHIVE_HUB: dict[str, str | None] = {
    # work-hub era
    "belzona-tickets":                    "work-hub",
    "JiraApp":                            "work-hub",
    # game-hub era
    "FFXIV-Scraping":                     "game-hub",
    "FFXIVPlugin":                        "game-hub",
    "InteractiveMaps":                    "game-hub",
    "Tetra-Master-Clone":                 "game-hub",
    "TownGeneratorOS":                    "game-hub",
    "botwr":                              "game-hub",
    "donjonrp":                           "game-hub",
    "dummy-sheet":                        "game-hub",
    # media-hub era
    "ClipsReview":                        "media-hub",
    "TagStudio":                          "media-hub",
    "restorePhotos":                      "media-hub",
    "twitterscraper":                     "media-hub",
    # homelab-core era
    "mRemoteNG":                          "homelab-core",
    "linutil":                            "homelab-core",
    # ontology-align era
    "Ontologies":                         "ontology-align",
    "opencyc":                            "ontology-align",
    # code-suite era
    "html-tree-generator__chrome-extension": "code-suite",
    "UsefulCodeToMakeGists":              "code-suite",
    # no hub — retire whenever
    "Newtonian-Particle-Simulator":       None,
    "MarvelGraph":                        None,
    "prettymaps":                         None,
    "webmapper":                          None,
    "FreshView":                          None,
    "ReverseYoutubePlaylist":             None,
    "infranodus":                         None,
    "John-Watson-Guides":                 None,
    "MTGScrape":                          None,
    "SteamScrape":                        None,
    "ChronoZoom":                         None,
    "chromeos-apk":                       None,
    "windows95":                          None,
    "esoteric-streamer":                  None,
    "nouns-ai-sd-server":                 None,
    "pc-part-dataset":                    None,
    "VTuberLIVE":                         None,  # L9 Creative has no hub yet
    "ai-demos":                           None,
}

ARCHIVE_TARGETS = set(ARCHIVE_HUB.keys())

# Repos that stay standalone — working tools, libraries, forks used as references.
# Not absorbed into a hub, not archived.
KEEP_AS_IS = {
    # XIVAPI site repo — reference, not a merge target
    "xivapi.com",
    # Genealogy cluster
    "AncestryBrowsableSchema",
    "FTAnalyzer",
    "wikitree-sourcer",
    # AI agent frameworks (forks/references — influence personal-ai-os but stay separate)
    "Archon",
    "OpenDevin",
    "agent-zero",
    "crewAI",
    "crewAI-examples",
    "crawl4ai",
    "portia",
    "headless-recorder",
    "langgraph-search-agents",
    "rag-from-scratch",
    "llm-answer-engine",
    "kg_llm",
    # ActivityWatch integrations (working, standalone)
    "aw-import-ical",
    "aw-watcher-ask",
    # Libraries / visualisation dependencies
    "GoJS",
    "jsoncrack.com",
    "venn.js",
    "segment-anything",
    # Browser extensions (working, self-contained)
    "YouTubeExtension",
    "free-map-genie",
    # This repo itself
    "git-suite",
}

LAYER_NAMES = {
    0: "Event Bus & Dispatch",
    1: "Ontological Backbone",
    2: "Automation & Workflow",
    3: "Knowledge & RAG",
    4: "Media & Archiving",
    5: "GIS & Maps",
    6: "Game & Entertainment",
    7: "Dev & Code Tools",
    8: "Homelab & Infra",
    9: "Creative & Graphics",
}

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
