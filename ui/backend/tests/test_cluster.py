"""cluster: theme suggestion, union-find grouping, form action."""
import asyncio

from services import cluster
from routers.cluster import form, FormRequest


def test_suggest_theme_from_topics():
    members = [
        {"name": "tilemaker", "topics": ["osm", "maps"]},
        {"name": "streets-gl", "topics": ["maps", "webgl"]},
    ]
    s = cluster.suggest_theme(members)
    assert s["name"] == "maps-hub"            # 'maps' is the most common topic
    assert "maps" in s["description"]


def test_union_find_components():
    v = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]]
    groups = cluster._union_find(v, threshold=0.9)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]                     # {0,1} together, {2} alone


def test_build_clusters_none_without_embeddings(monkeypatch):
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: False)
    assert asyncio.run(cluster.build_clusters([{"name": "x"}])) is None


def test_form_creates_hub_and_absorbs(isolated_plan):
    isolated_plan.clear()
    res = asyncio.run(form("s1", FormRequest(
        hub_name="map-suite", layer=5, description="maps", boundary="spatial",
        members=["tilemaker", "streets-gl"],
    )))
    plan = isolated_plan.get_plan()
    assert "map-suite" in plan["hubs"]
    assert set(plan["hubs"]["map-suite"]["absorbs"]) == {"tilemaker", "streets-gl"}
    assert res["absorbed"] == ["tilemaker", "streets-gl"]


def test_form_promote_keeps_member_as_hub(isolated_plan):
    isolated_plan.clear()
    asyncio.run(form("s1", FormRequest(
        hub_name="streets-gl", layer=5, members=["tilemaker", "streets-gl"],
        promote="streets-gl",
    )))
    plan = isolated_plan.get_plan()
    # promoted repo is the hub, not absorbed into itself
    assert plan["hubs"]["streets-gl"]["absorbs"] == ["tilemaker"]
