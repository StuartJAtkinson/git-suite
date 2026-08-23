"""
wikidata.py — Step 7 (Wikidata-backed install DAG).

Fetches the transitive P279/P361 closure above a hub's Wikidata Q-id,
augmented with the Q-ids of the hub's absorbed repos. Hybrid by design:
SPARQL is the primary source; on failure the router falls back to the
local plan (caller decides — this module only raises WdError).

Wikidata is friendlier than GitHub: 3 retries on 5xx/timeout, no rate-limit
plumbing. The User-Agent header is mandatory — Wikimedia throttles
unidentified clients.

ponytail: SPARQL results are cached one layer up (wikidata_subgraph table).
This module is purely the network layer + the query loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import httpx

log = logging.getLogger(__name__)

WD_API = "https://query.wikidata.org/sparql"
WD_USER_AGENT = "git-suite/0.1 (https://github.com/smato/git-suite)"

# Curated stop set — Wikidata roots / meta-entities that would otherwise
# explode the DAG into a hairball. A real hub reaches a stop node in 2–3
# hops. Add more here if a test ever finds a real-world path that escapes
# the set at depth > 0.
STOP_QIDS: frozenset[str] = frozenset({
    "Q35120",   # entity (Wikidata's root)
    "Q4167410", # Wikimedia disambiguation page
    "Q24017414", # second-level class (meta)
    "Q386724",  # work
    "Q7725634", # literary work
    "Q47461344", # type of work
    "Q1260632", # second-level concept (Wikidata meta)
    "Q223557",  # physical object
})


class WdError(Exception):
    """Any upstream failure (network, 4xx, malformed response)."""


def _headers() -> dict:
    return {
        "Accept": "application/sparql-results+json",
        "User-Agent": WD_USER_AGENT,
    }


async def wd_get(client: httpx.AsyncClient, url: str,
                 params: dict | None = None) -> httpx.Response:
    """Single GET with 3 retries on 5xx / timeout. No rate-limit code:
    Wikidata's quota is generous and not the failure mode we hit in practice.
    Raises WdError on any persistent failure."""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.get(url, headers=_headers(),
                                    params=params, timeout=30)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            await asyncio.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            return resp
        if resp.status_code in (500, 502, 503, 504):
            last_exc = RuntimeError(f"HTTP {resp.status_code}")
            await asyncio.sleep(2 ** attempt)
            continue
        # 4xx — treat as a hard failure (likely a malformed Q-id).
        raise WdError(f"SPARQL {resp.status_code}: {resp.text[:200]}")
    raise WdError(f"SPARQL unreachable after 3 retries: {last_exc}")


def _build_query(frontier: Iterable[str]) -> str:
    """One-round SPARQL: for each Q-id in the frontier, follow P279/P361 one
    hop and return (child, parent, label). Filter out stop-set members so
    the result is fed back into the next iteration cleanly."""
    values = " ".join(f"wd:{q}" for q in frontier)
    stop_clause = " ".join(f"wd:{q}" for q in STOP_QIDS)
    return f"""
SELECT ?qid ?oQid ?oLabel WHERE {{
  VALUES ?qid {{ {values} }}
  ?qid wdt:P279|wdt:P361 ?oQid .
  OPTIONAL {{ ?oQid rdfs:label ?oLabel FILTER (lang(?oLabel) = "en") }}
  FILTER (?oQid NOT IN ({stop_clause}))
}}
"""


def _parse_results(payload: dict, frontier: set[str], depth: int
                   ) -> tuple[list[dict], list[dict]]:
    """Convert SPARQL JSON bindings into (nodes, edges). `nodes` are the
    new Q-ids discovered at this hop (with their depth)."""
    nodes: list[dict] = []
    edges: list[dict] = []
    new_qids: set[str] = set()
    for binding in payload.get("results", {}).get("bindings", []):
        child = binding["qid"]["value"].rsplit("/", 1)[-1]   # "http://.../Q12345" → "Q12345"
        parent = binding["oQid"]["value"].rsplit("/", 1)[-1]
        label = binding.get("oLabel", {}).get("value", parent)
        if parent in STOP_QIDS:
            continue
        edges.append({"from": child, "to": parent, "prop": "P279/P361"})
        if parent not in frontier and parent not in new_qids:
            new_qids.add(parent)
            nodes.append({"qid": parent, "label": label, "depth": depth})
    return nodes, edges


async def fetch_subgraph(client: httpx.AsyncClient, root_qid: str,
                         member_qids: Iterable[str],
                         *, max_depth: int = 4) -> dict:
    """Transitive closure of P279/P361 above the root, unioned with the
    member_qids as leaves. Returns {nodes, edges, root}. Raises WdError
    on any upstream failure — the caller decides to fall back to local.

    Ponytail ceiling: depth=4. Real hubs reach a stop node in ≤3 hops; raise
    this if a test ever finds a longer path.
    """
    if not root_qid or not root_qid.startswith("Q"):
        raise WdError(f"invalid root qid: {root_qid!r}")
    root_qid = root_qid.strip().upper()

    all_nodes: list[dict] = [{"qid": root_qid, "label": root_qid, "depth": 0}]
    all_edges: list[dict] = []
    frontier: set[str] = {root_qid}

    for depth in range(1, max_depth + 1):
        if not frontier:
            break
        # Build the query and POST it (SPARQL via GET works too, but POST
        # avoids URL-length issues with many VALUES).
        query = _build_query(frontier)
        resp = await wd_get(client, WD_API, params={"query": query})
        try:
            payload = resp.json()
        except Exception as exc:
            raise WdError(f"SPARQL response not JSON: {exc}") from exc
        new_nodes, new_edges = _parse_results(payload, frontier, depth)
        if not new_nodes:
            break
        all_nodes.extend(new_nodes)
        all_edges.extend(new_edges)
        frontier = {n["qid"] for n in new_nodes}

    # Members are leaves — always present, regardless of what SPARQL returned.
    seen = {n["qid"] for n in all_nodes}
    for m in member_qids:
        if m and m.startswith("Q") and m not in seen:
            all_nodes.append({"qid": m, "label": m, "depth": 0, "kind": "repo"})
            seen.add(m)

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "root": root_qid,
    }
