"""End-to-end walkthrough of the full nav flow against the real FastAPI app.

This is the Phase 4 "browser walkthrough" — but cheaper. It boots the app via
TestClient, seeds one minimal session+scan, and:

  1. For routes that don't fetch GitHub, asserts a 200 with the JSON shape
     the frontend renders against.
  2. For routes that DO reach GitHub (reconcile/execute),
     proves the route is wired into the app via url_path_for (so a frontend
     call wouldn't 404 on routing) — their bodies are covered by their own
     focused tests.

The intent is "if this passes, every page in the nav has its backend
endpoint alive and returning the fields the page reads". It does NOT
verify the frontend — just the HTTP contract each page depends on.

Run:  python -m pytest tests/test_walkthrough.py -v
"""
import asyncio

from conftest import insert_scan


# Routes the nav actually calls. Each entry is (path, name) where the path
# is FastAPI url_path_for-ready and `name` is the symbol the route decorator
# names (so we can look it up in app.routes without spelling the path twice).
NAV_ROUTES = [
    ("setup",       "list_providers",          None),         # /api/config/providers
    ("scan",        "latest_scan",             {"session_id": "s1"}),  # /api/scan/latest/{session_id}
    ("hubs",        "list_hubs",               None),         # /api/hubs
    ("plan",        "get_plan",                None),         # /api/plan
    ("reconcile",   "reconcile",               {"session_id": "s1"}),  # network -> assert route only
    ("execute",     "preview",                 {"session_id": "s1"}),  # network -> assert route only
    ("stars",       "get_stars",               None),         # /api/stars
    ("migration",   "hub_migration",           {"hub": "personal-ai-os", "session_id": "s1"}),
    ("order",       "get_order",               {"session_id": "s1", "hub": "personal-ai-os"}),
    ("cluster",     "propose",                 {"session_id": "s1"}),
    ("promote",     "list_forks",              {"session_id": "s1"}),  # network -> assert route only
]


# (module, name) for routes the walkthrough actually invokes end-to-end.
OFFLINE_BODIES = {
    ("config",      "list_providers"),
    ("hubs",        "list_hubs"),
    ("plan",        "get_plan"),
    ("stars",       "get_stars"),
    ("migration",   "hub_migration"),
    ("order",       "get_order"),
}


def test_full_nav_walkthrough(temp_db, isolated_plan):
    """Every nav route is wired; the offline ones return the shape the
    frontend reads."""
    from fastapi.testclient import TestClient
    from main import app

    insert_scan(temp_db, repos=[
        {"name": "quivr", "language": "Python", "stars": 100},   # absorb of personal-ai-os
        {"name": "git-suite", "language": "Python", "stars": 1}, # keep
        {"name": "random-xyz", "language": "", "stars": 0},     # unplanned -> orphan
    ])

    with TestClient(app) as c:
        # --- 1. Route existence for every nav endpoint -----------------
        for module, name, params in NAV_ROUTES:
            try:
                url = app.url_path_for(name, **(params or {}))
            except Exception as exc:
                raise AssertionError(f"route {module}.{name} not wired: {exc}")
            assert url.startswith("/api/"), f"{name} -> {url} not under /api"

        # --- 2. Body shape for offline routes ---------------------------

        # Setup / providers
        providers = c.get("/api/config/providers").json()
        assert any(p["id"] == "anthropic" for p in providers)
        assert all({"id", "display_name", "api_type", "base_url",
                    "setup_url", "default_model", "needs_key"} <= set(p)
                   for p in providers)

        # Hubs (list + per-hub status)
        hubs = c.get("/api/hubs").json()
        for f in ("name", "priority", "description", "boundary",
                  "absorbs", "alternatives"):
            assert f in hubs[0], f"hub response missing {f!r}"

        # Plan
        plan = c.get("/api/plan").json()
        assert "hubs" in plan and "personal-ai-os" in plan["hubs"]
        assert "git-suite" in plan["keeps"]

        # Stars
        assert c.get("/api/stars").json()["count"] == 0

        # Migration (uses the seeded scan for the live/done flags)
        mig = c.get("/api/migration/hub/personal-ai-os/s1").json()
        items = {it["repo"]: it for it in mig["absorbs"]}
        assert items["quivr"]["live"] is True
        assert items["quivr"]["path"].startswith("modules/")

        # Order (empty ordering but the shape is fixed)
        o = c.get("/api/order/s1/personal-ai-os").json()
        assert "rows" in o and "compat_tags_vocab" in o
