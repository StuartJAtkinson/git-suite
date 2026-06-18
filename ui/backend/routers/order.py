"""
order.py — per-hub ontological ordering (Tree of Knowledge layout).

The Order page reads and writes through this router. plan.json is NOT
touched — all per-hub ordering, column classification, compat tags, and
feature annotations live in the `hub_order` and `hub_compat_tags` tables.

  GET  /api/order/{session_id}/{hub}                  full ordered list
  POST /api/order/{session_id}/{hub}                  batch save (positions, flags, tags, annotations)
  POST /api/order/{session_id}/{hub}/suggest-order    LLM: propose a reorder with per-move rationales
  POST /api/order/{session_id}/{hub}/suggest-column   LLM: propose a column for one repo
  POST /api/order/{session_id}/{hub}/compat-tags      set per-hub compat-tag vocabulary override
  POST /api/order/{session_id}/{hub}/annotate         set feature annotations for one repo
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import plan_store
from database import get_db
from routers.reconcile import reconcile
from services import llm
from services.columns import COLUMNS, COL_FLAGS, default_compat_tags

log = logging.getLogger(__name__)
router = APIRouter()


# --- helpers ---------------------------------------------------------------

async def _session(session_id: str) -> dict:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT github_token, github_user FROM session WHERE id = ?", (session_id,)
        )
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid session")
    return dict(rows[0])


async def _hub_meta(hub: str) -> dict:
    plan = plan_store.get_plan()
    meta = plan.get("hubs", {}).get(hub)
    if not meta:
        raise HTTPException(status_code=404, detail=f"unknown hub {hub!r}")
    return meta


async def _load_compat_tags(hub: str) -> list[str]:
    async for db in get_db():
        rows = await db.execute_fetchall(
            "SELECT tags FROM hub_compat_tags WHERE hub = ?", (hub,))
    if not rows:
        return default_compat_tags()
    try:
        tags = json.loads(rows[0]["tags"])
    except Exception:
        return default_compat_tags()
    # An empty override is treated as "no override" — fall back to the
    # global default so a freshly-reset hub still has a working vocabulary.
    return tags or default_compat_tags()


async def _repo_descriptions(session_id: str, repos: list[str]) -> dict[str, dict]:
    """Return {repo: {language, aim, topics, stars}} for the given repo names
    from the latest scan. Empty dict entries for repos that aren't in the
    scan (e.g. live yet, or owned but un-scanned)."""
    if not repos:
        return {}
    recon = await reconcile(session_id)
    by_name = {r["name"]: r for r in recon.get("repos", [])}
    out: dict[str, dict] = {}
    for name in repos:
        r = by_name.get(name)
        if not r:
            out[name] = {"language": "", "aim": "", "topics": [], "stars": 0}
            continue
        out[name] = {
            "language": r.get("language", ""),
            "aim": r.get("aim", ""),
            "topics": r.get("topics", []),
            "stars": r.get("stars", 0),
        }
    return out


# --- core CRUD -------------------------------------------------------------

@router.get("/order/{session_id}/{hub}")
async def get_order(session_id: str, hub: str):
    """Return the full ordered list for a hub.

    Shape: repos that the hub absorbs (from plan.json), joined with their
    `hub_order` row if one exists. Repos not yet ordered appear at the tail
    with `position = -1` and all column flags false. `compat_tags_vocab` is
    the per-hub override or the global default.
    """
    await _session(session_id)
    meta = await _hub_meta(hub)
    absorbs = list(meta.get("absorbs", []))
    # Always include the hub repo itself at position 0 — it's the
    # destination, not a candidate to order.
    repos = [hub] + [r for r in absorbs if r != hub]

    async for db in get_db():
        if repos:
            placeholders = ",".join("?" * len(repos))
            rows = await db.execute_fetchall(
                f"SELECT * FROM hub_order WHERE hub = ? AND repo IN ({placeholders})",
                (hub, *repos),
            )
        else:
            rows = []
    by_repo = {r["repo"]: dict(r) for r in rows}

    out_rows = []
    for i, name in enumerate(repos):
        existing = by_repo.get(name)
        if existing:
            try:
                ct = json.loads(existing.get("compat_tags") or "[]")
            except Exception:
                ct = []
            try:
                fa = json.loads(existing.get("feature_annotations") or "[]")
            except Exception:
                fa = []
            out_rows.append({
                "repo": name,
                "position": existing.get("position", i),
                "is_gather": bool(existing.get("is_gather")),
                "is_analyse": bool(existing.get("is_analyse")),
                "is_display": bool(existing.get("is_display")),
                "compat_tags": ct,
                "feature_annotations": fa,
                "is_hub_repo": name == hub,
            })
        else:
            out_rows.append({
                "repo": name,
                "position": -1 if name != hub else 0,
                "is_gather": False,
                "is_analyse": False,
                "is_display": False,
                "compat_tags": [],
                "feature_annotations": [],
                "is_hub_repo": name == hub,
            })

    # Stable sort: hub repo first, then by position (unpositioned at the tail
    # in name order so the user has a stable starting layout).
    out_rows.sort(key=lambda r: (
        0 if r["is_hub_repo"] else 1,
        0 if r["position"] >= 0 else 1,
        r["position"] if r["position"] >= 0 else 0,
        r["repo"],
    ))

    descriptions = await _repo_descriptions(session_id, repos)
    for row in out_rows:
        d = descriptions.get(row["repo"], {})
        row["language"] = d.get("language", "")
        row["aim"] = d.get("aim", "")
        row["topics"] = d.get("topics", [])
        row["stars"] = d.get("stars", 0)

    return {
        "hub": hub,
        "columns": list(COLUMNS),
        "compat_tags_vocab": await _load_compat_tags(hub),
        "rows": out_rows,
    }


class OrderRow(BaseModel):
    repo: str
    position: int
    is_gather: bool = False
    is_analyse: bool = False
    is_display: bool = False
    compat_tags: list[str] = []
    feature_annotations: list[str] = []


class OrderSaveRequest(BaseModel):
    rows: list[OrderRow]


@router.post("/order/{session_id}/{hub}")
async def save_order(session_id: str, hub: str, body: OrderSaveRequest):
    """Batch save. Replaces every (hub, repo) row in `rows` and deletes rows
    for absorbs that are no longer present (so removing a member from the
    hub cleans its order row too). The hub repo itself is always preserved
    at position 0."""
    await _session(session_id)
    await _hub_meta(hub)
    plan = plan_store.get_plan()
    absorbs = set(plan["hubs"][hub].get("absorbs", [])) | {hub}

    seen = set()
    async for db in get_db():
        for r in body.rows:
            if r.repo not in absorbs:
                raise HTTPException(
                    status_code=400,
                    detail=f"repo {r.repo!r} is not an absorb of hub {hub!r}",
                )
            if r.repo in seen:
                continue
            seen.add(r.repo)
            position = 0 if r.repo == hub else r.position
            await db.execute(
                """INSERT INTO hub_order
                   (hub, repo, position, is_gather, is_analyse, is_display,
                    compat_tags, feature_annotations, updated_at)
                   VALUES (?,?,?,?,?,?,?,?, datetime('now'))
                   ON CONFLICT(hub, repo) DO UPDATE SET
                     position=excluded.position,
                     is_gather=excluded.is_gather,
                     is_analyse=excluded.is_analyse,
                     is_display=excluded.is_display,
                     compat_tags=excluded.compat_tags,
                     feature_annotations=excluded.feature_annotations,
                     updated_at=datetime('now')""",
                (hub, r.repo, position,
                 1 if r.is_gather else 0,
                 1 if r.is_analyse else 0,
                 1 if r.is_display else 0,
                 json.dumps(r.compat_tags),
                 json.dumps(r.feature_annotations)),
            )
        # Drop rows for absorbs that disappeared from the plan.
        if absorbs:
            ph = ",".join("?" * len(absorbs))
            await db.execute(
                f"DELETE FROM hub_order WHERE hub = ? AND repo NOT IN ({ph})",
                (hub, *absorbs),
            )
        await db.commit()
    return {"hub": hub, "saved": len(seen)}


# --- LLM Suggest -----------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Strip ```json ... ``` fences if the model added them."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


async def _llm_json(prompt: str, system: str, max_tokens: int = 1024) -> dict | list:
    """Run the LLM and parse the response as JSON. Raises on parse error."""
    raw = await llm.complete(prompt, system=system, max_tokens=max_tokens)
    return json.loads(_strip_fences(raw))


@router.post("/order/{session_id}/{hub}/suggest-order")
async def suggest_order(session_id: str, hub: str):
    """LLM: propose a reorder of the current list.

    Returns:
      {
        "proposed": [{"repo": ..., "position": ...}, ...],
        "moves":    [{"repo": ..., "from": int, "to": int, "rationale": str}, ...],
        "rationale_overall": str
      }
    """
    await _session(session_id)
    meta = await _hub_meta(hub)
    current = await get_order(session_id, hub)
    rows = current["rows"]

    # Compact input for the prompt: name + language + aim + topics + stars
    # + current column flags. The LLM doesn't need descriptions, tags, or
    # annotations for ordering.
    repo_lines = []
    for r in rows:
        cols = [c for c in COLUMNS if r[f"is_{c.lower()}"] or
                (c == "Gather" and r["is_gather"]) or
                (c == "Analyse" and r["is_analyse"]) or
                (c == "Display" and r["is_display"])]
        col_str = ",".join(cols) or "unassigned"
        repo_lines.append(
            f"- {r['repo']} [lang={r['language']}, stars={r['stars']}, "
            f"cols={col_str}, aim={r['aim'][:200]}]"
        )
    repos_block = "\n".join(repo_lines) or "(no repos yet)"

    hub_desc = meta.get("description", "")
    hub_boundary = meta.get("boundary", "")
    system = (
        "You order software repos inside a hub along a Tree-of-Knowledge "
        "axis: foundational data first (what reality is), then "
        "transformation, then presentation. You return JSON only."
    )
    prompt = f"""Hub: {hub}
Description: {hub_desc or '(none)'}
Boundary: {hub_boundary or '(none)'}

Current ordered list (top = most foundational):
{repos_block}

Propose a new ordering. Reply with JSON in EXACTLY this shape:
{{
  "proposed": [{{"repo": "<name>", "position": <int>}}, ...],
  "moves":    [{{"repo": "<name>", "from": <int>, "to": <int>, "rationale": "<one line>"}}, ...],
  "rationale_overall": "<one paragraph>"
}}

Rules:
- Every repo in the current list must appear in `proposed` exactly once.
- Positions are 0-based and contiguous (0..N-1) with no gaps.
- The hub repo itself (if present) stays at position 0.
- Order so that Gather-classified repos come before Analyse, Analyse before Display, with reasoning per moved repo.
- `moves` lists only repos whose position changed; omit unmoved ones.
- Reply with JSON only — no prose, no fences.
"""
    out = await _llm_json(prompt, system=system, max_tokens=2048)
    return out


class SuggestColumnRequest(BaseModel):
    repo: str


@router.post("/order/{session_id}/{hub}/suggest-column")
async def suggest_column(session_id: str, hub: str, body: SuggestColumnRequest):
    """LLM: propose which column(s) a single repo belongs in.

    Returns:
      {
        "repo": ...,
        "is_gather": bool, "is_analyse": bool, "is_display": bool,
        "rationale": str
      }
    """
    await _session(session_id)
    meta = await _hub_meta(hub)
    descs = await _repo_descriptions(session_id, [body.repo])
    d = descs.get(body.repo, {})
    topics_str = ", ".join(d.get("topics") or [])

    system = (
        "You classify a single software repo into one or more of three "
        "Tree-of-Knowledge columns: Gather (ingest/scrape/store), Analyse "
        "(process/transform/automate), Display (present/visualise/UI). "
        "Return JSON only."
    )
    prompt = f"""Hub: {hub}
Hub description: {meta.get('description', '') or '(none)'}
Hub boundary: {meta.get('boundary', '') or '(none)'}

Repo: {body.repo}
Language: {d.get('language', '') or '(unknown)'}
Topics: {topics_str or '(none)'}
Description: {d.get('aim', '') or '(none)'}

Decide which of the three columns this repo belongs in. A repo can be in
more than one (e.g. a scraper that also has a UI is both Gather and
Display). Reply with JSON in EXACTLY this shape:
{{
  "is_gather": <bool>,
  "is_analyse": <bool>,
  "is_display": <bool>,
  "rationale": "<one or two sentences explaining the choice>"
}}
Reply with JSON only — no prose, no fences.
"""
    out = await _llm_json(prompt, system=system, max_tokens=512)
    out["repo"] = body.repo
    return out


# --- compat tags + annotations --------------------------------------------

class CompatTagsRequest(BaseModel):
    tags: list[str]


@router.post("/order/{session_id}/{hub}/compat-tags")
async def set_compat_tags(session_id: str, hub: str, body: CompatTagsRequest):
    """Set the per-hub compat-tag vocabulary override. Pass an empty list to
    reset to the global default."""
    await _session(session_id)
    await _hub_meta(hub)
    cleaned = [t.strip() for t in body.tags if t and t.strip()]
    async for db in get_db():
        await db.execute(
            """INSERT INTO hub_compat_tags (hub, tags, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(hub) DO UPDATE SET
                 tags=excluded.tags, updated_at=datetime('now')""",
            (hub, json.dumps(cleaned)),
        )
        await db.commit()
    return {"hub": hub, "tags": cleaned or default_compat_tags()}


class AnnotateRequest(BaseModel):
    repo: str
    annotations: list[str]


@router.post("/order/{session_id}/{hub}/annotate")
async def annotate(session_id: str, hub: str, body: AnnotateRequest):
    """Set feature annotations for one repo. Stage-5 stub — populates the
    `feature_annotations` JSON column so the README compose_section can
    render them. UI for this is intentionally out of scope for now."""
    await _session(session_id)
    await _hub_meta(hub)
    plan = plan_store.get_plan()
    if body.repo != hub and body.repo not in plan["hubs"][hub].get("absorbs", []):
        raise HTTPException(
            status_code=400,
            detail=f"repo {body.repo!r} is not an absorb of hub {hub!r}",
        )
    cleaned = [a.strip() for a in body.annotations if a and a.strip()]
    async for db in get_db():
        await db.execute(
            """INSERT INTO hub_order (hub, repo, position, feature_annotations, updated_at)
               VALUES (?, ?, -1, ?, datetime('now'))
               ON CONFLICT(hub, repo) DO UPDATE SET
                 feature_annotations=excluded.feature_annotations,
                 updated_at=datetime('now')""",
            (hub, body.repo, json.dumps(cleaned)),
        )
        await db.commit()
    return {"hub": hub, "repo": body.repo, "annotations": cleaned}
