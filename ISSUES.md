# Issues — git-suite (GitHub Index Builder)

## Open

- [ ] **L9 Creative has no hub** — `VTuberLIVE` (live audio-driven generative visuals) is unique with no OSS/commercial equivalent; currently kept as-is but has no layer home. Consider a `creative-hub` if other L9 repos accumulate *(found 2026-05-25)*

- [ ] **fetch_following() not paginated** — removed as a concern (following list no longer fetched in simplified script); if re-added later, remember to paginate beyond 100 *(found 2026-05-24)*
- [ ] **Absorb targets include non-owned repos** — some items in NEW_REPOS absorbs lists (e.g. `xivapi.com`, `autoEdit_2`, `intelli-video`) were never owned repos; they show as 100% absorbed from day one. Plan data needs an `owned_absorbs` vs `starred_inspiration` split if this becomes noisy *(found 2026-05-24)*


## Resolved

- [x] **place-time cross-layer conflict** — resolved: `place-time` is ontology-first (temporal/spatial as classification), not a mapping tool; removed from `map-suite` absorbs, kept in `ontology-align` only *(resolved 2026-05-24)*

- [x] **Path bug in embed_vba.ps1** — script deleted (defunct pipeline removed) *(resolved 2026-05-24)*
- [x] **compress variable dead in inject_datamashup()** — script deleted (defunct pipeline removed) *(resolved 2026-05-24)*
- [x] **Dead variable WithFullName in View_RepoFull M query** — script deleted (defunct pipeline removed) *(resolved 2026-05-24)*
- [x] **MarvelGraph duplicated in REPO_META** — duplicate entry removed *(resolved 2026-05-24)*
- [x] **Local-only repo whitelist duplicated** — consolidated to single `LOCAL_ONLY` set at top of file *(resolved 2026-05-24)*
- [x] **Missing pipeline step: xlsm origin undocumented** — entire Power Query pipeline removed *(resolved 2026-05-24)*
- [x] **Conflicting final outputs** — both competing pipelines removed; one script, one output *(resolved 2026-05-24)*
- [x] **No README / pipeline documentation** — replaced by `--help` text and inline usage comment *(resolved 2026-05-24)*
- [x] **All file paths hardcoded to H:\GitHub\\** — both scripts now use `Path(__file__).parent`; outputs live in the project folder *(resolved 2026-05-24)*
