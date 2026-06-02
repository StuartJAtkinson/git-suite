"""readme: compose the roadmap section from the LIVE plan (not the static seed)."""


def test_compose_reads_live_plan(isolated_plan):
    from routers import readme
    section = readme.compose_section("media-hub", [], plan=isolated_plan.get_plan())
    assert "Integration Roadmap" in section
    assert "comictagger" in section          # a seeded media-hub absorb
    assert readme._ROADMAP_START in section and readme._ROADMAP_END in section


def test_compose_reflects_plan_edits(isolated_plan):
    from routers import readme
    isolated_plan.set_verdict("brand-new-repo", "absorb", "media-hub")
    section = readme.compose_section("media-hub", [], plan=isolated_plan.get_plan())
    assert "brand-new-repo" in section        # proves it's the live plan, not the seed


def test_compose_includes_alternatives(isolated_plan):
    from routers import readme
    section = readme.compose_section("personal-ai-os", [], plan=isolated_plan.get_plan())
    assert "OSS alternatives" in section
    assert "Commercial alternatives" in section


def test_compose_merges_scraped_refs(isolated_plan):
    from routers import readme
    refs = [{"url": "https://x.test", "name": "AcmeProduct", "features": ["does X", "does Y"]}]
    section = readme.compose_section("code-suite", refs, plan=isolated_plan.get_plan())
    assert "AcmeProduct" in section
    assert "does X" in section
