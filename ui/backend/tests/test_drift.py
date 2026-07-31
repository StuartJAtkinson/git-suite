"""drift: periodic reconcile snapshots."""
import asyncio

from conftest import insert_scan


def test_snapshot_writes_a_row(temp_db, isolated_plan):
    from services import drift
    insert_scan(temp_db, repos=[
        {"name": "quivr"},
        {"name": "git-suite"},
        {"name": "MarvelGraph"},
        {"name": "random-xyz"},
    ])
    sid = asyncio.run(drift.snapshot_now(source="manual"))
    assert sid > 0
    latest = asyncio.run(drift.latest_snapshot())
    assert latest is not None
    assert latest["source"] == "manual"
    assert latest["stats"]["live"] == 4
    assert latest["stats"]["absorb"] == 1
    assert latest["stats"]["keep"] == 1
    assert latest["stats"]["archive"] == 1
    assert latest["stats"]["orphan"] == 1
    # Per-hub rollup is non-empty — sample plan has 9 hubs.
    assert len(latest["hubs"]) >= 1
    # Hubs that DO have quivr listed absorb should report 1 absorb target.
    quivr_hub = next(h for h in latest["hubs"] if "quivr" in h.get("absorbs", [])) \
        if any("quivr" in h.get("absorbs", []) for h in latest["hubs"]) else None
    if quivr_hub:
        assert quivr_hub["absorb_total"] >= 1


def test_snapshot_returns_minus_one_when_no_scan(temp_db, isolated_plan):
    from services import drift
    # No sessions / no scans at all.
    assert asyncio.run(drift.snapshot_now()) == -1


def test_history_returns_oldest_last_by_default(temp_db, isolated_plan):
    from services import drift
    insert_scan(temp_db, repos=[{"name": "quivr"}])
    asyncio.run(drift.snapshot_now(source="manual"))
    asyncio.run(drift.snapshot_now(source="manual"))
    snaps = asyncio.run(drift.history())
    assert len(snaps) == 2
    # Newest first.
    assert snaps[0]["taken_at"] >= snaps[1]["taken_at"]


def test_scheduler_interval_floor(monkeypatch):
    """A misconfigured interval can't push the scheduler below the floor."""
    from services import drift
    s = drift.DriftScheduler()

    import json
    from pathlib import Path
    cfg_path = Path.home() / ".git-suite" / "config.json"
    original = None
    if cfg_path.exists():
        original = cfg_path.read_text(encoding="utf-8")

    try:
        # Point the scheduler at a tiny in-memory config.
        cfg_path.write_text(json.dumps({"drift": {"interval_seconds": 5}}), encoding="utf-8")
        assert asyncio.run(s._interval()) == drift.MIN_INTERVAL_SECONDS
    finally:
        if original is None:
            cfg_path.unlink(missing_ok=True)
        else:
            cfg_path.write_text(original, encoding="utf-8")


def test_router_endpoints(temp_db, isolated_plan):
    """The router reads/writes through the same service functions."""
    from fastapi.testclient import TestClient
    import main
    from services import drift
    insert_scan(temp_db, repos=[{"name": "quivr"}, {"name": "git-suite"}])

    client = TestClient(main.app)
    # No snapshot yet -> latest is null.
    r = client.get("/api/drift/status")
    assert r.status_code == 200
    assert r.json()["latest"] is None
    # Trigger one.
    r = client.post("/api/drift/snapshot")
    assert r.status_code == 200
    assert r.json()["id"] > 0
    # Now latest returns it.
    r = client.get("/api/drift/status")
    assert r.status_code == 200
    body = r.json()
    assert body["latest"] is not None
    assert body["interval_seconds"] >= drift.DEFAULT_INTERVAL_SECONDS
    # History returns it.
    r = client.get("/api/drift/history")
    assert r.status_code == 200
    assert len(r.json()["snapshots"]) == 1
