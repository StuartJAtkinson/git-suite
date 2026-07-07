"""cluster: theme suggestion, union-find grouping, form action, mixed-source."""
import asyncio
import json

from services import cluster
from routers.cluster import form, FormRequest, propose, refresh_forks


def test_suggest_theme_from_topics():
    members = [
        {"name": "tilemaker", "topics": ["osm", "maps"]},
        {"name": "streets-gl", "topics": ["maps", "webgl"]},
    ]
    s = cluster.suggest_theme(members)
    assert s["name"] == "maps-hub"            # 'maps' is the most common topic
    assert "maps" in s["description"]


def test_kmeans_partitions_into_k():
    # Two tight blobs; k=2 must separate them.
    v = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0], [0.01, 0.99]]
    groups = cluster._kmeans(v, k=2)
    assert sorted(len(g) for g in groups) == [2, 2]


def test_kmeans_does_not_chain():
    # A~B and B~C (cos 0.707) but A≁C (cos 0). Single-linkage union-find would
    # chain all three; k-means with k=2 keeps the far pair apart.
    a, b, c = [1.0, 0.0], [0.7071, 0.7071], [0.0, 1.0]
    groups = cluster._kmeans([a, b, c], k=2)
    assert sorted(len(g) for g in groups) == [1, 2]


def test_kmeans_clamps_k_to_n():
    groups = cluster._kmeans([[1.0, 0.0]], k=5)   # k > n
    assert len(groups) == 1 and groups[0] == [0]


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


# -- mixed-source clustering --------------------------------------------------


def _fake_embed_factory(plan: dict[str, list[float]]):
    """Return an `embed` coroutine that maps each text to a deterministic
    vector from `plan`, with a tiny perturbation for unknown texts."""
    import math
    def _vec(text: str) -> list[float]:
        for key, v in plan.items():
            if key in text:
                return list(v)
        # Unknown: map to a fresh unit vector derived from the hash so
        # unknown items form their own cluster.
        h = abs(hash(text))
        return [math.sin(h), math.cos(h), 0.0]
    async def embed(texts):
        return [_vec(t) for t in texts]
    return embed


def test_build_clusters_mixed_returns_none_without_embeddings(monkeypatch):
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: False)
    assert asyncio.run(cluster.build_clusters_mixed(
        [{"name": "x", "aim": "", "topics": [], "language": "", "stars": 0}],
        [], [],
    )) is None


def test_build_clusters_mixed_drops_singletons_with_min_size(monkeypatch):
    """min_cluster_size=2 demotes one-member clusters to orphans_returned."""
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: True)
    # Two tight blobs + one totally unlike them → k=2 puts the loner alone;
    # with min_cluster_size=2, the loner gets dropped into the orphan list.
    monkeypatch.setattr(embeddings, "embed", _fake_embed_factory({
        "alpha": [1.0, 0.0, 0.0],
        "beta":  [0.0, 1.0, 0.0],
    }))
    pool = [
        {"name": "alpha-1", "aim": "alpha", "topics": [], "language": "", "stars": 0},
        {"name": "alpha-2", "aim": "alpha", "topics": [], "language": "", "stars": 0},
        {"name": "beta-1",  "aim": "beta",  "topics": [], "language": "", "stars": 0},
    ]
    clusters, dropped = asyncio.run(cluster.build_clusters_mixed(
        pool, [], [], k=2, min_cluster_size=2,
    ))
    sizes = sorted(c["size"] for c in clusters)
    assert sizes == [2]              # one stays, the lone beta is dropped
    assert len(dropped) == 1
    assert dropped[0]["name"] == "beta-1"


def test_build_clusters_mixed_tags_sources_and_groups(temp_db, monkeypatch):
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: True)
    # owned + fork + star that all point at "maps" get one vector; a star
    # about audio points elsewhere and ends up alone.
    maps_vec = [1.0, 0.0, 0.0]
    other_vec = [0.0, 1.0, 0.0]
    monkeypatch.setattr(embeddings, "embed", _fake_embed_factory({
        "maps": maps_vec, "audio": other_vec,
    }))

    owned = [{"name": "tilemaker", "aim": "build maps", "topics": ["maps"],
              "language": "Python", "stars": 0}]
    forks = [{"name": "map-fork", "description": "fork of maps", "topics": ["maps"],
              "language": "Python", "stars": 0, "full_name": "u/map-fork"}]
    stars = [
        {"name": "osm-tools", "description": "maps stuff", "topics": ["maps"],
         "language": "JS", "stars": 100, "full_name": "ext/osm-tools"},
        {"name": "audio-fx", "description": "audio dsp", "topics": ["audio"],
         "language": "C++", "stars": 50, "full_name": "ext/audio-fx"},
    ]

    clusters, _orphans = asyncio.run(cluster.build_clusters_mixed(owned, forks, stars, k=2))
    assert clusters is not None
    # Largest first; the maps cluster has 3 members, the audio one has 1.
    assert clusters[0]["size"] == 3
    assert clusters[-1]["size"] == 1
    sources = sorted(m["source"] for m in clusters[0]["members"])
    assert sources == ["fork", "owned", "star"]


def test_propose_mixed_includes_counts_and_source(temp_db, isolated_plan, monkeypatch):
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: True)
    monkeypatch.setattr(embeddings, "embed", _fake_embed_factory({"x": [1.0, 0.0, 0.0]}))

    # Seed: a session + scan with one orphan, plus a fork + a star.
    from tests.conftest import insert_scan
    insert_scan(temp_db, repos=[{"name": "x-repo", "aim": "x"}])
    # In-memory fork + star rows (skip the github round-trip).
    async def _seed_snapshots():
        async for db in temp_db.get_db():
            await db.execute(
                "INSERT INTO fork (full_name, name, owner, description, topics, "
                "language, parent_full_name, pushed_at, archived, url) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("u/x-fork", "x-fork", "u", "fork of x", "[]", "Python",
                 "ext/x", "", 0, ""),
            )
            await db.execute(
                "INSERT INTO starred_repo (full_name, name, owner, description, "
                "topics, language, stars, pushed_at, archived, url) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("ext/x-star", "x-star", "ext", "x", "[]", "Python", 1, "", 0, ""),
            )
            await db.commit()
    asyncio.run(_seed_snapshots())

    res = asyncio.run(propose("s1", source="mixed"))
    assert res["source"] == "mixed"
    assert res["counts"] == {"owned": 1, "forks": 1, "stars": 1}
    assert res["available"] is True
    # All three sources land in the one big cluster.
    assert res["clusters"][0]["size"] == 3
    sources = sorted(m["source"] for m in res["clusters"][0]["members"])
    assert sources == ["fork", "owned", "star"]


def test_propose_owned_legacy_path_still_works(temp_db, isolated_plan, monkeypatch):
    """?source=owned is mixed-with-no-forks-no-stars: same clustering, owned-only."""
    from services import embeddings
    monkeypatch.setattr(embeddings, "has_embeddings", lambda: True)
    monkeypatch.setattr(embeddings, "embed", _fake_embed_factory({"a": [1.0, 0.0, 0.0]}))

    from tests.conftest import insert_scan
    insert_scan(temp_db, repos=[{"name": "a-repo", "aim": "a thing"}])
    res = asyncio.run(propose("s1", source="owned"))
    assert res["source"] == "owned"
    # owned now reports counts too — forks/stars are simply zero.
    assert res["counts"] == {"owned": 1, "forks": 0, "stars": 0}
    # No fork or star in the input; only the owned repo shows up.
    assert res["clusters"][0]["members"][0]["source"] == "owned"


def test_apply_forbids_drops_member_and_keeps_rest():
    from routers.cluster import _apply_forbids
    clusters = [
        {"suggested_name": "maps-hub", "members": [
            {"repo": "tilemaker"}, {"repo": "streets-gl"},
        ], "size": 2},
        {"suggested_name": "audio-hub", "members": [
            {"repo": "audio-fx"}, {"repo": "audio-fx-2"},
        ], "size": 2},
    ]
    forbid_map = {"tilemaker": ["maps-hub"], "streets-gl": ["audio-hub"]}
    dropped = _apply_forbids(clusters, forbid_map)
    # Only tilemaker is dropped: streets-gl's forbid ("audio-hub") doesn't match.
    assert {d["repo"] for d in dropped} == {"tilemaker"}
    # The maps cluster now has 1 member; audio cluster untouched.
    assert clusters[0]["size"] == 1
    assert clusters[1]["size"] == 2
