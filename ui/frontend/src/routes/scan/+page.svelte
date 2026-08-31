<script>
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { session, currentScanId } from '$lib/stores';
  import { api, scanWs } from '$lib/api';
  import { SOURCE_GLYPH } from '$lib/columns';

  // ONE GitHub pull, three phases shown as they happen: your repos, your forks,
  // your stars. Then ✨ Enrich runs the LLM distill (Purpose / Domain /
  // Entities). NOTHING here clusters — clustering is its own explicit step on
  // the Cluster page. Hub is read-only, backfilled from the live plan.
  //
  // Records table is fully sortable (click a header) and carries an editable
  // Notes column — that's the human override for the LLM's purpose/domain
  // guesses, which the user wants to author themselves.

  let owned = [];          // owned repos (own forks via is_fork)
  let stars = [];          // starred repos
  let records = {};        // full_name/name -> {purpose, entities, domain}
  let hubMap = {};         // name -> hub (backfilled from the live plan)
  let notes = {};          // full_name -> note text (per session)

  let status = 'idle';     // idle | pulling | done | error  (pulling = repos streaming)
  let forkCount = 0;
  let starCount = 0;
  let starsLoading = false;  // stars load in the background after repos land
  let pullErrors = [];     // per-phase failures, surfaced (no silent swallow)
  let enrichStatus = '';   // '' | 'running' | 'done'
  let enrichMsg = '';
  let enrichStop = false;  // user pressed Stop mid-loop
  let enrichCached = 0;    // repos with a record so far
  let enrichTotal = 0;
  let enrichLog = [];      // [{repo, domain}] most-recent-first (live ticker)
  const ENRICH_BATCH = 2;  // tiny batches → ticks every few seconds (LLM ~slow)
  let errorMsg = '';
  let ws;

  // Sort state for the records table. `sortKey` picks a column; clicking the
  // same header flips `sortDir`. Default: by source then name (the natural
  // reading order — owned, then forks, then stars, alphabetic within).
  let sortKey = 'source';
  let sortDir = 'asc';
  function flipSort(k) {
    if (sortKey === k) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    else { sortKey = k; sortDir = 'asc'; }
  }
  // Visible cols → values extracted from the records_view row. Notes are kept
  // separate (mutable) but the sort reads from `r.note` so editing reorders.
  function sortValue(r, k) {
    switch (k) {
      case 'source':   return SOURCE_ORDER[r.source] ?? 99;
      case 'name':     return (r.name || '').toLowerCase();
      case 'purpose':  return (r.rec?.purpose || '').toLowerCase();
      case 'domain':   return (r.rec?.domain || '').toLowerCase();
      case 'entities': return (r.rec?.entities?.join(' ') || '').toLowerCase();
      case 'hub':      return (r.hub || '').toLowerCase();
      case 'stars':    return r.stars || 0;
      case 'note':     return (notes[r.key] || '').toLowerCase();
      case 'enriched': return r.rec?.purpose ? 1 : 0;
      default:         return '';
    }
  }
  const SOURCE_ORDER = { owned: 0, fork: 1, star: 2 };

  onMount(() => { if (!$session) goto('/'); rehydrate(); });
  onDestroy(() => { if (ws) ws.close(); });

  async function rehydrate() {
    try {
      const [scan, s, n] = await Promise.all([
        api.latestScan($session.session_id).catch(() => null),
        api.getStars().catch(() => ({ stars: [] })),
        api.getNotes($session.session_id).catch(() => ({})),
      ]);
      if (!scan?.repos?.length) return;
      owned = scan.repos;
      stars = s.stars || [];
      starCount = stars.length;
      notes = n || {};
      await loadHubs();
      refreshMeta();
      status = 'done';
    } catch (e) { /* stay idle */ }
  }

  async function loadHubs() {
    // Read-only Hub column from the live plan. No clustering, no token spend.
    const recon = await api.reconcile($session.session_id).catch(() => ({ repos: [] }));
    hubMap = {};
    for (const r of recon.repos || []) if (r.hub) hubMap[r.name] = r.hub;
    hubMap = hubMap;
  }

  async function refreshMeta() {
    // Cheap, DB-only. NO per-repo GitHub calls here.
    try {
      records = (await api.distillRecords($session.session_id).catch(() => ({}))) || {};
    } catch (e) { /* non-fatal */ }
  }

  // The GitHub pull: repos stream over the WS; forks come free (the scan writes
  // the fork table); stars load in the background after.
  function startPull() {
    status = 'pulling';
    owned = []; stars = []; hubMap = {};
    records = {}; notes = {};            // fresh pull → fresh notes (keys might disappear)
    forkCount = 0; starCount = 0; starsLoading = false;
    pullErrors = []; enrichMsg = ''; errorMsg = '';
    api.startScan($session.session_id).then(({ scan_id }) => {
      currentScanId.set(scan_id);
      ws = scanWs(
        scan_id,
        (repo) => (owned = [...owned, repo]),
        () => finishPull(),
        (msg) => { status = 'error'; errorMsg = msg; }
      );
    }).catch((e) => { status = 'error'; errorMsg = e.message; });
  }

  // Repos are in (the WS "done" fired). Flip to done IMMEDIATELY — synchronously,
  // in the same WS callback that already renders the live repo count — so the
  // page never looks frozen. Stars + hub backfill load in the background.
  function finishPull() {
    forkCount = owned.filter((r) => r.is_fork).length;
    status = 'done';
    loadStars();
    loadHubs();
    refreshMeta();
  }

  const STAR_TIMEOUT_MS = 90_000;
  function withTimeout(promise, ms, what) {
    let timer;
    return Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(new Error(`${what} timed out after ${ms / 1000}s`)),
          ms,
        );
      }),
    ]).finally(() => clearTimeout(timer));
  }

  async function loadStars() {
    starsLoading = true;
    try {
      // GitHub's starred-list is paginated (~6 pages for a large account) and the
      // token can hit the secondary rate limit mid-loop; without a timeout the
      // "pulling stars…" spinner would spin until the tab is closed. Race it so
      // it ALWAYS settles; a timeout is a recoverable error, not a hang.
      const res = await withTimeout(
        api.refreshStars($session.session_id),
        STAR_TIMEOUT_MS, 'Stars refresh',
      );
      starCount = res.count ?? 0;
      const get = await withTimeout(api.getStars(), STAR_TIMEOUT_MS, 'Stars lookup');
      stars = (get.stars) || [];
    } catch (e) {
      pullErrors = [...pullErrors, `Stars pull failed: ${e.message}`];
    } finally {
      starsLoading = false;
    }
  }

  // ✨ Enrich — LLM read of each repo (Purpose / Domain / Entities), looped in
  // SMALL batches so it's visibly working: every few seconds the count ticks up
  // and the just-finished repos scroll past with their domain. Cached +
  // resumable: Stop → Enrich picks up exactly where it left off. No clustering.
  async function enrich() {
    enrichStatus = 'running'; enrichStop = false; enrichLog = [];
    enrichMsg = 'Starting…';
    let batchNo = 0;
    try {
      while (!enrichStop) {
        batchNo += 1;
        const d = await api.distill($session.session_id, ENRICH_BATCH);
        enrichTotal = d.total;
        enrichCached = d.cached;
        for (const r of (d.done_repos || [])) {
          const short = (r.repo || '').split('/').pop();
          enrichLog = [{ repo: short, domain: r.domain }, ...enrichLog].slice(0, 15);
        }
        await refreshMeta();                                  // table fills live too
        if (d.remaining <= 0) {
          enrichMsg = `✓ Enriched all ${d.total} repos.`; break;
        }
        if (d.stop_reason) {
          enrichMsg = `Paused at ${d.cached}/${d.total} — ${d.stop_reason}. Press Enrich to resume.`;
          break;
        }
        enrichMsg = `Enriching… ${d.cached}/${d.total} (batch ${batchNo}, +${d.done})`;
        await new Promise((r) => setTimeout(r, 250));         // gentle between batches
      }
      if (enrichStop) enrichMsg = `Stopped at ${enrichCached}/${enrichTotal} — resume with Enrich.`;
    } catch (e) { enrichMsg = `Enrich error: ${e.message}`; }
    finally { enrichStatus = 'done'; }
  }

  function stopEnrich() { enrichStop = true; }

  $: repoCount = owned.filter((r) => !r.is_fork).length;
  $: forkFromOwned = owned.filter((r) => r.is_fork).length;

  $: records_view = [
    ...owned.map((r) => {
      const fn = r.full_name || r.name;
      return {
        key: fn, name: r.name, source: r.is_fork ? 'fork' : 'owned',
        hub: hubMap[r.name] || r.mid_cat || '', stars: r.stars,
        readme_url: r.url ? `https://github.com/${fn}/blob/main/README.md` : '',
        repo_url: r.url,
        rec: records[fn] || records[r.name] || null,
        note: notes[fn] || '',
        issue: null,
      };
    }),
    ...stars.map((r) => {
      const fn = r.full_name;
      return {
        key: fn, name: r.name, source: 'star',
        hub: '', stars: r.stars,
        readme_url: fn ? `https://github.com/${fn}/blob/main/README.md` : '',
        repo_url: fn ? `https://github.com/${fn}` : '',
        rec: records[fn] || null,
        note: notes[fn] || '',
        issue: null,
      };
    }),
  ];

  // Sort a fresh copy on every render so editing a note reorders live. Cheap
  // enough — table size is repo count, never thousands.
  $: records_sorted = (() => {
    const rows = [...records_view];
    rows.sort((a, b) => {
      const va = sortValue(a, sortKey), vb = sortValue(b, sortKey);
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ?  1 : -1;
      // stable tiebreaker: name
      const na = (a.name || '').toLowerCase(), nb = (b.name || '').toLowerCase();
      return na < nb ? -1 : na > nb ? 1 : 0;
    });
    return rows;
  })();

  $: counts = records_view.reduce((a, r) => (a[r.source] = (a[r.source] || 0) + 1, a), {});
  $: noteCount = Object.values(notes).filter((n) => (n || '').trim()).length;

  // Debounce the per-row save so typing doesn't fire one POST per keystroke.
  let noteTimers = {};
  let noteSaving = {};
  function onNoteInput(key, value) {
    notes = { ...notes, [key]: value };
    clearTimeout(noteTimers[key]);
    noteTimers[key] = setTimeout(() => saveNote(key, value), 600);
  }
  async function saveNote(key, value) {
    noteSaving = { ...noteSaving, [key]: true };
    try {
      await api.saveNote($session.session_id, key, value);
    } catch (e) {
      pullErrors = [...pullErrors, `Notes save failed for ${key}: ${e.message}`];
    } finally {
      noteSaving = { ...noteSaving, [key]: false };
    }
  }
</script>

<div class="page-header">
  <h1>GitHub Pull</h1>
  <p class="sub">
    One pull: <strong>your repos &amp; forks</strong> (streamed), then
    <strong>your stars</strong> in the background. Then <strong>✨ Enrich</strong>
    distills <em>Purpose · Domain · Entities</em>. Clustering is a separate step.
  </p>
</div>

{#if status === 'idle'}
  <button on:click={startPull}>⤓ Pull from GitHub</button>
{:else if status === 'pulling'}
  <div class="info-msg"><span class="spinner">⟳</span> Pulling your repos &amp; forks… ({owned.length})</div>
{:else if status === 'done'}
  <div class="ok-msg">
    Pulled — {repoCount} repos · {forkFromOwned || forkCount} forks ·
    {#if starsLoading}<span class="spinner">⟳</span> pulling stars…{:else}{stars.length} stars.{/if}
  </div>
  {#each pullErrors as e}<div class="error-msg" style="margin-top:0.4rem">{e}</div>{/each}
  <div class="actions-row">
    <button on:click={startPull} class="secondary">⤓ Re-pull</button>
    {#if enrichStatus === 'running'}
      <button on:click={stopEnrich} class="primary">⏸ Stop enriching</button>
    {:else}
      <button on:click={enrich} class="primary">✨ Enrich</button>
    {/if}
    </div>
  {#if enrichMsg || enrichLog.length}
    <div class="enrich-panel">
      <div class="enrich-head">
        {#if enrichStatus === 'running'}<span class="spinner">⟳</span>{/if}
        <span>{enrichMsg}</span>
      </div>
      {#if enrichTotal}
        <div class="ebar"><div class="efill" style="width:{enrichCached / enrichTotal * 100}%"></div></div>
      {/if}
      {#if enrichLog.length}
        <ul class="enrich-log">
          {#each enrichLog as e (e.repo)}
            <li><span class="ok">✓</span> <b>{e.repo}</b> <span class="arrow">→</span> {e.domain || '—'}</li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
{:else}
  <div class="error-msg">{errorMsg}</div>
  <button on:click={startPull} class="secondary" style="margin-top: 0.5rem">Retry</button>
{/if}

{#if records_view.length > 0}
  <div class="section">
    <div class="section-head">
      <h2>Records ({records_view.length})</h2>
      <span class="muted-small">click any column header to sort</span>
      <button class="secondary sm" type="button" on:click={() => goto('/scan/print')}>Print preview</button>
    </div>
    <p class="sub">Hub is read-only here — it fills in once you form hubs on the Cluster step. The <b>Notes</b> column is yours to author; it persists per session and isn't read by the LLM.</p>
    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.6rem;">
      <span class="badge">{SOURCE_GLYPH.owned} owned: {counts.owned || 0}</span>
      <span class="badge">{SOURCE_GLYPH.fork} forks: {counts.fork || 0}</span>
      <span class="badge">{SOURCE_GLYPH.star} stars: {counts.star || 0}</span>
      <span class="badge" style="background:#e6effa;color:#1e40af">enriched: {Object.keys(records).length}</span>
      <span class="badge" style="background:#fef3c7;color:#92400e">notes: {noteCount}</span>
    </div>
    <table class="records">
      <thead>
        <tr>
          <th class="sortable" on:click={() => flipSort('source')} title="Click to sort by source">
            <span class="caret">{sortKey === 'source' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
          <th class="sortable" on:click={() => flipSort('name')} title="Click to sort by repo name">
            Repo <span class="caret">{sortKey === 'name' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
          <th class="sortable" on:click={() => flipSort('purpose')} title="Click to sort by purpose">
            Purpose <span class="caret">{sortKey === 'purpose' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
          <th class="sortable" on:click={() => flipSort('domain')} title="Click to sort by domain">
            Domain <span class="caret">{sortKey === 'domain' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
          <th class="sortable" on:click={() => flipSort('entities')} title="Click to sort by entities">
            Entities <span class="caret">{sortKey === 'entities' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
          <th class="sortable" on:click={() => flipSort('hub')} title="Click to sort by hub">
            Hub <span class="caret">{sortKey === 'hub' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
          <th class="sortable num" on:click={() => flipSort('stars')} title="Click to sort by stars">
            ★ <span class="caret">{sortKey === 'stars' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
          <th class="sortable note-col" on:click={() => flipSort('note')} title="Click to sort by notes">
            Notes <span class="caret">{sortKey === 'note' ? (sortDir === 'asc' ? '▴' : '▾') : '⇅'}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each records_sorted as r (r.key)}
          <tr class:warn={r.issue}>
            <td class="src" title={r.source}>{SOURCE_GLYPH[r.source]}</td>
            <td class="name">
              {#if r.repo_url}
                <a href={r.repo_url} target="_blank" rel="noopener">{r.name}</a>
              {:else}{r.name}{/if}
              {#if r.readme_url}
                <a class="readme" href={r.readme_url} target="_blank" rel="noopener" title="README on GitHub">README</a>
              {/if}
            </td>
            <td class="purpose">{r.rec?.purpose || '—'}</td>
            <td class="domain">{#if r.rec?.domain}<span class="domain-pill">{r.rec.domain}</span>{:else}—{/if}</td>
            <td class="entities">{r.rec?.entities?.join(' · ') || '—'}</td>
            <td class="hub">{r.hub || ''}</td>
            <td class="stars">{r.stars || ''}</td>
            <td class="note-cell">
              <input class="note-input" type="text"
                placeholder={r.rec?.purpose ? 'correct / expand on purpose…' : 'why this is here…'}
                value={notes[r.key] || ''}
                on:input={(e) => onNoteInput(r.key, e.target.value)} />
              {#if noteSaving[r.key]}<span class="note-saving" title="Saving…">⟳</span>{/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  table.records { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
  table.records th { text-align: left; color: #6b7280; font-weight: 600; border-bottom: 2px solid #e5e7eb; padding: 0.3rem 0.5rem; }
  table.records th.sortable { cursor: pointer; user-select: none; }
  table.records th.sortable:hover { background: #f1f5f9; color: #1e293b; }
  table.records th .caret { color: var(--quiet-text); font-size: 0.7rem; margin-left: 0.15rem; font-weight: 400; }
  table.records th.num { text-align: right; }
  table.records th.note-col { width: 22rem; min-width: 14rem; }
  table.records td { border-bottom: 1px solid #f1f5f9; padding: 0.28rem 0.5rem; vertical-align: top; }
  table.records tr:hover td { background: #f8fafc; }
  tr.warn td { background: #fff7ed; }
  tr.warn:hover td { background: #ffedd5; }
  td.src { text-align: center; }
  td.name a { color: #1e293b; font-family: var(--mono); }
  td.name a.readme { font-size: 0.66rem; color: #6b7280; margin-left: 0.3rem; }
  td.purpose { color: #1e293b; max-width: 280px; }
  td.domain .domain-pill { background: #e6effa; color: #1e40af; border-radius: 4px; padding: 0.1em 0.45em; font-size: 0.72rem; }
  td.entities { color: #6b7280; max-width: 220px; }
  td.hub { color: #6b7280; }
  td.stars { color: var(--quiet-text); text-align: right; }
  td.note-cell { padding: 0.18rem 0.5rem; }
  td.note-cell .note-input {
    width: 100%; box-sizing: border-box; padding: 0.25rem 0.4rem;
    border: 1px solid #e5e7eb; border-radius: 4px; font: inherit;
    background: #fff; color: #1e293b;
  }
  td.note-cell .note-input:focus { outline: none; border-color: #1e40af; box-shadow: 0 0 0 2px #e6effa; }
  td.note-cell .note-input::placeholder { color: #cbd5e1; }
  td.note-cell .note-saving { font-size: 0.7rem; color: #6b7280; margin-left: 0.3rem; }
  .muted-small { color: var(--quiet-text); font-size: 0.74rem; font-weight: 400; margin-left: 0.5rem; }
  ul.warnlist { list-style: none; padding: 0; margin: 0; }
  ul.warnlist li { padding: 0.35rem 0.5rem; border-bottom: 1px solid #f1f5f9; display: flex; gap: 0.6rem; align-items: baseline; }
  .warn-reason { color: #b45309; font-size: 0.8rem; }

  .enrich-panel { margin-top: 0.6rem; padding: 0.6rem 0.8rem; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; }
  .enrich-head { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: #1e293b; }
  .ebar { height: 6px; background: #e5e7eb; border-radius: 3px; overflow: hidden; margin: 0.5rem 0; }
  .efill { height: 100%; background: #1e40af; transition: width 0.25s; }
  .enrich-log { list-style: none; margin: 0.3rem 0 0; padding: 0; font-size: 0.78rem; max-height: 200px; overflow-y: auto; }
  .enrich-log li { padding: 0.12rem 0; color: #475569; }
  .enrich-log b { font-family: var(--mono); color: #1e293b; }
  .enrich-log .ok { color: #16a34a; }
  .enrich-log .arrow { color: var(--quiet-text); }
</style>
