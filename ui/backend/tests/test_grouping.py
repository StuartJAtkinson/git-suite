"""grouping_store: the durable ledger seeded from a clustering payload."""
import grouping_store


def _payload():
    return {
        "clusters": [
            {"slug": "map-suite", "suggested_name": "map-suite",
             "suggested_description": "maps", "confidence": 0.9,
             "members": [
                 {"full_name": "tilemaker", "repo": "tilemaker", "name": "tilemaker"},
                 {"full_name": "planetiler", "repo": "planetiler", "name": "planetiler"},
             ]},
            {"slug": "media", "suggested_name": "media", "confidence": 0.4,
             "members": [
                 {"full_name": "yt-dlp", "repo": "yt-dlp", "name": "yt-dlp"},
             ]},
        ],
        "orphans_returned": [
            {"full_name": "stray", "repo": "stray", "name": "stray"},
        ],
        "answers": [{"question": "q", "answer": "a"}],
        "round": 2,
    }


def test_seed_marks_members_proposed_and_orphans_unsettled(isolated_grouping):
    ledger = isolated_grouping.seed_from_clusters(_payload())

    assert ledger["statuses"]["tilemaker"] == {
        "status": "proposed", "clump": "map-suite", "confidence": 0.9, "why": ""}
    assert ledger["statuses"]["yt-dlp"]["status"] == "proposed"
    assert ledger["statuses"]["yt-dlp"]["clump"] == "media"
    assert ledger["statuses"]["yt-dlp"]["confidence"] == 0.4
    assert ledger["statuses"]["stray"]["status"] == "unsettled"
    assert ledger["statuses"]["stray"]["clump"] is None


def test_seed_records_clumps_and_round(isolated_grouping):
    ledger = isolated_grouping.seed_from_clusters(_payload())

    assert set(ledger["clumps"]) == {"map-suite", "media"}
    assert ledger["clumps"]["map-suite"]["confidence"] == 0.9
    assert ledger["round"] == 2
    assert ledger["answers"] == [{"question": "q", "answer": "a"}]


def test_summary_counts(isolated_grouping):
    isolated_grouping.seed_from_clusters(_payload())
    s = isolated_grouping.summary()
    assert s["counts"]["proposed"] == 3
    assert s["counts"]["unsettled"] == 1
    assert s["counts"]["settled"] == 0
    assert s["clumps"] == 2


def test_load_heals_missing_keys(isolated_grouping):
    # A hand-written file missing newer keys still loads with defaults.
    import json
    isolated_grouping._FILE.write_text(json.dumps({"statuses": {}}), encoding="utf-8")
    ledger = isolated_grouping.load()
    assert ledger["clumps"] == {}
    assert ledger["answers"] == []
    assert ledger["floor"] == 0.85


def test_reset_clears_everything(isolated_grouping):
    isolated_grouping.seed_from_clusters(_payload())
    ledger = isolated_grouping.reset()
    assert ledger["statuses"] == {}
    assert ledger["clumps"] == {}
    assert ledger["round"] == 0
