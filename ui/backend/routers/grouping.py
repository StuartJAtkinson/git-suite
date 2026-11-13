"""grouping.py — read + reset the durable grouping ledger.

The ledger is pre-plan working state (see GROUPING.md). It is seeded whenever
the Cluster page groups/imports, and read back here so the walk can resume.
Portfolio-scoped, so there is no session_id in these routes."""
from fastapi import APIRouter

import grouping_store

router = APIRouter()


@router.get("/grouping")
async def get_grouping():
    ledger = grouping_store.load()
    return {"summary": grouping_store.summary(ledger), "ledger": ledger}


@router.post("/grouping/reset")
async def reset_grouping():
    ledger = grouping_store.reset()
    return {"summary": grouping_store.summary(ledger), "ledger": ledger}
