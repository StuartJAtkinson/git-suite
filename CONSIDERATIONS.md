# Considerations — git-suite

Design decisions that need a human call (not guessed at). See `CONSIDERATIONS.html`
for a rendered worksheet — reply with e.g. `1a, 2b`.

- 1. Two hex values are used interchangeably for the same "card/panel border" role: `#dde1e9` (app.css's `.card`/`.hub-card`, plus `promote`'s `.fork` and `summary`'s stat box/`.member-col`) vs `#e5e7eb` (used in 9 of 11 route files for the same semantic border). Which one becomes the single token?
- 2. Three hex values are used for the same "warn/highlight amber text" role: `#92400e` (execute, order, scan, setup), `#b45309` (cluster, promote, scan), `#78350f` (triage only). Which one becomes the single token?
- 3. Three hex values are used interchangeably for the same "light-blue info tag" role (all paired with `#1e40af` text): `#eff6ff` (`app.css` `.info-msg`/`.lang-tag`, triage `.hub-btn`/`.recommend-row.star-row`), `#dbeafe` (`app.css` `.badge`/`.p3`/`.cat-absorb`, order `.hub-badge`, triage `.hub-btn:hover`), `#e6effa` (cluster/scan `.domain-pill`, scan's inline "enriched" badge, order `.col.checked`). Which one becomes the single token?
