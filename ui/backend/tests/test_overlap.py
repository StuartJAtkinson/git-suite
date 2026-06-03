"""overlap: straddle detection + matrix."""
from routers.overlap import _analyse


def test_clear_repo_is_not_a_boundary_case():
    repos = [{"name": "tilemaker", "aim": "osm vector map tiles geo", "language": "", "topics": []}]
    matrix, cases = _analyse(repos, ["map-suite", "game-hub"])
    assert cases == []


def test_straddling_repo_flagged_and_counted():
    # text hitting both map ("map") and game ("dungeon") keyword profiles
    repos = [{"name": "thing", "aim": "procedural dungeon map generator", "language": "", "topics": []}]
    matrix, cases = _analyse(repos, ["map-suite", "game-hub"])
    assert len(cases) == 1
    pair = {cases[0]["top"][0]["hub"], cases[0]["top"][1]["hub"]}
    assert pair == {"map-suite", "game-hub"}
    # symmetric matrix increment
    assert matrix["map-suite"]["game-hub"] == 1
    assert matrix["game-hub"]["map-suite"] == 1
