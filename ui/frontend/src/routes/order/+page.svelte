<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';
  import { COLUMNS, COL_FLAGS } from '$lib/columns';

  // Per-hub ontological ordering (Tree of Knowledge layout).
  // One ordered list of repo rows. Each row has three checkboxes
  // (Gather / Analyse / Display) that act as classification only —
  // ordering is a single global ToK rank.

  let hubs = [];
  let hub = null;
  let data = null;          // GET /api/order response
  let rows = [];            // local working copy
  let compatTags = [];      // per-hub compat-tag vocabulary
  let columns = COLUMNS;

  let loading = false;
  let saving = false;
  let error = '';
  let msg = '';
  let lastSavedAt = null;
  let history = [];         // single-step undo for the last move

  // Filter: 'all' or one of the column names. With 'all', every row shows.
  // With a column name, only rows with that flag set show.
  let activeFilter = 'all';

  // Per-row Suggest state
  let suggesting = null;    // repo name currently being asked
  let suggestRationale = '';
  let suggestPropose = null; // {is_gather, is_analyse, is_display, rationale}

  // Hub-order Suggest state
  let suggestingOrder = false;
  let proposedOrder = null;  // {proposed: [{repo, position}], moves: [...], rationale_overall}
  let orderRationale = '';

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    try { hubs = await api.getHubs(); }
    catch (e) { error = e.message; }
    const fromQuery = $page.url.searchParams.get('hub');
    if (fromQuery && hubs.includes(fromQuery)) await selectHub(fromQuery);
  });

  async function selectHub(name) {
    hub = name;
    activeFilter = 'all';
    history = [];
    proposedOrder = null;
    suggestPropose = null;
    await load();
  }

  async function load() {
    if (!hub) return;
    loading = true; error = ''; msg = '';
    try {
      data = await api.getOrder($session.session_id, hub);
      rows = data.rows.map((r) => ({ ...r }));   // shallow clone for editing
      compatTags = [...(data.compat_tags_vocab || [])];
      lastSavedAt = null;
    } catch (e) { error = e.message; }
    finally { loading = false; }
  }

  // --- ordering ------------------------------------------------------------

  function move(from, to) {
    if (to < 0 || to >= rows.length) return;
    // Push the pre-move state for single-step undo.
    history = [rows.map((r) => ({ ...r }))];
    const item = rows[from];
    rows.splice(from, 1);
    rows.splice(to, 0, item);
    // Reassign contiguous positions (skip the hub repo at index 0).
    reassignPositions();
    rows = rows;
  }

  function undo() {
    if (!history.length) return;
    rows = history.pop();
    history = [];
  }

  function reassignPositions() {
    // Position 0 stays reserved for the hub repo (if present). Everything
    // else gets 0..N-1 in current order so a save always lands a clean
    // contiguous layout.
    let p = 0;
    for (const r of rows) {
      if (r.is_hub_repo) { r.position = 0; continue; }
      r.position = p++;
    }
  }

  // --- column flags --------------------------------------------------------

  function toggleFlag(row, col) {
    const key = COL_FLAGS[col];
    row[key] = !row[key];
    rows = rows;
  }

  function setFlag(row, col, val) {
    const key = COL_FLAGS[col];
    row[key] = !!val;
    rows = rows;
  }

  // --- compat tags ---------------------------------------------------------

  function toggleTag(row, tag) {
    row.compat_tags = row.compat_tags || [];
    if (row.compat_tags.includes(tag)) {
      row.compat_tags = row.compat_tags.filter((t) => t !== tag);
    } else {
      row.compat_tags = [...row.compat_tags, tag];
    }
    rows = rows;
  }

  // --- per-row Suggest -----------------------------------------------------

  async function suggestForRow(row) {
    suggesting = row.repo; suggestRationale = ''; suggestPropose = null;
    try {
      const r = await api.suggestColumn($session.session_id, hub, row.repo);
      suggestPropose = r;
    } catch (e) { error = e.message; }
    finally { suggesting = null; }
  }

  function acceptSuggest(row) {
    if (!suggestPropose) return;
    setFlag(row, 'Gather', suggestPropose.is_gather);
    setFlag(row, 'Analyse', suggestPropose.is_analyse);
    setFlag(row, 'Display', suggestPropose.is_display);
    suggestPropose = null;
  }

  // --- hub-order Suggest ---------------------------------------------------

  async function suggestOrderAll() {
    if (!hub) return;
    suggestingOrder = true; error = '';
    try {
      proposedOrder = await api.suggestOrder($session.session_id, hub);
      orderRationale = proposedOrder.rationale_overall || '';
    } catch (e) { error = e.message; }
    finally { suggestingOrder = false; }
  }

  function acceptProposedOrder() {
    if (!proposedOrder) return;
    // Build a map: repo -> new position from the LLM proposal
    const byRepo = Object.fromEntries(
      (proposedOrder.proposed || []).map((p) => [p.repo, p.position])
    );
    // Sort the local rows by the proposed position, but keep the hub repo
    // at index 0 regardless of what the LLM returned for it.
    const hubRow = rows.find((r) => r.is_hub_repo);
    const rest = rows.filter((r) => !r.is_hub_repo)
      .sort((a, b) => (byRepo[a.repo] ?? 999) - (byRepo[b.repo] ?? 999));
    rows = hubRow ? [hubRow, ...rest] : rest;
    reassignPositions();
    proposedOrder = null;
  }

  // --- filter --------------------------------------------------------------

  $: filteredRows = (() => {
    if (activeFilter === 'all') return rows;
    const key = COL_FLAGS[activeFilter];
    return rows.filter((r) => r[key]);
  })();

  function isRowFilteredOut(row) {
    if (activeFilter === 'all') return false;
    const key = COL_FLAGS[activeFilter];
    return !row[key];
  }

  // --- save ----------------------------------------------------------------

  async function save() {
    if (!hub) return;
    saving = true; error = ''; msg = '';
    try {
      // Reassign positions in the full (unfiltered) order so the saved
      // layout is always a clean 0..N-1 sequence.
      reassignPositions();
      const payload = {
        rows: rows.map((r) => ({
          repo: r.repo,
          position: r.position,
          is_gather: !!r.is_gather,
          is_analyse: !!r.is_analyse,
          is_display: !!r.is_display,
          compat_tags: r.compat_tags || [],
          feature_annotations: r.feature_annotations || [],
        })),
      };
      await api.saveOrder($session.session_id, hub, payload.rows);
      lastSavedAt = new Date();
      msg = 'Saved.';
    } catch (e) { error = e.message; }
    finally { saving = false; }
  }
</script>

<div class="page-header">
  <h1>Order</h1>
  <p class="sub">Per-hub Tree-of-Knowledge ordering. One ordered list per hub — foundational first, presentation last. Each row has three classification checkboxes (Gather / Analyse / Display); they act as filters, not slots. Drag alternatives: arrow buttons on every row.</p>
</div>

{#if error}<div class="error-msg">{error}</div>{/if}
{#if msg}<div class="ok-msg">{msg}</div>{/if}

{#if !hub}
  <div class="hub-picker">
    <h3>Choose a hub</h3>
    {#if hubs.length === 0}
      <p class="empty">No hubs yet — add one on the <a href="/hubs">Hubs</a> page first.</p>
    {:else}
      <div class="hub-grid">
        {#each hubs as h}
          <button class="hub-card" on:click={() => selectHub(h)}>
            <h4>{h}</h4>
          </button>
        {/each}
      </div>
    {/if}
  </div>
{:else}
  <div class="bar">
    <label>Hub
      <select bind:value={hub} on:change={() => selectHub(hub)}>
        {#each hubs as h}<option value={h}>{h}</option>{/each}
      </select>
    </label>
    <label>Filter
      <select bind:value={activeFilter}>
        <option value="all">all</option>
        {#each columns as c}<option value={c}>{c}</option>{/each}
      </select>
    </label>
    <button class="ghost sm" on:click={suggestOrderAll} disabled={suggestingOrder || rows.length < 2}>
      {suggestingOrder ? 'Suggesting…' : '✨ Suggest order'}
    </button>
    <button on:click={save} disabled={saving || loading}>
      {saving ? 'Saving…' : '💾 Save'}
    </button>
    <button class="ghost sm" on:click={undo} disabled={!history.length}>↶ Undo</button>
    {#if lastSavedAt}<span class="saved">Saved {lastSavedAt.toLocaleTimeString()}</span>{/if}
    <span class="spacer"></span>
    <span class="counts">
      {rows.length} repos · {rows.filter((r) => r.is_gather).length} Gather ·
      {rows.filter((r) => r.is_analyse).length} Analyse ·
      {rows.filter((r) => r.is_display).length} Display
    </span>
  </div>

  {#if loading}<p class="loading">Loading…</p>{/if}

  {#if proposedOrder}
    <div class="card propose">
      <h4>Proposed order</h4>
      {#if orderRationale}<p class="rationale">{orderRationale}</p>{/if}
      <ol class="proposed">
        {#each proposedOrder.proposed as p, i}
          <li>{p.repo}</li>
        {/each}
      </ol>
      {#if (proposedOrder.moves || []).length}
        <h5>Moves</h5>
        <ul class="moves">
          {#each proposedOrder.moves as m}
            <li><code>{m.repo}</code>: {m.from} → {m.to} — {m.rationale}</li>
          {/each}
        </ul>
      {/if}
      <div class="propose-actions">
        <button on:click={acceptProposedOrder}>Accept all</button>
        <button class="ghost" on:click={() => (proposedOrder = null)}>Discard</button>
      </div>
    </div>
  {/if}

  <div class="order-list">
    {#each rows as r, i (r.repo)}
      <div class="row" class:dim={isRowFilteredOut(r)} class:hub-row={r.is_hub_repo}>
        <div class="rank">
          {#if r.is_hub_repo}
            <span class="hub-badge" title="Hub repo — pinned to position 0">HUB</span>
          {:else}
            <span class="pos">{r.position + 1}</span>
            <div class="move-buttons">
              <button class="ghost xs" title="Move to top" on:click={() => move(i, 1)} disabled={i === 1}>⤒</button>
              <button class="ghost xs" title="Move up" on:click={() => move(i, i - 1)} disabled={i <= 1}>↑</button>
              <button class="ghost xs" title="Move down" on:click={() => move(i, i + 1)} disabled={i === rows.length - 1}>↓</button>
              <button class="ghost xs" title="Move to bottom" on:click={() => move(i, rows.length - 1)} disabled={i === rows.length - 1}>⤓</button>
            </div>
          {/if}
        </div>

        <div class="body">
          <div class="title-line">
            <span class="repo">{r.repo}</span>
            {#if r.language}<span class="lang">{r.language}</span>{/if}
            {#if r.stars}<span class="stars" title="stars on GitHub">★ {r.stars}</span>{/if}
            <span class="spacer"></span>
            <button class="ghost xs" on:click={() => suggestForRow(r)} disabled={suggesting === r.repo || r.is_hub_repo}
              title="Ask the LLM which column(s) this repo belongs in">
              {suggesting === r.repo ? '…' : '✨ Suggest'}
            </button>
          </div>

          {#if r.aim}<p class="aim">{r.aim}</p>{/if}

          <div class="cols">
            {#each columns as c}
              <label class="col" class:checked={r[COL_FLAGS[c]]}>
                <input type="checkbox" checked={r[COL_FLAGS[c]]} on:change={() => toggleFlag(r, c)} />
                {c}
              </label>
            {/each}
          </div>

          {#if compatTags.length}
            <div class="tags">
              {#each compatTags as t}
                <button class="tag" class:on={(r.compat_tags || []).includes(t)}
                  on:click={() => toggleTag(r, t)}
                  title={(r.compat_tags || []).includes(t) ? 'Remove' : 'Add'}>
                  {t}
                </button>
              {/each}
            </div>
          {/if}
        </div>

        {#if suggestPropose && suggestPropose.repo === r.repo}
          <div class="suggest-card">
            <p class="rationale">{suggestPropose.rationale}</p>
            <div class="cols">
              {#each columns as c}
                <span class="col" class:checked={suggestPropose[COL_FLAGS[c]]}>{c}</span>
              {/each}
            </div>
            <div class="propose-actions">
              <button on:click={() => acceptSuggest(r)}>Accept</button>
              <button class="ghost" on:click={() => (suggestPropose = null)}>Discard</button>
            </div>
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  .hub-picker { margin-top: 1rem; }
  .hub-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.5rem; margin-top: 0.6rem; }
  .hub-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.7rem 0.9rem; cursor: pointer; text-align: left; font-family: inherit; }
  .hub-card:hover { border-color: #4f46e5; }
  .hub-card h4 { margin: 0; font-family: monospace; }

  .bar { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; margin: 0.6rem 0 1rem; font-size: 0.85rem; }
  .bar label { display: flex; align-items: center; gap: 0.35rem; }
  .bar .spacer { flex: 1; }
  .saved { color: #16a34a; font-size: 0.78rem; }
  .counts { color: #6b7280; font-size: 0.78rem; }

  .propose { background: #faf5ff; border-color: #c4b5fd; margin-bottom: 1rem; }
  .propose h4 { margin: 0 0 0.4rem; }
  .propose .rationale { color: #4b5563; font-style: italic; margin: 0.2rem 0 0.6rem; }
  .proposed { margin: 0.2rem 0 0.6rem; padding-left: 1.2rem; font-family: monospace; font-size: 0.85rem; }
  .moves { margin: 0.2rem 0 0.6rem; padding-left: 1.2rem; font-size: 0.82rem; color: #374151; }
  .moves code { font-family: monospace; background: #f3f4f6; padding: 0 0.25rem; border-radius: 3px; }
  .propose-actions { display: flex; gap: 0.5rem; }

  .order-list { display: flex; flex-direction: column; gap: 0.4rem; }
  .row { display: flex; gap: 0.7rem; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.6rem 0.8rem; align-items: flex-start; }
  .row.hub-row { background: #f9fafb; }
  .row.dim { opacity: 0.35; }
  .rank { display: flex; flex-direction: column; align-items: center; gap: 0.3rem; min-width: 56px; }
  .pos { font-family: monospace; font-weight: 600; color: #6b7280; }
  .hub-badge { font-size: 0.7rem; font-weight: 700; background: #ddd6fe; color: #5b21b6; padding: 0.15rem 0.45rem; border-radius: 4px; }
  .move-buttons { display: flex; flex-direction: column; gap: 0.15rem; }
  button.xs { padding: 0.1rem 0.4rem; font-size: 0.78rem; line-height: 1; }

  .body { flex: 1; min-width: 0; }
  .title-line { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .title-line .spacer { flex: 1; }
  .repo { font-family: monospace; font-weight: 600; font-size: 0.95rem; }
  .lang { font-size: 0.7rem; background: #eff6ff; color: #1e40af; border-radius: 4px; padding: 0.05em 0.35em; }
  .stars { font-size: 0.75rem; color: #6b7280; }
  .aim { color: #4b5563; font-size: 0.85rem; margin: 0.25rem 0 0.5rem; }
  .cols { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .col { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.78rem; padding: 0.1rem 0.5rem; border: 1px solid #e5e7eb; border-radius: 4px; background: #fff; cursor: pointer; }
  .col.checked { background: #eef2ff; border-color: #6366f1; color: #3730a3; font-weight: 600; }
  .tags { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.4rem; }
  .tag { font-size: 0.72rem; padding: 0.1rem 0.45rem; border-radius: 12px; background: #f3f4f6; color: #4b5563; border: 1px solid transparent; cursor: pointer; }
  .tag.on { background: #ecfdf5; color: #065f46; border-color: #6ee7b7; }

  .suggest-card { flex-basis: 100%; margin-top: 0.4rem; background: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 6px; padding: 0.5rem 0.7rem; }
</style>
