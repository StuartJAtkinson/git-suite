"""
topic_llm.py — single-shot LLM topic discovery across the whole portfolio.

Replaces k-means + suggest_theme() with one big prompt that hands the LLM
every distilled record (purpose + entities + domain) at once. Returns a
JSON object of {themes: [{name, slug, repo_names: [...]}]} with UNIQUE
slugs and EXPLICIT overlap (a repo can appear in multiple themes).

Why this beats k-means + suggest_theme():
- suggest_theme is a token-Counter that picks the most common entity
  across members. When members share generic entities ("data", "server",
  "computer") two clusters end up named identically ("data-hub" twice,
  "server-hub" twice) and the user sees collisions.
- The LLM sees ALL distilled text at once, can compare clusters side by
  side, and produces UNIQUE theme names with deliberate scoping (e.g.
  "tabletop role-playing" not "games" because it has tabletop-specific
  signals across many repos).

Cost: one LLM call. ~700 distilled records × ~150 tokens = ~105k input
tokens. Fits in any 128k+ context model.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter

from services import distill, llm

log = logging.getLogger(__name__)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    s = _SLUG_RE.sub("-", (name or "").lower()).strip("-")
    return s or "theme"


_SYS = (
    "You organise a software portfolio into THEMES — the real-world "
    "activities, hobbies, or lines of work the repos serve. "
    "Output STRICT JSON. Schema:\n"
    '{"themes": [\n'
    '  {"name": "<2-4 word theme label, lowercase where natural, e.g. '
    '"tabletop role-playing", "homeserver administration", "LLM tooling">", '
    '   "slug": "<kebab-case unique id derived from name>", '
    '   "repo_names": ["<repo name exactly as given>", ...]}\n'
    ']}\n'
    "Rules — in priority order:\n"
    "1. NEVER group by software type or tech stack. Forbidden theme names "
    "include (but are not limited to): 'software', 'tools', 'tooling', 'data', "
    "'data processing', 'data analysis', 'programming', 'programming language', "
    "'python', 'javascript', 'typescript', 'rust', 'go', 'web app', 'cli', "
    "'library', 'framework', 'api', 'automation', 'machine learning', 'web "
    "development', 'devops'. These are not themes — they're categories of "
    "computing.\n"
    "2. Name the HUMAN ACTIVITY the repos serve: tabletop role-playing, "
    "homelab administration, music production, gardening, IT support, fantasy "
    "writing, cooking, photography. If you can't name an activity, the theme "
    "is wrong.\n"
    "3. SLUGS must be unique kebab-case derived from the name.\n"
    "4. A repo may appear in MULTIPLE themes.\n"
    "5. Aim for 15-30 themes. Small related clusters can be one theme.\n"
    "6. Every repo in the input must appear in at least one theme "
    "(use 'misc-unsorted' for anything unclassifiable).\n"
    "7. No descriptions, no prose — JSON only, nothing after the closing ']'."
)


def _build_prompt(records: list[dict]) -> str:
    """Compact per-repo table: name | purpose | entities | domain.
    Trimmed aggressively so the full ~700-row table fits the prompt budget
    with room for the JSON response."""
    lines = [
        f"Portfolio ({len(records)} repos). Produce the themes JSON.",
        "",
        "NAME | PURPOSE | ENTITIES | DOMAIN",
    ]
    for r in records:
        name = r.get("name", "")
        purpose = (r.get("purpose") or "").replace("\n", " ").strip()[:120]
        entities = ", ".join(r.get("entities") or [])[:80]
        domain = (r.get("domain") or "").strip()[:40]
        lines.append(f"{name} | {purpose} | {entities} | {domain}")
    return "\n".join(lines)


def _extract_json(raw: str) -> str:
    """The LLM sometimes wraps the JSON in ```json fences, prefixes it with
    'Sure, here is the JSON:' prose, or trails it with a second object. Find
    the FIRST balanced {...} and return it — json.loads that."""
    raw = (raw or "").strip()
    # Strip a leading ```json fence (and matching trailing ```).
    if raw.startswith("```"):
        first_nl = raw.find("\n")
        if first_nl > 0:
            raw = raw[first_nl + 1:]
        if raw.endswith("```"):
            raw = raw[:-3].rstrip()
    # Walk forward to the first '{' and find the matching '}'.
    start = raw.find("{")
    if start < 0:
        return raw          # let json.loads raise
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(raw[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    return raw[start:]      # unbalanced — let json.loads raise


def _validate(themes: list[dict], known_names: set[str]) -> list[dict]:
    """Drop themes whose slug collides; coerce missing fields; dedupe
    member names; remove repo_names that aren't in the input."""
    seen_slugs: set[str] = set()
    out: list[dict] = []
    for t in themes:
        name = (t.get("name") or "").strip()
        slug = _slug(t.get("slug") or name)
        # Slug-uniqueness: append -2, -3 ... if collision.
        base = slug
        n = 2
        while slug in seen_slugs:
            slug = f"{base}-{n}"
            n += 1
        seen_slugs.add(slug)
        members = [m.strip() for m in (t.get("repo_names") or [])
                   if isinstance(m, str) and m.strip() in known_names]
        if not members:
            continue
        out.append({
            "name": name,
            "slug": slug,
            "description": (t.get("description") or "").strip()[:240],
            "repo_names": sorted(set(members)),
        })
    return out


async def discover_themes(repos: list[dict]) -> list[dict]:
    """Take a list of {name, purpose, entities, domain} dicts (already
    distilled) and return a list of validated themes with unique slugs.
    Falls back to [] if no LLM is configured or every provider fails.

    Each repo is expected to have at minimum `name`. Other fields may be
    empty strings. Caller should have already filtered to orphans.
    """
    if not repos:
        return []
    known = {r.get("name", "") for r in repos}
    known.discard("")
    prompt = _build_prompt(repos)
    last_err = ""
    for attempt in range(2):                                # one retry on bad JSON
        try:
            raw = await llm.complete(prompt, system=_SYS, max_tokens=16000)
        except llm.AllProvidersFailed as exc:
            log.warning("topic_llm: all providers failed: %s", exc)
            return []
        try:
            parsed = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            last_err = str(exc)
            log.warning("topic_llm: JSON parse failed (attempt %d, len %d): %s",
                        attempt + 1, len(raw), exc)
            continue
        themes = parsed.get("themes") if isinstance(parsed, dict) else parsed
        if not isinstance(themes, list):
            last_err = "themes is not a list"
            continue
        validated = _validate(themes, known)
        if validated:
            return validated
        last_err = "no themes after validation"
    log.warning("topic_llm: giving up — %s", last_err)
    return []


def parse_external_response(raw: str, known_names: set[str]) -> list[dict]:
    """Parse + validate a themes JSON blob pasted back from an external LLM
    (the response to render_external_prompt's EXPECTED RESPONSE contract).
    Same extraction/validation as the internal one-shot call, just without
    the retry loop — a human is in the loop here, not a retry budget."""
    parsed = json.loads(_extract_json(raw))
    themes = parsed.get("themes") if isinstance(parsed, dict) else parsed
    if not isinstance(themes, list):
        raise ValueError("expected {\"themes\": [...]} or a bare [...] list")
    return _validate(themes, known_names)


def themes_to_clusters(themes: list[dict], pool_by_name: dict[str, dict]
                       ) -> tuple[list[dict], list[dict]]:
    """Convert validated themes into the (clusters, orphans) tuple the rest
    of the pipeline already understands.

    Each theme becomes a cluster; its members are looked up in `pool_by_name`
    to retrieve the rich dict (with source / stars / full_name). Repos in the
    pool that don't appear in any theme's repo_names land in `orphans_returned`.
    """
    assigned: set[str] = set()
    clusters: list[dict] = []
    for t in themes:
        members: list[dict] = []
        for nm in t["repo_names"]:
            p = pool_by_name.get(nm)
            if not p:
                continue
            members.append({
                "repo": p.get("repo") or p.get("name") or nm,
                "full_name": p.get("full_name"),
                "source": p.get("source", "owned"),
                "stars": p.get("stars", 0),
                "domain": p.get("domain", ""),
                "entities": p.get("entities", []),
                "purpose": p.get("purpose", ""),
                "aim": p.get("aim") or p.get("description") or "",
            })
            assigned.add(p.get("full_name") or nm)
        if not members:
            continue
        clusters.append({
            "members": members,
            "suggested_name": t["name"],
            "suggested_description": t.get("description", ""),
            "slug": t["slug"],
            "size": len(members),
        })
    orphans = [p for k, p in pool_by_name.items()
               if (p.get("full_name") or p.get("name") or k) not in assigned]
    return clusters, orphans