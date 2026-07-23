"""cluster: form action + the one-shot LLM theme grouping."""
import asyncio

from routers.cluster import form, FormRequest


def test_form_creates_hub_and_absorbs(isolated_plan):
    isolated_plan.clear()
    res = asyncio.run(form("s1", FormRequest(
        hub_name="map-suite", description="maps", boundary="spatial",
        members=["tilemaker", "streets-gl"],
    )))
    plan = isolated_plan.get_plan()
    assert "map-suite" in plan["hubs"]
    assert set(plan["hubs"]["map-suite"]["absorbs"]) == {"tilemaker", "streets-gl"}
    assert res["absorbed"] == ["tilemaker", "streets-gl"]


def test_form_promote_keeps_member_as_hub(isolated_plan):
    isolated_plan.clear()
    asyncio.run(form("s1", FormRequest(
        hub_name="streets-gl", members=["tilemaker", "streets-gl"],
        promote="streets-gl",
    )))
    plan = isolated_plan.get_plan()
    # promoted repo is the hub, not absorbed into itself
    assert plan["hubs"]["streets-gl"]["absorbs"] == ["tilemaker"]


# -- one-shot LLM topic grouping ----------------------------------------------


def test_propose_returns_available_false_when_no_scan(temp_db):
    """No scan → no orphans → no themes. Page should ask the user to group."""
    res = asyncio.run(__import__("routers.cluster", fromlist=["propose"]).propose(
        "s1", saved_only=True))
    assert res["available"] is False
    assert "Group" in res["reason"]
