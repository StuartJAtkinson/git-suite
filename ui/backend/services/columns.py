"""
columns.py — single source of truth for the Order page's column names and
the default compat-tag vocabulary.

Tree-of-Knowledge ordering. Renaming the columns is a one-edit change:
this module is read by the API, the Suggest prompt construction, and (via
mirror constants) the frontend.
"""
from __future__ import annotations

# Order matters: this is the ontological left-to-right ordering and the
# display order of column filter toggles on the Order page.
COLUMNS: tuple[str, ...] = ("Gather", "Analyse", "Display")

# Map column name -> boolean column on hub_order. Kept in code (not the DB)
# so renaming a column doesn't require a schema migration.
COL_FLAGS: dict[str, str] = {
    "Gather":  "is_gather",
    "Analyse": "is_analyse",
    "Display": "is_display",
}


def default_compat_tags() -> list[str]:
    """Seed compat-tag vocabulary. Each hub can override via the API."""
    return [
        "Inspiration",
        "Imports From",
        "Exports To",
        "Component Of",
        "Replacement For",
        "Depends On",
    ]
