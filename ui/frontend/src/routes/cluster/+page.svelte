<script>
  import { onMount, onDestroy } from 'svelte';
  import { browser } from '$app/environment';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';
  import { SOURCE_GLYPH } from '$lib/columns';

  // Layout: each cluster is a vertical column. Within a column, owned sits at
  // the top, then forks, then stars. Cells are rectangles big enough to read;
  // they never overlap (column does the spacing). The d3 force simulation is
  // gone — placement is deterministic.

  let data = null;
  let clusters = [];        // [{suggested_name, members, size, lx, ly}]
  let orphans = [];         // [{repo, ...}] — repo not in any cluster this pass
  let loading = true;
  let errorMsg = '';
  let msg = '';
  let k = 8;                // cluster count — fed to "Cluster" button only
  let busy = false;
  let hoveredId = null;
  let selected = new Set();   // hover-to-select cluster picker
  let width = 1200;
  const HEADER_H = 30;
  const CELL_W = 168;
  const CELL_H = 56;
  const CELL_GAP = 6;
  const COL_GAP = 24;
  const PADDING = 28;

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load(recompute = false, opts = {}) {
    loading = true; errorMsg = '';
    try {
      data = await api.getClusters($session.session_id, {
        k, recompute, savedOnly: !recompute,
        anchors: opts.anchors ?? false,
      });
      if (data.k) k = data.k;
      build(data.clusters || [], opts.anchors ? data.clusters || [] : []);
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  }

  // Build the layout. For an anchored pass the orphans surface separately so
  // the sidebar can list them.
  function normalise(m) {
    return {
      repo: m.repo || m.name || m.full_name,
      source: m.source || 'owned',
      language: m.language || '',
      stars: m.stars || 0,
      domain: m.domain || '',
      entities: m.entities || [],
      aim: m.aim || m.description || '',
      purpose: m.purpose || '',
    };
  }

  function build(allClusters, _anchorMember) {
    clusters = allClusters.map((c, idx) => {
      const all = (c.members || []).map(normalise);
      const owned = all.filter((m) => m.source === 'owned');
      const forks = all.filter((m) => m.source === 'fork');
      const stars = all.filter((m) => m.source === 'star');
      return {
        index: idx,
        suggested_name: c.suggested_name,
        suggested_description: c.suggested_description,
        anchored_to: c.anchored_to || null,
        owned, forks, stars,
        size: owned.length + forks.length + stars.length,
      };
    });
    orphans = (data.orphans_returned || []).map(normalise);
    placeColumns();
  }

  // Deterministic column placement — width comes from the page container.
  function placeColumns() {
    const totalW = Math.max(width, PADDING * 2 + clusters.length * (CELL_W + COL_GAP));
    clusters = clusters.map((c, i) => {
      const cx = PADDING + i * (CELL_W + COL_GAP) + CELL_W / 2;
      return { ...c, lx: cx, ly: HEADER_H };
    });
    // Recompute stage height from the tallest column.
    heightForLayout = HEADER_H + PADDING + maxColRows() * (CELL_H + CELL_GAP);
  }
  let heightForLayout = 600;

  function maxColRows() {
    return clusters.reduce((m, c) => Math.max(m, c.owned.length + c.forks.length + c.stars.length), 1);
  }

  // Position a member within its cluster column by source-order (owned top).
  function cellPos(c, source, row) {
    const ownedN = c.owned.length, forksN = c.forks.length;
    const y = HEADER_H + PADDING + row * (CELL_H + CELL_GAP) + CELL_H / 2;
    const x = c.lx;
    return { x, y };
  }

  function memberRow(c, m) {
    if (m.source === 'fork') return c.owned.length + c.forks.indexOf(m);
    if (m.source === 'star') return c.owned.length + c.forks.length + c.stars.indexOf(m);
    return c.owned.indexOf(m);                 // owned (default)
  }

  function rect(c, source, row) {
    const { x, y } = cellPos(c, source, row);
    return `left:${x - CELL_W / 2}px; top:${y - CELL_H / 2}px; width:${CELL_W}px; height:${CELL_H}px;`;
  }

  // ── actions ─────────────────────────────────────────────────────────────
  async function doCluster(scratch) {
    busy = true; errorMsg = '';
    try {
      data = null; await load(true, { anchors: !scratch });
      msg = scratch ? 'Clustered from scratch.' : 'Placed orphans into existing clusters.';
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  async function promoteToHub(member) {
    const name = member.repo;
    busy = true; errorMsg = '';
    try {
      const col = clusters.find((c) => c.owned.includes(member)
                              || c.forks.includes(member)
                              || c.stars.includes(member));
      const members = col ? [
        ...col.owned.map((m) => m.repo),
        ...col.forks.map((m) => m.repo),
        ...col.stars.map((m) => m.repo),
      ] : [member.repo];
      await api.formHub($session.session_id, {
        hub_name: name, description: col?.suggested_description || '',
        boundary: col?.suggested_description || '',
        members, promote: name,
      });
      msg = `Promoted ${name}.`;
      await load(false);
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  // Remove a member from its current cluster → it joins the orphan sidebar.
  // The forbid list is updated server-side to mark this cluster as off-limits
  // for the next re-cluster pass; reassigning the repo into a cluster wipes
  // the forbid entry.
  async function removeFromCluster(member, cluster) {
    busy = true; errorMsg = '';
    try {
      await api.setVerdict(member.repo, 'orphan');
      await api.forbidRepo(member.repo, cluster.suggested_name);
      // Reflect locally so the canvas + sidebar update without a re-fetch.
      clusters = clusters.map((c) => {
        if (c.index !== cluster.index) return c;
        return {
          ...c,
          owned: c.owned.filter((m) => m !== member),
          forks: c.forks.filter((m) => m !== member),
          stars: c.stars.filter((m) => m !== member),
          size: c.size - 1,
        };
      }).filter((c) => c.size > 0);
      orphans = [...orphans, { ...member }];
      msg = `${member.repo} moved to orphans — won't re-cluster into ${cluster.suggested_name}.`;
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  async function assignOrphanToCluster(orphan, clusterLabel) {
    if (!clusterLabel) return;                     // "(unassigned)" — leave orphan alone
    busy = true; errorMsg = '';
    try {
      const col = clusters.find((c) => c.suggested_name === clusterLabel);
      if (!col) return;
      await api.clearForbids(orphan.repo);          // placement wipes forbids
      const tag = clusterLabel.startsWith('★ ')
        ? 'owned' : (col.stars.find((m) => m.repo === orphan.repo) ? 'star'
                    : col.forks.find((m) => m.repo === orphan.repo) ? 'fork' : 'owned');
      clusters = clusters.map((c) => {
        if (c.suggested_name !== clusterLabel) return c;
        return { ...c, [tag === 'owned' ? 'owned' : tag]: [...c[tag], orphan], size: c.size + 1 };
      }).filter((c) => c.size > 0);
      orphans = orphans.filter((o) => o !== orphan);
      msg = `${orphan.repo} → ${clusterLabel}.`;
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  // ── helpers ─────────────────────────────────────────────────────────────
  $: totalCount = clusters.reduce((n, c) => n + c.size, 0) + orphans.length;

  function borderKey(source) {
    return source === 'fork' ? 'F' : source === 'star' ? 'S' : 'O';
  }
</script>

<svelte:window bind:innerWidth={width} />

<div class="page-header">
  <h1>Cluster</h1>
  <p class="sub">
    Prime cluster, then drop orphans into the columns you've already laid out.
    Hover a card to promote it (becomes the hub) or remove it (joins the orphan
    sidebar). Names and ordering aren't curated — they emerge from the embedding.
  </p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if msg}<div class="ok-msg" style="margin-top:0.6rem">{msg}</div>{/if}
{#if loading}<p class="loading">Working…</p>{/if}

{#if !loading && data && !data.available}
  <div class="info-msg" style="margin-top:1rem">
    {#if data.saved === false}
      Not clustered yet. <button class="ghost sm" on:click={() => doCluster(true)}>🧩 Cluster now</button>
    {:else}
      {data.reason} <a href="/setup">Open Setup →</a>
    {/if}
  </div>
{/if}

{#if !loading && data && data.available}
  <div class="toolbar">
    <div class="toolbar-stats">
      <b>{clusters.length}</b> clusters · <b>{totalCount}</b> repos
      {#if data.orphans_returned?.length}
        · <span class="stat-orphans">{orphans.length} orphans</span>
      {/if}
    </div>
    <label class="k-in">
      # clusters
      <input type="number" min="2" max="30" bind:value={k} />
    </label>
    <button class="primary" disabled={busy} on:click={() => doCluster(true)} title="Fresh k-means pass over the whole free pool">
      Cluster
    </button>
    <button class="primary soft" disabled={busy} on:click={() => doCluster(false)}
      title="Snap the remaining orphans into the existing columns; one new theme can crystallise if 60+ remain">
      Cluster orphans
    </button>
    {#if data.saved}<span class="saved-pill">saved</span>{/if}
  </div>

  <div class="layout">
    <aside class="orphan-bar">
      <div class="orphan-head">
        <b>Orphans</b>
        <span class="hint">{orphans.length}</span>
      </div>
      {#if orphans.length === 0}
        <p class="muted small">None left — every repo is in a column.</p>
      {:else}
        {#each orphans as o (o.repo)}
          <div class="orphan-row border-{borderKey(o.source)}" on:mouseenter={() => (hoveredId = o.repo)} on:mouseleave={() => (hoveredId = null)}>
            <span class="orphan-name">{o.repo}</span>
            <select class="orphan-pick"
              on:change={(e) => assignOrphanToCluster(o, e.target.value)}
              disabled={busy}>
              <option value="">(keep orphan)</option>
              {#each clusters as c}
                <option value={c.suggested_name}>→ {c.suggested_name}</option>
              {/each}
            </select>
          </div>
        {/each}
      {/if}
    </aside>

    <div class="canvas">
      {#if clusters.length === 0}
        <p class="empty">No clusters remaining — every orphan is in the sidebar.</p>
      {:else}
        <div class="stage" bind:clientWidth={width} style="height:{heightForLayout + PADDING}px">
          {#each clusters as c (c.index)}
            <div class="col-label" style="left:{c.lx}px;">{c.suggested_name}</div>
            <div class="col-meta" style="left:{c.lx}px;">
              <span class="col-summary">⛁ {c.suggested_description || ''}</span>
              {#if c.anchored_to}
                <span class="anchor-pill">★ {c.anchored_to}</span>
              {/if}
            </div>
            {#each c.owned as m (m.repo)}
              <div class="cell border-O"
                style={rect(c, 'owned', c.owned.indexOf(m))}
                on:mouseenter={() => (hoveredId = m.repo)}
                on:mouseleave={() => (hoveredId = null)}
                role="button" tabindex="0">
                <div class="cell-title">{m.repo}</div>
                <div class="cell-sub">
                  <span class="src-tag">{SOURCE_GLYPH[m.source] || SOURCE_GLYPH.owned}</span>
                  {#if m.language}<span class="lang">{m.language}</span>{/if}
                  {#if m.stars}<span>★ {m.stars}</span>{/if}
                </div>
                {#if hoveredId === m.repo}
                  <div class="cell-actions">
                    <button disabled={busy} on:click={() => promoteToHub(m)}>★ Promote</button>
                    <button disabled={busy} class="remove"
                      on:click={() => removeFromCluster(m, c)}>✕ Remove</button>
                  </div>
                {/if}
              </div>
            {/each}
            {#each c.forks as m (m.repo)}
              <div class="cell border-F"
                style={rect(c, 'fork', c.owned.length + c.forks.indexOf(m))}
                on:mouseenter={() => (hoveredId = m.repo)}
                on:mouseleave={() => (hoveredId = null)}
                role="button" tabindex="0">
                <div class="cell-title">{m.repo}</div>
                <div class="cell-sub">
                  <span class="src-tag">{SOURCE_GLYPH.fork}</span>
                  {#if m.language}<span class="lang">{m.language}</span>{/if}
                  {#if m.stars}<span>★ {m.stars}</span>{/if}
                </div>
                {#if hoveredId === m.repo}
                  <div class="cell-actions">
                    <button disabled={busy} on:click={() => promoteToHub(m)}>★ Promote</button>
                    <button disabled={busy} class="remove"
                      on:click={() => removeFromCluster(m, c)}>✕ Remove</button>
                  </div>
                {/if}
              </div>
            {/each}
            {#each c.stars as m (m.repo)}
              <div class="cell border-S"
                style={rect(c, 'star', c.owned.length + c.forks.length + c.stars.indexOf(m))}
                on:mouseenter={() => (hoveredId = m.repo)}
                on:mouseleave={() => (hoveredId = null)}
                role="button" tabindex="0">
                <div class="cell-title">{m.repo}</div>
                <div class="cell-sub">
                  <span class="src-tag">{SOURCE_GLYPH.star}</span>
                  {#if m.language}<span class="lang">{m.language}</span>{/if}
                  {#if m.stars}<span>★ {m.stars}</span>{/if}
                </div>
                {#if hoveredId === m.repo}
                  <div class="cell-actions">
                    <button disabled={busy} on:click={() => promoteToHub(m)}>★ Promote</button>
                    <button disabled={busy} class="remove"
                      on:click={() => removeFromCluster(m, c)}>✕ Remove</button>
                  </div>
                {/if}
              </div>
            {/each}
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<script context="module">
  function borderKey(source) {
    return source === 'fork' ? 'F' : source === 'star' ? 'S' : 'O';
  }
</script>

<!-- The "borderKey" helper above isn't a context module — kept in the live
     script so the template can call it directly. -->

<style>
  .toolbar { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap;
    padding: 0.6rem 0.8rem; background: #f8fafc; border: 1px solid #e5e7eb;
    border-radius: 8px; margin-top: 1rem; }
  .toolbar-stats { color: #4b5563; font-size: 0.88rem; margin-right: auto; }
  .stat-orphans { color: #b45309; font-weight: 600; }
  .k-in { display: flex; gap: 0.4rem; align-items: center; font-size: 0.84rem; color: #4b5563; }
  .k-in input { width: 64px; padding: 0.28rem 0.4rem; border: 1px solid #d1d5db; border-radius: 5px; }

  .primary { background: #4f46e5; color: #fff; border: none; border-radius: 6px;
    padding: 0.4rem 0.85rem; font-size: 0.86rem; font-weight: 600; cursor: pointer; }
  .primary.soft { background: #6366f1; }
  .primary:disabled { opacity: 0.5; cursor: not-allowed; }

  .saved-pill { font-size: 0.74rem; background: #ecfdf5; color: #047857;
    border: 1px solid #a7f3d0; border-radius: 4px; padding: 0.1rem 0.55rem; }

  .layout { display: grid; grid-template-columns: 280px 1fr; gap: 1rem;
    margin-top: 0.7rem; }
  .orphan-bar { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 0.65rem 0.75rem; height: fit-content; position: sticky; top: 0.5rem;
    max-height: calc(100vh - 1rem); overflow-y: auto; }
  .orphan-head { display: flex; align-items: baseline; justify-content: space-between;
    margin-bottom: 0.5rem; padding-bottom: 0.4rem; border-bottom: 1px solid #e5e7eb; }
  .orphan-head .hint { color: #6b7280; font-size: 0.84rem; }
  .orphan-row { display: flex; align-items: center; gap: 0.35rem; padding: 0.32rem 0;
    border-left: 3px solid transparent; padding-left: 0.35rem; }
  .orphan-row.border-O { border-left-color: #111827; }
  .orphan-row.border-F { border-left-color: #d1d5db; }
  .orphan-row.border-S { border-left-color: #facc15; }
  .orphan-name { font-family: monospace; font-size: 0.78rem; color: #111827;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .orphan-pick { font-size: 0.74rem; padding: 0.15rem 0.25rem; border: 1px solid #d1d5db;
    border-radius: 4px; max-width: 110px; }

  .stage { position: relative; border: 1px solid #e5e7eb; border-radius: 10px;
    background: radial-gradient(circle at 1px 1px, #f1f5f9 1px, transparent 0) 0 0 / 22px 22px;
    overflow-x: auto; }
  .col-label { position: absolute; top: 4px; transform: translateX(-50%);
    font-size: 0.92rem; font-weight: 800; color: #4338ca; text-transform: uppercase;
    letter-spacing: 0.04em; white-space: nowrap; }
  .col-meta { position: absolute; top: 26px; transform: translateX(-50%);
    font-size: 0.74rem; color: #6b7280; max-width: 168px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; display: flex; gap: 0.35rem; }
  .anchor-pill { background: #fef3c7; color: #92400e; font-weight: 700; padding: 0.05em 0.4em;
    border-radius: 4px; font-size: 0.72rem; }

  .cell { position: absolute; border-radius: 6px; padding: 0.4rem 0.5rem;
    background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.08); cursor: default;
    overflow: hidden; display: flex; flex-direction: column; gap: 0.18rem; }
  .cell.border-O { border: 2px solid #111827; }
  .cell.border-F { border: 2px solid #d1d5db; }
  .cell.border-S { border: 2px solid #facc15; }
  .cell-title { font-family: monospace; font-size: 0.78rem; font-weight: 600;
    color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cell-sub { display: flex; gap: 0.35rem; align-items: center; font-size: 0.7rem;
    color: #4b5563; }
  .src-tag { font-family: monospace; }
  .lang { background: #eff6ff; color: #1e40af; padding: 0 0.3em; border-radius: 3px; }
  .cell-actions { position: absolute; inset: 0; background: rgba(255,255,255,0.92);
    display: flex; gap: 0.4rem; align-items: center; justify-content: center; }
  .cell-actions button { font-size: 0.74rem; padding: 0.3rem 0.6rem; border-radius: 5px;
    border: 1px solid #4f46e5; color: #4f46e5; background: #fff; cursor: pointer;
    font-weight: 600; }
  .cell-actions button.remove { border-color: #d1d5db; color: #6b7280; }
  .cell-actions button.remove:hover { border-color: #dc2626; color: #dc2626; }
  .cell-actions button:disabled { opacity: 0.5; }

  .muted { color: #9ca3af; }
  .small { font-size: 0.78rem; }
</style>
