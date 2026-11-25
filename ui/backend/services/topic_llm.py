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
    '{\n'
    '  "themes": [\n'
    '    {"name": "<2-4 word theme label, lowercase where natural, e.g. '
    '"tabletop role-playing", "homeserver administration", "LLM tooling">", '
    '     "slug": "<kebab-case unique id derived from name>", '
    '     "repo_names": ["<repo name exactly as given>", ...], '
    '     "confidence": <0.0 to 1.0>}\n'
    '  ],\n'
    '  "questions": [\n'
    '    {"question": "<one sentence of what is genuinely ambiguous>", '
    '     "repos": ["<repo name exactly as given>", ...], '
    '     "options": ["<answer option A>", "<B>", ...]}\n'
    '  ]\n'
    '}\n'
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
    "7. `confidence` is your certainty (0.0-1.0) that this theme's membership "
    "is correct. 1.0 = certain. Use a value below 0.6 when the theme is fuzzy "
    "or its members seem heterogeneous.\n"
    "8. `questions` surface ONLY genuine semantic ambiguity — a repo or small "
    "group that could honestly belong to two different activities, or a clump "
    "whose boundary is unclear. Each names the repos in question and 2-4 "
    "concrete options a human can click to resolve it. At most 5 questions. "
    "Do not ask about themes you rated 0.9 or higher. If nothing is ambiguous "
    "give an empty list.\n"
    "9. No descriptions, no prose — JSON only, nothing after the closing '}'."
)


def _build_prompt(records: list[dict], answers: list[dict] | None = None) -> str:
    """Compact per-repo table: name | purpose | entities | domain.
    Trimmed aggressively so the full ~700-row table fits the prompt budget
    with room for the JSON response. `answers` are prior (question, answer)
    pairs from earlier refinement rounds, folded in as steering context."""
    head = []
    if answers:
        head.append("Apply these earlier answers from the user (they resolve "
                     "earlier ambiguity — do not re-ask them):")
        for a in answers:
            head.append(f"- Q: {a.get('question', '')}")
            head.append(f"  A: {a.get('answer', '')}")
        head.append("")

    head.append(f"Portfolio ({len(records)} repos). Produce the themes JSON.")
    head.append("")
    head.append("NAME | PURPOSE | ENTITIES | DOMAIN")
    for r in records:
        name = r.get("name", "")
        purpose = (r.get("purpose") or "").replace("\n", " ").strip()[:120]
        entities = ", ".join(r.get("entities") or [])[:80]
        domain = (r.get("domain") or "").strip()[:40]
        head.append(f"{name} | {purpose} | {entities} | {domain}")
    return "\n".join(head)


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


def _coerce_confidence(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, f))


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
            "confidence": _coerce_confidence(t.get("confidence")),
        })
    return out


def _validate_questions(items, known_names: set[str]) -> list[dict]:
    """Coerce the LLM's clarifying questions into a stable card shape. Each
    survives only if it has question text, >=1 known repo, and 2+ options."""
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for i, q in enumerate(items):
        if not isinstance(q, dict):
            continue
        question = (q.get("question") or "").strip()
        if not question:
            continue
        repos = [r.strip() for r in (q.get("repos") or [])
                 if isinstance(r, str) and r.strip() in known_names]
        options = [o.strip() for o in (q.get("options") or [])
                   if isinstance(o, str) and o.strip()][:6]
        if not options:
            continue
        out.append({
            "id": f"q{i}",
            "question": question,
            "repos": repos,
            "options": options,
        })
    return out[:5]


async def discover_themes(repos: list[dict],
                          answers: list[dict] | None = None
                          ) -> tuple[list[dict], list[dict]]:
    """Take a list of {name, purpose, entities, domain} dicts (already
    distilled) and return (themes, questions) — validated themes with unique
    slugs and any clarifying questions the LLM raised. `answers` are prior
    (question, answer) pairs folded back in for iterative refinement. Falls
    back to ([], []) if no LLM is configured or every provider fails.

    Each repo is expected to have at minimum `name`. Other fields may be
    empty strings. Caller should have already filtered to orphans.
    """
    if not repos:
        return [], []
    known = {r.get("name", "") for r in repos}
    known.discard("")
    prompt = _build_prompt(repos, answers=answers)
    last_err = ""
    for attempt in range(2):                                # one retry on bad JSON
        try:
            raw = await llm.complete(prompt, system=_SYS, max_tokens=16000)
        except llm.AllProvidersFailed as exc:
            log.warning("topic_llm: all providers failed: %s", exc)
            return [], []
        try:
            parsed = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            last_err = str(exc)
            log.warning("topic_llm: JSON parse failed (attempt %d, len %d): %s",
                        attempt + 1, len(raw), exc)
            continue
        themes_raw = parsed.get("themes") if isinstance(parsed, dict) else parsed
        questions_raw = parsed.get("questions") if isinstance(parsed, dict) else []
        if not isinstance(themes_raw, list):
            last_err = "themes is not a list"
            continue
        validated = _validate(themes_raw, known)
        if validated:
            return validated, _validate_questions(questions_raw, known)
        last_err = "no themes after validation"
    log.warning("topic_llm: giving up — %s", last_err)
    return [], []


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
            "confidence": t.get("confidence"),
        })
    orphans = [p for k, p in pool_by_name.items()
               if (p.get("full_name") or p.get("name") or k) not in assigned]
    return clusters, orphans


# ── iterative deltas over the grouping ledger (step 2) ──────────────────────
# After round 0 populates the ledger, refinement is NOT a full re-cluster: the
# LLM proposes small, targeted changes (merge / split / move / rename) with a
# rationale + confidence, or a clarifying question when it can't decide. The
# human approves; approving commits to the ledger and settles the touched repos.


# One delta round runs in chunks of clumps — see propose_deltas. Eight clumps
# is a prompt a local model can hold; the whole ledger at once is ~24K tokens.
DELTA_CHUNK_CLUMPS = 8
# The schema says "at most 10 deltas" per call, and a delta is ~90 tokens, so
# ~1500 is enough for a full response. A local model generating at a few
# tokens a second needs the ceiling to be near what it actually uses — a
# 4000-token budget just lets it ramble for another half hour.
DELTA_CHUNK_MAX_TOKENS = 1500

_DELTA_SYS = (
    "You refine an existing grouping of a software portfolio. The grouping is a "
    "set of CLUMPS (themes = human activities) with repos assigned to them. You "
    "do NOT re-cluster from scratch — you propose small, targeted changes "
    "(deltas) to fix specific problems. Output STRICT JSON. Schema:\n"
    '{\n'
    '  "deltas": [\n'
    '    {"type": "merge", "a": "<clump slug>", "b": "<clump slug>", '
    '"new_name": "<merged name>", "rationale": "<one sentence>", '
    '"confidence": <0.0-1.0>},\n'
    '    {"type": "split", "cluster": "<clump slug>", '
    '"members": ["<repo exact>", ...], "new_name": "<new clump name>", '
    '"rationale": "...", "confidence": <0.0-1.0>},\n'
    '    {"type": "move", "repo": "<repo exact>", "from": "<clump slug>", '
    '"to": "<clump slug | unplaced>", "rationale": "...", '
    '"confidence": <0.0-1.0>},\n'
    '    {"type": "rename", "cluster": "<clump slug>", "new_name": "<new name>", '
    '"rationale": "...", "confidence": <0.0-1.0>}\n'
    '  ],\n'
    '  "questions": [\n'
    '    {"question": "<one sentence>", "repos": ["<repo exact>", ...], '
    '"options": ["<A>", "<B>", ...]}\n'
    '  ]\n'
    '}\n'
    "Rules — in priority order:\n"
    "1. Only propose changes to repos/clumps that are NOT marked settled. "
    "Settled repos are frozen — cite them as context, never move/split/rename "
    "them away.\n"
    "2. Propose at most 10 deltas, most impactful first. Prefer few confident "
    "deltas over many speculative ones.\n"
    "3. `confidence` is your certainty the change is correct. Use below 0.6 "
    "only when guessing.\n"
    "4. merge two clumps that are really the same activity; name the result "
    "after the ACTIVITY, never a tech-stack word.\n"
    "5. split a clump only when its members clearly fall into two different "
    "activities; name the new clump.\n"
    "6. move a single repo to a more fitting clump, or to \"unplaced\" if it "
    "belongs nowhere yet.\n"
    "7. rename a clump whose name does not describe the activity.\n"
    "8. questions: ONLY for genuine ambiguity that blocks a confident delta. "
    "At most 5. Options are concrete answers a human can click.\n"
    "9. No prose — JSON only."
)


def _build_delta_prompt(records: list[dict], ledger: dict,
                        answers: list[dict] | None = None,
                        focus_clumps: list[str] | None = None) -> str:
    """Current clumps + which repos are frozen vs actionable, so the LLM only
    proposes deltas over the unsettled/proposed/ambiguous set.

    `focus_clumps` narrows the round to a slice of the ledger: the clumps in
    focus list their members, the rest are listed by name and size only, and
    the actionable table carries just the focused repos. That is what keeps a
    call inside a local model's context window — one whole-ledger prompt over
    887 repos is ~24K tokens and no 8B model answers it.
    """
    statuses = ledger.get("statuses", {})
    clumps = ledger.get("clumps", {})
    by_clump: dict = {}
    for key, s in statuses.items():
        by_clump.setdefault(s.get("clump"), []).append(key)
    focus = set(focus_clumps) if focus_clumps is not None else None

    lines: list[str] = []
    if answers:
        lines.append("Apply these earlier answers (do not re-ask):")
        for a in answers:
            lines.append(f"- Q: {a.get('question', '')}")
            lines.append(f"  A: {a.get('answer', '')}")
        lines.append("")

    lines.append("CURRENT CLUMPS:")
    for slug, meta in clumps.items():
        conf = meta.get("confidence")
        conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "?"
        members = by_clump.get(slug, [])
        if focus is None or slug in focus:
            lines.append(f"- {slug} \"{meta.get('name', slug)}\" (conf {conf_s}): "
                         f"{', '.join(members) or '(empty)'}")
        else:
            lines.append(f"- {slug} \"{meta.get('name', slug)}\" (conf {conf_s}): "
                         f"{len(members)} members")

    settled = [k for k, s in statuses.items() if s.get("status") == "settled"]
    if settled:
        lines.append("")
        lines.append("FROZEN (settled — do NOT move, split, or rename away):")
        for k in settled:
            lines.append(f"- {k} -> {statuses[k].get('clump') or 'unplaced'}")

    lines.append("")
    lines.append("ACTIONABLE — propose deltas for these:")
    lines.append("NAME | PURPOSE | ENTITIES | DOMAIN | current clump")
    for r in records:
        name = r.get("name", "")
        s = statuses.get(name)
        if not s or s.get("status") == "settled":
            continue
        clump = s.get("clump")
        if focus is not None and clump is not None and clump not in focus:
            continue
        purpose = (r.get("purpose") or "").replace("\n", " ").strip()[:120]
        entities = ", ".join(r.get("entities") or [])[:80]
        domain = (r.get("domain") or "").strip()[:40]
        lines.append(f"{name} | {purpose} | {entities} | {domain} | "
                     f"{clump or 'unplaced'}")

    lines.append("")
    lines.append("Produce the deltas JSON.")
    return "\n".join(lines)


def _validate_deltas(items, clumps: set[str], repos: set[str]) -> list[dict]:
    """Keep only structurally-sound deltas whose slugs/repos are known. Order
    preserved; capped at 10. Confidence coerced to [0,1] or None."""
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for d in items:
        if not isinstance(d, dict):
            continue
        dtype = d.get("type")
        base = {
            "confidence": _coerce_confidence(d.get("confidence")),
            "rationale": (d.get("rationale") or "").strip()[:240],
        }
        if dtype == "merge":
            a, b = d.get("a"), d.get("b")
            if a in clumps and b in clumps and a != b:
                out.append({**base, "type": "merge", "a": a, "b": b,
                            "new_name": (d.get("new_name") or "").strip()})
        elif dtype == "split":
            c = d.get("cluster")
            members = [m.strip() for m in (d.get("members") or [])
                       if isinstance(m, str) and m.strip() in repos]
            if c in clumps and members:
                out.append({**base, "type": "split", "cluster": c,
                            "members": members,
                            "new_name": (d.get("new_name") or "").strip()})
        elif dtype == "move":
            repo = (d.get("repo") or "").strip()
            to = d.get("to")
            if repo in repos and (to == "unplaced" or to in clumps):
                out.append({**base, "type": "move", "repo": repo,
                            "from": d.get("from"), "to": to})
        elif dtype == "rename":
            c = d.get("cluster")
            new_name = (d.get("new_name") or "").strip()
            if c in clumps and new_name:
                out.append({**base, "type": "rename", "cluster": c,
                            "new_name": new_name})
    return out[:10]


async def propose_deltas(records: list[dict], ledger: dict,
                         answers: list[dict] | None = None
                         ) -> tuple[list[dict], list[dict]]:
    """Read the ledger and ask the LLM for targeted refinement deltas +
    clarifying questions. Returns ([], []) when nothing to refine or no LLM.

    The round runs in chunks of clumps, one LLM call each: a whole-ledger
    prompt over 887 repos is ~24K tokens, which no local model answers inside
    a sane timeout, and a provider that is down would otherwise be waited on
    once per chunk. Deltas from every chunk are merged, de-duplicated and
    capped at 10 (the schema's own limit); questions at 5.
    """
    clumps = set(ledger.get("clumps", {}).keys())
    repos = {r.get("name", "") for r in records}
    repos.discard("")
    if not clumps or not repos:
        return [], []
    statuses = ledger.get("statuses", {})
    # Only clumps that still hold unsettled members are worth a look.
    active = [slug for slug in clumps
              if any(s.get("clump") == slug and s.get("status") != "settled"
                     for s in statuses.values())]
    if not active:
        return [], []

    chunks = [active[i:i + DELTA_CHUNK_CLUMPS]
              for i in range(0, len(active), DELTA_CHUNK_CLUMPS)]
    deltas: list[dict] = []
    questions: list[dict] = []
    seen: set[tuple] = set()
    for chunk in chunks:
        prompt = _build_delta_prompt(records, ledger, answers=answers,
                                     focus_clumps=chunk)
        try:
            raw = await llm.complete(prompt, system=_DELTA_SYS,
                                     max_tokens=DELTA_CHUNK_MAX_TOKENS)
        except llm.AllProvidersFailed as exc:
            # The provider is gone — don't wait on it once per chunk.
            log.warning("topic_llm.propose_deltas: all providers failed: %s", exc)
            return [], []
        try:
            parsed = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            log.warning("propose_deltas: JSON parse failed: %s", exc)
            continue
        deltas_raw = parsed.get("deltas") if isinstance(parsed, dict) else parsed
        questions_raw = parsed.get("questions") if isinstance(parsed, dict) else []
        for d in _validate_deltas(deltas_raw, clumps, repos):
            key = (d.get("type"), d.get("a"), d.get("b"), d.get("cluster"),
                   d.get("repo"))
            if key in seen:
                continue
            seen.add(key)
            deltas.append(d)
        questions.extend(_validate_questions(questions_raw, repos))
    deltas.sort(key=lambda d: -(d.get("confidence") or 0))
    return deltas[:10], questions[:5]