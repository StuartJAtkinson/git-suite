"""readme: compose the roadmap section from the LIVE plan (not the static seed)
+ render the Tree-of-Knowledge ordering from the hub_order table."""


def test_compose_reads_live_plan(isolated_plan):
    from routers import readme
    section = readme.compose_section("media-hub", plan=isolated_plan.get_plan())
    assert "Integration Roadmap" in section
    assert "comictagger" in section          # a seeded media-hub absorb
    assert readme._ROADMAP_START in section and readme._ROADMAP_END in section


def test_compose_reflects_plan_edits(isolated_plan):
    from routers import readme
    isolated_plan.set_verdict("brand-new-repo", "absorb", "media-hub")
    section = readme.compose_section("media-hub", plan=isolated_plan.get_plan())
    assert "brand-new-repo" in section        # proves it's the live plan, not the seed


def test_compose_includes_alternatives(isolated_plan):
    from routers import readme
    section = readme.compose_section("personal-ai-os", plan=isolated_plan.get_plan())
    assert "OSS alternatives" in section
    assert "Commercial alternatives" in section


# --- Tree-of-Knowledge ordering block -------------------------------------

def test_compose_renders_tok_block_when_hub_order_present(isolated_plan):
    """When hub_order rows are passed, the README gains a ToK ordering
    subsection listing each absorb in its ordered position with column
    flags, compat tags, and feature annotations as sub-bullets."""
    from routers import readme
    # media-hub's seeded absorbs include comictagger + simklExporter
    hub_order_rows = [
        {"repo": "media-hub", "position": 0, "is_gather": 0, "is_analyse": 0, "is_display": 0,
         "compat_tags": [], "feature_annotations": []},
        {"repo": "comictagger", "position": 1, "is_gather": 1, "is_analyse": 0, "is_display": 1,
         "compat_tags": ["Imports From"], "feature_annotations": ["reads CBZ", "emits JXL"]},
        {"repo": "simklExporter", "position": 2, "is_gather": 1, "is_analyse": 0, "is_display": 0,
         "compat_tags": [], "feature_annotations": []},
    ]
    section = readme.compose_section("media-hub", isolated_plan.get_plan(), hub_order_rows)
    assert "Tree-of-Knowledge ordering" in section
    # Position numbers appear in order
    p1 = section.index("`#1`")
    p2 = section.index("`#2`")
    assert p1 < p2
    # Column flags render as a tag line
    assert "Gather" in section and "Display" in section
    # Compat tag + annotations render as sub-bullets
    assert "Imports From" in section
    assert "reads CBZ" in section
    assert "emits JXL" in section
    # Hub repo is rendered as a header
    assert "_(hub)_" in section


def test_compose_omits_tok_block_when_no_hub_order(isolated_plan):
    """The ToK block is opt-in. With hub_order_rows=None or [], the README
    keeps the original alphabetical 'Repos to absorb' block and does not
    add the ordering subsection."""
    from routers import readme
    section_no_rows = readme.compose_section("media-hub", isolated_plan.get_plan(), None)
    section_empty = readme.compose_section("media-hub", isolated_plan.get_plan(), [])
    assert "Tree-of-Knowledge ordering" not in section_no_rows
    assert "Tree-of-Knowledge ordering" not in section_empty
    # Original list is still there
    assert "Repos to absorb" in section_no_rows
    assert "comictagger" in section_no_rows


def test_compose_tok_block_pins_hub_repo_to_top(isolated_plan):
    """Even if a hub_order row says the hub repo is at position 5, the
    README pins it to the top of the ordering block."""
    from routers import readme
    hub_order_rows = [
        {"repo": "media-hub", "position": 5, "is_gather": 0, "is_analyse": 0, "is_display": 0,
         "compat_tags": [], "feature_annotations": []},
        {"repo": "comictagger", "position": 0, "is_gather": 1, "is_analyse": 0, "is_display": 0,
         "compat_tags": [], "feature_annotations": []},
    ]
    section = readme.compose_section("media-hub", isolated_plan.get_plan(), hub_order_rows)
    # The "_(hub)_" marker appears before any `#N` position
    hub_idx = section.index("_(hub)_")
    p1 = section.index("`#")
    assert hub_idx < p1


def test_compose_tok_block_falls_back_for_unordered_repos(isolated_plan):
    """Absorbs that don't have a hub_order row still appear in the ToK block
    (sorted alphabetically at the tail) so a member is never silently
    dropped from the README."""
    from routers import readme
    hub_order_rows = [
        {"repo": "media-hub", "position": 0, "is_gather": 0, "is_analyse": 0, "is_display": 0,
         "compat_tags": [], "feature_annotations": []},
        {"repo": "comictagger", "position": 1, "is_gather": 1, "is_analyse": 0, "is_display": 0,
         "compat_tags": [], "feature_annotations": []},
    ]
    section = readme.compose_section("media-hub", isolated_plan.get_plan(), hub_order_rows)
    # Unordered absorbs from the seed (e.g. simklExporter) are still
    # rendered, with the 'not yet ordered' marker.
    assert "not yet ordered" in section
    assert "simklExporter" in section
