#!/usr/bin/env python3
"""
bootstrap_lists.py — one-shot driver that creates the 17 GitHub User Lists
matching the hub-leaders table in H:\\GitHub\\git-suite\\TAXONOMY.md
(lines 683-716, decided 2026-10-11, revised 2026-10-12).

Idempotent — existing Lists with the same name are reused, not duplicated.
Aspirational entries (Stuart's own not-yet-published roadmap) are silently
skipped via the ASPIRATIONAL set; other 404s are surfaced as a warning.

Credential flow (LLM never sees raw tokens):

  Recommended — Infisical CLI on Windows:
    infisical init   # interactive, pick the homelab project once
    infisical run --domain https://infisical.stuartjatkinson.co.uk \\
        --env=dev --path=/ -- python bootstrap_lists.py
    The CLI injects GITHUB_LISTS_TOKEN into the script's env.

  Fallback — direct env var:
    export GITHUB_LISTS_TOKEN=<classic PAT with `user` scope>

  Legacy — direct Infisical API call (kept for non-CLI workflows):
    export INFISICAL_TOKEN=<service token>
    INFISICAL_SECRET_NAME defaults to GITHUB_LISTS_TOKEN.

The script prints only the PAT length, never the value.

No new dependencies — stdlib only (`urllib.request`, `json`, `os`).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

# ponytail: GraphQL as plain strings — fragments are clearer than a builder for
# one-shot use; bump only if this becomes a long-lived service module.
GQL_CREATE_LIST = """
mutation CreateUserList($name: String!, $description: String!, $isPrivate: Boolean!) {
  createUserList(input: {name: $name, description: $description, isPrivate: $isPrivate}) {
    list { id name slug description isPrivate }
  }
}
""".strip()

# `viewer.lists(name:)` is NOT a valid filter (verified — schema rejects it).
# Idempotency instead pulls all viewer lists once at the start and matches
# client-side by `name`.
GQL_ALL_LISTS = """
query AllLists {
  viewer {
    lists(first: 100) {
      totalCount
      nodes { id name slug description isPrivate }
    }
  }
}
""".strip()

GQL_REPO_ID = """
query RepoId($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id
    nameWithOwner
  }
}
""".strip()

GQL_UPDATE_LISTS = """
mutation UpdateListsForItem($itemId: ID!, $listIds: [ID!]!) {
  updateUserListsForItem(input: {itemId: $itemId, listIds: $listIds}) {
    item {
      ... on Repository { id nameWithOwner }
    }
  }
}
""".strip()

USER_AGENT = "git-suite-bootstrap-lists/1.0"


def _post_json(url: str, headers: dict[str, str], body: bytes, timeout: int) -> bytes:
    """POST JSON; raise on non-2xx with body in the message."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        # Body may include the token in error responses — strip it before raising.
        msg = exc.read().decode(errors="replace")
        for needle in ("Bearer ", "bearer ", "token="):
            if needle in msg.lower():
                msg = "[redacted — token-bearing error]"
                break
        raise RuntimeError(f"POST {url} → HTTP {exc.code}: {msg}")


def fetch_github_token_from_infisical() -> str:
    """Resolve the GitHub PAT from env / Infisical. Returns the token; never logs it.

    Resolution order:
        1. GITHUB_LISTS_TOKEN env var (preferred — `infisical run` injects it).
        2. INFISICAL_TOKEN env var → fetch INFISICAL_SECRET_NAME (default
           GITHUB_LISTS_TOKEN) from the Infisical raw-secrets endpoint.
        3. Hard error with install instructions.
    """
    # Preferred path — CLI injected.
    direct = os.environ.get("GITHUB_LISTS_TOKEN")
    if direct:
        return direct

    # Fallback path — direct Infisical HTTP call.
    infisical_token = os.environ.get("INFISICAL_TOKEN")
    if not infisical_token:
        sys.exit(
            "No GITHUB_LISTS_TOKEN or INFISICAL_TOKEN env var.\n\n"
            "  Recommended — Infisical CLI:\n"
            "    infisical init --domain https://infisical.stuartjatkinson.co.uk\n"
            "    infisical run --env=dev --path=/ -- python bootstrap_lists.py\n\n"
            "  Or directly:\n"
            "    export GITHUB_LISTS_TOKEN=<classic GitHub PAT with `user` scope>\n"
        )

    host = os.environ.get("INFISICAL_HOST", "https://infisical.stuartjatkinson.co.uk").rstrip("/")
    secret_name = os.environ.get("INFISICAL_SECRET_NAME", "GITHUB_LISTS_TOKEN")
    api_version = os.environ.get("INFISICAL_API_VERSION", "v3")

    url = f"{host}/api/{api_version}/secrets/raw/{secret_name}"
    raw_bytes = _post_json(
        url,
        {
            "Authorization": f"Bearer {infisical_token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        b"{}",
        timeout=30,
    )
    data = json.loads(raw_bytes)
    # Infisical v3 wraps the secret under `secret.secretValue`; older shapes put
    # it at top level. Accept either.
    secret_value = (
        data.get("secret", {}).get("secretValue")
        if isinstance(data.get("secret"), dict)
        else None
    ) or data.get("secretValue")
    if not secret_value:
        sys.exit(f"Infisical response missing secretValue for {secret_name}: keys={list(data)}")
    return secret_value


def github_gql(query: str, variables: dict[str, Any], token: str) -> dict[str, Any]:
    """Call api.github.com/graphql with the given PAT as bearer. Returns `data`."""
    payload = json.dumps({"query": query, "variables": variables}).encode()
    raw = _post_json(
        "https://api.github.com/graphql",
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        payload,
        timeout=60,
    )
    data = json.loads(raw)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


def fetch_existing_lists(token: str) -> dict[str, dict[str, Any]]:
    """Fetch all viewer lists once; return {name: list} for name-based lookup."""
    data = github_gql(GQL_ALL_LISTS, {}, token)
    return {n["name"]: n for n in data["viewer"]["lists"]["nodes"]}


def create_list(name: str, description: str, token: str) -> dict[str, Any]:
    """Create a new viewer list; return the list object."""
    data = github_gql(
        GQL_CREATE_LIST,
        {"name": name, "description": description, "isPrivate": False},
        token,
    )
    return data["createUserList"]["list"]


def repo_node_id(slug: str, token: str) -> tuple[str, str] | None:
    """Resolve 'owner/name' → (global node id, nameWithOwner), or None on 404.

    Bare names fall back to the viewer as owner — owned repos live there.
    """
    if "/" not in slug:
        owner, name = "StuartJAtkinson", slug
    else:
        owner, name = slug.split("/", 1)
    try:
        data = github_gql(GQL_REPO_ID, {"owner": owner, "name": name}, token)
    except RuntimeError as exc:
        # 404 from GraphQL arrives as `errors` with type NOT_FOUND — already raised.
        msg = str(exc)
        if "NOT_FOUND" in msg or "Could not resolve" in msg:
            return None
        raise
    repo = data.get("repository")
    if repo is None:
        return None
    return repo["id"], repo["nameWithOwner"]


def add_repo_to_list(item_id: str, list_id: str, token: str) -> None:
    """Set the lists for a repository node (one-call add to multiple lists)."""
    github_gql(GQL_UPDATE_LISTS, {"itemId": item_id, "listIds": [list_id]}, token)


# Aspirational roadmap entries — not on GitHub yet, will retry on every run
# until they exist. Drop a name once it has been published.
ASPIRATIONAL: set[str] = {
    "StuartJAtkinson/sql_schema_visualizer",
    "StuartJAtkinson/homelab-mcp",
    "StuartJAtkinson/belzona-tickets",
    "StuartJAtkinson/ask-ai",
    "StuartJAtkinson/marvel-ontology",
    "StuartJAtkinson/stardog",
    "StuartJAtkinson/sparql.anything",
    "StuartJAtkinson/chemeter-data",
    "StuartJAtkinson/democracy-watcher",
    "StuartJAtkinson/aw-watcher-netstatus",
    "StuartJAtkinson/aw-watcher-media-player",
    "StuartJAtkinson/timeliner",
    "StuartJAtkinson/ddb-bridge",
    "StuartJAtkinson/d4lf",
    "StuartJAtkinson/WoWAnalyzer",
    "StuartJAtkinson/xiv-resources",
    "StuartJAtkinson/Memoria",
}


# 17 Lists. Membership matches TAXONOMY.md:683-702 + satellites column.
# Order is the order in the table; this is the user-facing order on the page.
LISTS: list[dict[str, Any]] = [
    {
        "name": "Database",
        "description": (
            "Rung 1 / Single Computer: storage engines and generic DB "
            "tooling. Ordered within: relational → multi-model → graph. "
            "Discriminator 4 (engine vs dataset) — software that knows what "
            "its data means lives here, not Storage."
        ),
        "members": [
            "StuartJAtkinson/sql-schema-miner",
            "SchemaCrawler/SchemaCrawler",
            "dbeaver/cloudbeaver",
            "bytebase/bytebase",
            "StuartJAtkinson/sql_schema_visualizer",
        ],
    },
    {
        "name": "Homelab",
        "description": (
            "Substrate of the homelab — hypervisors, orchestration, IaC, "
            "self-hosted dashboards. The leaf that turns one box into many. "
            "Q-anchor: server / Q58326 (Wikidata)."
        ),
        "members": [
            "StuartJAtkinson/homelab-designer",
            "awesome-selfhosted/awesome-selfhosted",
            "StuartJAtkinson/homelab-discovery",
            "StuartJAtkinson/homelab-mcp",
            "community-scripts/ProxmoxVE",
            "SimpleHomelab/Deployrr",
        ],
    },
    {
        "name": "IT Support & Device Mgmt",
        "description": (
            "End-user IT and per-device tooling — help-desk, install, "
            "configure, repair, find. The rung-3 leaf that keeps hands on "
            "the box."
        ),
        "members": [
            "StuartJAtkinson/belzona-tickets",
            "atlassian-api/atlassian-python-api",
            "StuartJAtkinson/Jira-Lens",
            "StuartJAtkinson/EMailParseAI",
        ],
    },
    {
        "name": "Ingestion",
        "description": (
            "Rung 5 / Data Input: pull external streams (social, calendar, "
            "audio, web) into local repositories for downstream presentation "
            "or analysis."
        ),
        "members": [
            "StuartJAtkinson/socialMediaArchiver",
            "StuartJAtkinson/multitudes",
            "StuartJAtkinson/dnd-session-recorder",
            "ActivityWatch/aw-import-ical",
            "StuartJAtkinson/YouTubeCommunityPosts",
            "StuartJAtkinson/tweetext",
            "StuartJAtkinson/twitterscraper",
        ],
    },
    {
        "name": "Code & Build Tooling",
        "description": (
            "Developer productivity, code navigation, repo-level comms, "
            "build/dep tooling. Function is dev-experience, not infra."
        ),
        "members": [
            "StuartJAtkinson/git-suite",
            "StuartJAtkinson/astral",
            "StuartJAtkinson/all-repos",
        ],
    },
    {
        "name": "Ai — Agent Tooling",
        "description": (
            "AI agents that act on the codebase (planning, code-edit, "
            "orchestration). Distinct from model-serving infra."
        ),
        "members": [
            "StuartJAtkinson/Atelier-Harness",
            "StuartJAtkinson/ask-ai",
            "Aider-AI/aider",
            "OpenDevin/OpenDevin",
            "coleam00/Archon",
            "crewAIInc/crewAI-examples",
        ],
    },
    {
        "name": "Ontology",
        "description": (
            "RDF, OWL, SKOS, knowledge graphs — semantic content. Q-anchor: "
            "knowledge graph / Q3249551 (Wikidata)."
        ),
        "members": [
            "StuartJAtkinson/marvel-ontology",
            "StuartJAtkinson/CommonCoreOntologies",
            "StuartJAtkinson/ontologiesUK",
            "StuartJAtkinson/stardog",
            "StuartJAtkinson/sparql.anything",
        ],
    },
    {
        "name": "Geospatial & Mapping",
        "description": (
            "Maps, routing, location data, geospatial visualisation."
        ),
        "members": [
            "StuartJAtkinson/map-merch",
            "StuartJAtkinson/streets-gl",
            "gboeing/osmnx",
            "keplergl/kepler.gl",
        ],
    },
    {
        "name": "Business",
        "description": (
            "CRM, data sync, business-object extraction from structured "
            "sources."
        ),
        "members": [
            "StuartJAtkinson/chemeter-data",
            "StuartJAtkinson/ZohoAPI",
            "twentyhq/twenty",
        ],
    },
    {
        "name": "Civic & Public Affairs",
        "description": (
            "Public sector, gov data, civic tech — domain-specific tooling "
            "for civic workflows."
        ),
        "members": [
            "StuartJAtkinson/organised-commons",
            "StuartJAtkinson/canvassing-planner",
            "StuartJAtkinson/democracy-watcher",
            "StuartJAtkinson/federated-api-model",
        ],
    },
    {
        "name": "Lifelogging",
        "description": (
            "Quantified-self, activity watching, timeline aggregation. "
            "Presentation layer fed by the Ingestion hub. "
            "Q-anchor: quantified self / Q5805249."
        ),
        "members": [
            "StuartJAtkinson/timelinize",
            "StuartJAtkinson/Genealogy",
            "ActivityWatch/activitywatch",
            "StuartJAtkinson/aw-watcher-netstatus",
            "StuartJAtkinson/aw-watcher-media-player",
            "StuartJAtkinson/simklExporter",
            "StuartJAtkinson/timeliner",
        ],
    },
    {
        "name": "Health",
        "description": "Exercise, diet, training tracking.",
        "members": ["StuartJAtkinson/traintenance"],
    },
    {
        "name": "Travel",
        "description": "Trip planning, itineraries, location intelligence.",
        "members": ["StuartJAtkinson/travel-planner"],
    },
    {
        "name": "Video",
        "description": "Media output for the production workflow.",
        "members": ["StuartJAtkinson/video-autoeditor"],
    },
    {
        "name": "Games — TTRPG",
        "description": "Tabletop role-playing — campaign builders, char sheets, VTT bridging.",
        "members": [
            "StuartJAtkinson/ddb-bridge",
            "StuartJAtkinson/swipe-vtt",
            "StuartJAtkinson/dnd-aFirstStep",
        ],
    },
    {
        "name": "Games — In-game Data",
        "description": (
            "Game-specific data tools — loot, builds, routes, parses. Domain "
            "knowledge beats engine test (discriminator 4)."
        ),
        "members": [
            "StuartJAtkinson/game-across-the-obelisk",
            "StuartJAtkinson/d4lf",
            "StuartJAtkinson/free-map-genie",
            "StuartJAtkinson/AllaganTools",
            "StuartJAtkinson/WoWAnalyzer",
            "StuartJAtkinson/FFXIVPlugin",
            "StuartJAtkinson/xiv-resources",
            "StuartJAtkinson/Memoria",
        ],
    },
    {
        "name": "Games — Collectibles",
        "description": "Physical card/figure collection tracking.",
        "members": [
            "StuartJAtkinson/card-collector",
        ],
    },
]


def main() -> int:
    # Resolve the GitHub PAT — order: GITHUB_LISTS_TOKEN env var (CLI-injected)
    # → INFISICAL_TOKEN + raw-secrets call (legacy direct) → fail with help.
    # The PAT itself never appears in this session's prompts/logger.
    source = "GITHUB_LISTS_TOKEN env var" if os.environ.get("GITHUB_LISTS_TOKEN") else "Infisical API"
    github_token = fetch_github_token_from_infisical()
    print(f"PAT resolved via {source} (length {len(github_token)} chars)")

    existing_lists = fetch_existing_lists(github_token)
    print(f"Pre-existing viewer lists: {len(existing_lists)}")

    created, reused, members_added, members_skipped, members_aspirational = 0, 0, 0, 0, 0
    skipped_details: list[str] = []

    for spec in LISTS:
        existing = existing_lists.get(spec["name"])
        if existing:
            lst = existing
            reused += 1
            print(f"= {spec['name']:30s} reused ({lst['slug']})")
        else:
            lst = create_list(spec["name"], spec["description"], github_token)
            created += 1
            print(f"+ {spec['name']:30s} created ({lst['slug']})")

        for slug in spec["members"]:
            if slug in ASPIRATIONAL:
                # Roadmap entry — not yet published on GitHub; retry on next run.
                members_aspirational += 1
                continue
            rid = repo_node_id(slug, github_token)
            if rid is None:
                members_skipped += 1
                skipped_details.append(f"  - {spec['name']}: {slug} (404)")
                continue
            node_id, _ = rid
            add_repo_to_list(node_id, lst["id"], github_token)
            members_added += 1

    print()
    print(f"Lists:   {created} created, {reused} reused")
    print(f"Members: {members_added} added, {members_skipped} skipped, {members_aspirational} aspirational (will retry next run)")
    if skipped_details:
        print("\nSkipped (likely 404 — verify canonical owner/name):")
        for line in skipped_details:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())