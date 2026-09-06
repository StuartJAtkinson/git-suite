# UX conventions — git-suite

Reference document for the SvelteKit UI in `ui/frontend/src/`. It records what
the code **actually does today**, not what it should do. Open questions live in
`STYLE.md`; fixable drift from these conventions lives in `ISSUES.md`.

Everything global is in `ui/frontend/src/app.css` (268 lines). Route files carry
only styles genuinely local to that page — anything used by two or more pages
gets promoted into `app.css` (that's how `.tag`, `.bar` and `.gap-pill` got
there).

---

## Design tokens

Declared in one `:root` block at `app.css:264`:

| Token | Value | Role |
|---|---|---|
| `--border` | `#e5e7eb` | every card / panel / section / row border, and the track of progress bars |
| `--quiet-text` | `#9ca3af` | de-emphasised text: `.quiet`, `.empty`, `.tag.none`, install's DAG edge strokes |
| `--mono` | `'Consolas', 'Fira Code', monospace` | **all** monospace: repo names, paths, hashes, commands, `kbd`, `.preview-box` |

There are no other tokens. Everything else below is a literal hex repeated
across files — see `ISSUES.md` for the ones that should be promoted.

## Colour

**Brand blue `#0057b7`** — links, the default `<button>`, the focus ring
(`box-shadow: 0 0 0 3px rgba(0,87,183,0.15)`), `.hub-card:hover`,
`.progress-fill`, and the selected-card border on Triage. Hover/active darkens
to `#003d8f`.

**Surfaces** — page background `#f0f2f5`; cards/panels `#fff`; inset rows
(`.repo-row`, `.ref-card`, `.scan-row:nth-child(even)`) `#f9fafb`; the nav bar
and `.stat-value` use the near-black `#1a1a2e`; `.preview-box` is a dark
terminal panel (`#0d1117` on `#e6edf3`).

**Grey text ramp**, darkest to lightest: `#374151` (form labels, `.section-head
h2`, body copy in cards) → `#4b5563` (`.hub-card .desc`, secondary meta) →
`#6b7280` (`.muted`, `.sub`, `.hint`, `.loading`, crumbs, counts) →
`var(--quiet-text)` `#9ca3af` (`.quiet`, `.empty`).

**Semantic pairs** are always background + matching darker text, Tailwind-ish
families, and are used consistently for these meanings:

| Meaning | Background | Text | Where |
|---|---|---|---|
| error / destructive | `#fef2f2` | `#dc2626` | `.error-msg`, `button.danger` |
| success / done / keep | `#f0fdf4` `#d1fae5` `#dcfce7` | `#15803d` `#065f46` `#166534` | `.ok-msg`, `button.success`, `.cat-keep`, `.tag.ok`, `.tag.make` |
| info / hub / absorb | `#eff6ff` `#dbeafe` | `#1e40af` | `.info-msg`, `.lang-tag`, `.cat-absorb`, `.p3`, `.gap-pill` |
| warn / archive | `#fef3c7` | `#92400e` | `.cat-archive`, `.tag.arch` |
| neutral / orphan / none | `#f3f4f6` | `#4b5563` | `.cat-orphan`, `.p4`, `.tag.none` |
| docs | `#e0e7ff` | `#3730a3` | `.tag.doc` |

Priority badges `.p1`–`.p4` run red → orange → blue → grey.

> Two of these roles currently have more than one hex in circulation (the
> amber text and the light-blue info background). Which value wins is an open
> question in `STYLE.md`, not a convention — don't treat the table above as
> settled for those two rows.

## Shape and spacing

- **Radius**: `10px` cards and hub cards · `8px` panels, `.bar`, `.preview-box`,
  `.ref-card` · `6px` inputs, buttons, `.repo-row`, messages · `4px` badges,
  tags, `.scan-row` · `2px` progress bars · `50%` avatars.
- **Base font size** is `15px` on `body`. Page `<h1>` is `1.5rem`, section
  `<h2>` `1rem`, body/inputs `0.875–0.95rem`, meta and hints `0.8–0.85rem`,
  badges and tags `0.7–0.74rem`.
- **Font weights** used: 400, 500 (labels, buttons), 600 (badges, headings),
  700 (nav brand, `.stat-value`).
- **Gaps** cluster on `0.25 / 0.4 / 0.5 / 0.6 / 0.75 / 1rem`.
- **Page padding**: `main { padding: 1.25rem 1.5rem; }`. Cards pad `1.5rem`,
  compact panels `0.6–0.9rem`.
- Font stack is `system-ui, -apple-system, sans-serif` everywhere except
  monospace, which is always `var(--mono)`.

## Page skeleton

Every workflow route follows the same shape:

```
<div class="page-header">
  <h1>{Step name}</h1>
  <p class="sub">{one sentence: what this step does}</p>
</div>
[<div class="bar"> … page-level controls … </div>]        ← Install, Order
<div class="section">
  <div class="section-head"><h2>{Group} ({count})</h2></div>
  … rows …
</div>
```

- `.section-head` is a flex row with a bottom `1px solid var(--border)`; the
  heading sits left, any section-scoped action sits right.
- Counts go in the `<h2>` in parentheses.
- `.bar` is the shared horizontal control strip (white, bordered, `0.85rem`
  padding) for controls that apply to the whole page.
- `.hint` is an inline explanatory paragraph inside a section; `.sub` is the
  page- or section-level subtitle. `.crumb` is a back-link line above the `h1`.
- Empty states use `.empty` (italic, quiet) inline, or
  `.info-msg.centered` (max 560px, centred) for a whole-page empty state.

## Controls

- **Button variants** come from `app.css:66-91` and are the only ones intended
  to exist: default (brand blue) · `.secondary` (grey) · `.success` (green) ·
  `.danger` (red) · `.ghost` (transparent, `#d1d5db` outline). Global sizes are
  default and `.sm`; Order adds a page-local `.xs` for its reorder arrows.
- **The primary action of a group is the leftmost button**; `.ghost` /
  `.secondary` alternatives follow it (Accept → Discard, on Order and Cluster).
- **Row-level actions are right-aligned** via `style="margin-left:auto"` on the
  button (Execute's Push / Mark absorbed / Hide).
- **Destructive actions are always `.danger`** and, for hubs, gated: a hub must
  be archived before delete is offered.
- **Icon prefixes** are a glyph + space + label, never an icon alone:
  `↻ Re-check`, `⤓ Pull from GitHub`, `⏸ Stop enriching`, `✨ Enrich`,
  `↶ Undo`. The exception is Order's row-reorder cluster, which is
  glyph-only (`⤒ ↑ ↓ ⤓`, `button.ghost.xs`) with the label carried by `title`.
- **Ellipsis is the character `…`**, never three dots.
- Keyboard shortcuts are shown with `<kbd>` (mono, `var(--border)` background)
  in the page `.sub` — see Triage.

## Terminology

- The nine workflow steps, in nav order, are **Setup · Scan · Cluster · Own ·
  Order · Triage · Execute · Install · Summary**. The nav label is the name of
  the step; page `<h1>`s are meant to repeat it verbatim.
- A repo's verdict is one of **absorb · archive · keep · orphan** — used as the
  `.cat-*` badge classes, in `plan.json`, and in the Triage keyboard map. There
  is no fifth verdict and no synonyms ("merge", "consolidate", "drop" are not
  used in the UI).
- **Hub** = a destination repo other repos are absorbed into. **Absorb** moves a
  repo's *content* into a hub; at feature level it moves a *feature* into an
  owned repo. Hubs are never seeded or curated — they emerge from the scan.
- **Pull** is the GitHub fetch; **Enrich** is the follow-up per-repo detail
  fetch; **Reconcile** is comparing plan against live GitHub.
