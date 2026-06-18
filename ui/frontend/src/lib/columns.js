// columns.js — mirror of services/columns.py. The single source of truth
// for the Order page's three column names. Edit here AND in
// ui/backend/services/columns.py to rename.

export const COLUMNS = ['Gather', 'Analyse', 'Display'];

// Map column name -> boolean field on the API response. Kept in JS so the
// renames flow through without touching the data shape.
export const COL_FLAGS = {
  Gather:  'is_gather',
  Analyse: 'is_analyse',
  Display: 'is_display',
};

// Prefix symbol shown on cluster nodes to indicate the source
// (owned / fork / star). Matches the Python router's `source` field.
export const SOURCE_GLYPH = {
  owned: '[O]',
  fork:  '[F]',
  star:  '[S]',
};
