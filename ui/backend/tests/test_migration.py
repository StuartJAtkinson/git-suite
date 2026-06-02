"""migration: scaffold, rule-template checklist, MIGRATION.md composition."""
import asyncio

import pytest


def test_slug():
    from services import migration
    assert migration.slug("FFXIV-Scraping") == "ffxiv-scraping"
    assert migration.slug("html-tree-generator__chrome-extension") == "html-tree-generator-chrome-extension"


def test_scaffold_for():
    from services import migration
    sc = migration.scaffold_for("game-hub", ["AllaganTools", "Lumina"])
    assert sc[0] == {"repo": "AllaganTools", "module": "allagantools", "path": "modules/allagantools/"}


def test_rule_checklist_mentions_repo_and_hub():
    from services import migration
    steps = migration._rule_checklist(
        {"name": "AllaganTools", "language": "C#", "stars": 12, "pushed_at": "2024-05-01T00:00:00Z"},
        "game-hub",
    )
    assert any("AllaganTools" in s for s in steps)
    assert any("game-hub" in s for s in steps)
    assert any("project reference" in s for s in steps)   # C# dependency hint


def test_checklist_for_falls_back_to_rule(monkeypatch):
    from services import migration, llm
    monkeypatch.setattr(llm, "has_provider", lambda: False)
    out = asyncio.run(migration.checklist_for(
        {"name": "tweetext", "language": "Python", "topics": []},
        {"name": "media-hub", "layer": 4, "description": "media"},
        None,
    ))
    assert out["source"] == "rule"
    assert len(out["steps"]) >= 5


def test_build_migration_md():
    from services import migration
    items = [
        {"repo": "tweetext", "module": "tweetext", "path": "modules/tweetext/",
         "live": True, "done": False, "steps": ["step one", "step two"]},
    ]
    md = migration.build_migration_md("media-hub", {"layer": 4, "description": "media"}, items)
    assert "# media-hub — Migration Plan" in md
    assert "modules/tweetext/" in md
    assert "1. step one" in md
