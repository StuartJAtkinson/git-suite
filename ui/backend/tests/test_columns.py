"""columns: single source of truth for the Order page."""
from services import columns


def test_columns_are_three_toK_steps():
    assert columns.COLUMNS == ("Gather", "Analyse", "Display")


def test_col_flags_cover_every_column():
    for c in columns.COLUMNS:
        assert c in columns.COL_FLAGS
        assert columns.COL_FLAGS[c].startswith("is_")


def test_default_compat_tags_is_a_list_of_strings():
    tags = columns.default_compat_tags()
    assert isinstance(tags, list)
    assert len(tags) >= 3
    assert all(isinstance(t, str) and t.strip() for t in tags)
