"""
init_hub_readmes.py
Writes an Integration Roadmap section to each hub repo's README.md.

Inserts (or replaces) the section immediately after the first # heading, covering:
  - My projects to absorb (linked, with aim pulled from github_index.csv)
  - Open-source inspiration projects
  - Commercial benchmarks
  - 2-way sync goal statement

Usage:
    python init_hub_readmes.py                      # prompts for suite root
    python init_hub_readmes.py --hub game-hub       # single hub only
    python init_hub_readmes.py --root D:\\repos     # skip the prompt
    python init_hub_readmes.py --dry-run            # print without writing
"""

import argparse
import csv
import re
import sys
from pathlib import Path

_HERE       = Path(__file__).parent
CSV_IN      = _HERE / "github_index.csv"
GITHUB_USER = "StuartJAtkinson"
DEFAULT_ROOT = Path(r"H:\GitHub")

SECTION_START = "<!-- integration-roadmap-start -->"
SECTION_END   = "<!-- integration-roadmap-end -->"

# ---------------------------------------------------------------------------
# Hub plan data (absorbs) — keep in sync with portfolio_review.py
# ---------------------------------------------------------------------------

HUB_ABSORBS = {
    "personal-ai-os": [
        "quivr", "EMailParseAI", "heart-on-a-sleeve", "gsd-work",
        "LangFlowProject", "Multi-agent-DataAnalysis", "MultiCoT", "STTScrape",
    ],
    "ontology-align": [
        "place-time", "ontologiesUK", "CommonCoreOntologies", "federated-api-model",
        "IAO", "Sagex3-Script-Parser", "UKPoliticsData", "neo4J-SQL-Graphs",
    ],
    "homelab-core": [
        "homelab-designer", "homelab-discovery", "infisical", "orchestration-stack",
        "ai-work-orchestration", "winutil", "linutil", "fusio",
    ],
    "work-hub": [
        "guided-tickets", "jira-dependency-graph", "ZohoAPI", "Jira-Lens",
    ],
    "media-hub": [
        "socialMediaArchiver", "YouTubeCommunityPosts", "simklExporter",
        "CBL-ReadingLists", "marvel-comics-api", "EXIF-SpaceTime", "tweetext",
        "comictagger", "linkedin-api", "TagStudio", "ClipsReview",
        "autoEdit_2", "intelli-video", "AIPhotoRestore",
    ],
    "map-suite": [
        "qgis-mcp", "Fantasy-Map-Generator", "planetiler", "OSM2World",
        "streets-gl", "openindoor6", "OsmGo", "worldengine",
    ],
    "game-hub": [
        "FFXIVQuestMap", "FFXIVAPI", "AllaganTools", "Lumina", "XIVSlothCombo",
        "PokeManager", "Pokedex-RL", "ZeldaRecipes", "BOTW-Recipes",
        "BlossomsPokemonGoManager", "Pogo-Account-Checker", "GoDex", "PokemonGo-Bot",
        "botw-tools", "d4buildsAPI", "gwSkills", "DungeonGeneration",
        "Chronicle-Keeper", "foundryvtt-session-scheduler", "dnd-aMagaAdventure", "Armoria",
    ],
    "code-suite": [
        "DoIHaveEverything", "Coding-Cheatsheets", "CodeAtlasVsix", "SQLFluffParsing",
        "ClickTheseThings", "Page-Manipulator", "RepoReader", "bytebytego-grabber",
        "bloop", "all-repos", "astral",
    ],
}

# OSS and commercial alternatives per hub
# These are the projects to analyse features from and eventually sync with
HUB_ALTERNATIVES = {
    "personal-ai-os": {
        "oss": [
            "Jan", "anything-llm", "open-webui", "kotaemon",
            "LangFlow", "n8n", "Flowise", "mem0",
        ],
        "commercial": [
            "ChatGPT", "Notion AI", "mem.ai", "Superhuman",
            "Replika", "Woebot", "Perplexity",
        ],
    },
    "ontology-align": {
        "oss": [
            "Protégé", "RDFLib", "ROBOT", "Apache Jena",
            "ThesauRex", "Skosmos", "VocBench", "SHACL Playground",
        ],
        "commercial": [
            "TopBraid Composer", "PoolParty", "Palantir Ontology",
            "Stardog", "Ontotext GraphDB",
        ],
    },
    "homelab-core": {
        "oss": [
            "Portainer", "Coolify", "Runtipi", "Umbrel",
            "Ansible", "Terraform", "Pulumi", "Consul", "Dockge",
        ],
        "commercial": [
            "Portainer Business", "Replicated", "Temporal Cloud",
            "HashiCorp Cloud", "Doppler",
        ],
    },
    "work-hub": {
        "oss": [
            "Vikunja", "Plane", "AppFlowy", "n8n",
            "Taiga", "Gitea Issues", "tegon", "twenty",
        ],
        "commercial": [
            "Jira", "Monday.com", "ClickUp", "Zoho CRM",
            "Linear", "Asana", "Salesforce", "HubSpot",
        ],
    },
    "media-hub": {
        "oss": [
            "Immich", "Jellyfin", "Kavita", "Paperless-ngx",
            "ArchiveBox", "Suwayomi-Server", "Komga",
        ],
        "commercial": [
            "Google Photos", "Adobe Lightroom", "Frame.io",
            "Simkl", "Marvel Unlimited", "Plex", "Archive.social",
        ],
    },
    "map-suite": {
        "oss": [
            "QGIS", "OpenLayers", "Leaflet", "CesiumJS",
            "MapLibre GL", "OpenMapTiles", "Azgaar Fantasy Map",
        ],
        "commercial": [
            "ESRI ArcGIS", "Mapbox", "HERE Maps",
            "Google Maps Platform", "Felt", "MapInfo Pro",
        ],
    },
    "game-hub": {
        "oss": [
            "Playnite", "Foundry VTT", "Universalis",
            "Garland Tools", "XIVAPI", "WoWAnalyzer",
        ],
        "commercial": [
            "DnDBeyond", "WorldAnvil", "Steam", "Battle.net",
            "SquareEnix Companion App", "Overwolf",
        ],
    },
    "code-suite": {
        "oss": [
            "Sourcegraph OSS", "Gitea", "aider", "OpenGrok",
            "code2flow", "Understand (SciTools trial)",
        ],
        "commercial": [
            "GitHub", "Sourcegraph Enterprise", "JetBrains Fleet",
            "CodeMR", "SciTools Understand",
        ],
    },
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_aims() -> dict[str, str]:
    if not CSV_IN.exists():
        return {}
    with open(CSV_IN, encoding="utf-8-sig") as f:
        return {
            r["Name"].strip(): (r.get("Aim") or r.get("Description") or "").strip()
            for r in csv.DictReader(f)
        }


def gh_url(repo: str) -> str:
    return f"https://github.com/{GITHUB_USER}/{repo}"

# ---------------------------------------------------------------------------
# Section builder
# ---------------------------------------------------------------------------

def build_section(hub: str, aims: dict[str, str]) -> str:
    absorbs = HUB_ABSORBS.get(hub, [])
    alts    = HUB_ALTERNATIVES.get(hub, {"oss": [], "commercial": []})

    lines = [
        SECTION_START,
        "",
        "## Integration Roadmap",
        "",
        "> **Aim:** Pull in functionality from the projects listed below, take inspiration",
        "> from open-source and commercial alternatives, analyse their features and integrate",
        "> the best ideas into this software.",
        ">",
        "> **Long-term goal:** 2-way sync compatibility with the open-source and commercial",
        "> alternatives listed here, so data and workflows move freely in both directions.",
        "",
        "### My projects to absorb",
        "",
        "| Project | What it contributes |",
        "|---------|---------------------|",
    ]

    for repo in absorbs:
        aim  = aims.get(repo, "").rstrip(".")
        link = f"[{repo}]({gh_url(repo)})"
        lines.append(f"| {link} | {aim or '—'} |")

    oss_str = " · ".join(alts["oss"])
    com_str = " · ".join(alts["commercial"])

    lines += [
        "",
        "### Open-source inspiration",
        "",
        oss_str or "_(to be defined)_",
        "",
        "### Commercial benchmarks",
        "",
        com_str or "_(to be defined)_",
        "",
        SECTION_END,
    ]

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# README updater
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(
    rf"{re.escape(SECTION_START)}.*?{re.escape(SECTION_END)}",
    re.DOTALL,
)


def update_readme(readme_path: Path, hub: str, aims: dict[str, str], dry_run: bool) -> str:
    section = build_section(hub, aims)

    if readme_path.exists():
        original = readme_path.read_text(encoding="utf-8")
        if SECTION_START in original:
            # Replace existing section
            updated = _SECTION_RE.sub(section, original)
            action  = "updated"
        else:
            # Insert after first heading (first line starting with #)
            lines   = original.splitlines(keepends=True)
            insert  = 0
            for i, line in enumerate(lines):
                if line.startswith("#"):
                    insert = i + 1
                    break
            lines.insert(insert, "\n" + section + "\n")
            updated = "".join(lines)
            action  = "inserted"
    else:
        updated = f"# {hub}\n\n{section}\n"
        action  = "created"

    if dry_run:
        print(f"\n{'-' * 60}")
        print(f"  [{hub}] README.md -- would be {action}")
        print(f"{'-' * 60}")
        print(updated[:1200] + ("..." if len(updated) > 1200 else ""))
    else:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"  [{action}] {readme_path}")

    return action

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root",    default=None, metavar="PATH",
                        help=f"Root directory containing hub repos (default: prompt)")
    parser.add_argument("--hub",     metavar="NAME",
                        help="Process a single hub only")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written; don't touch any files")
    args = parser.parse_args()

    if args.root:
        root = Path(args.root)
    else:
        answer = input(f"Where is your software suite? [{DEFAULT_ROOT}]: ").strip()
        root   = Path(answer) if answer else DEFAULT_ROOT

    if not root.exists():
        print(f"[!!] Directory not found: {root}")
        sys.exit(1)
    aims  = load_aims()
    hubs  = [args.hub] if args.hub else sorted(HUB_ABSORBS.keys())

    if args.dry_run:
        print("[DRY RUN] No files will be written.\n")

    found, skipped = 0, 0
    for hub in hubs:
        hub_dir    = root / hub
        readme_path = hub_dir / "README.md"

        if not hub_dir.exists():
            print(f"  [--] {hub}  (directory not found at {hub_dir})")
            skipped += 1
            continue

        update_readme(readme_path, hub, aims, args.dry_run)
        found += 1

    print(f"\nDone: {found} processed, {skipped} skipped (repo not cloned locally).")
    if skipped:
        print(f"  Clone missing repos to {root} and re-run.")


if __name__ == "__main__":
    main()
