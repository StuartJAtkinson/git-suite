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
  let k = 20;               // cluster count — fed to "Cluster" button only. Higher = more granular columns; the user can drop it for broader hubs.
  let coherence = 0.40;     // avg member→centroid cosine floor; below this a group falls to orphans. Prime pass uses 0.20 (let clusters emerge); orphan pass uses this value (snap to existing themes).
  let busy = false;
  let hoveredId = null;
  let selected = new Set();   // hover-to-select cluster picker
  let width = 1200;
  const HEADER_H = 30;
  const CELL_W = 420;    // ~2.5× — names + 4-line description fit comfortably
  const CELL_H = 96;     // taller — accommodates up-to-4 lines of description
  const CELL_GAP = 6;
  const COL_GAP = 24;
  const PADDING = 28;
  const MAX_ROWS_BEFORE_SCROLL = 50;     // per-column internal scroll cap

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load(recompute = false, opts = {}) {
    loading = true; errorMsg = '';
    try {
      // After any mutation the cache was invalidated (see _invalidate_all_clusters
      // / _invalidate in the backend routers); savedOnly would just surface a
      // stale "not clustered yet" banner. Pass savedOnly=false on no-recompute
      // too so the server falls through to a cheap re-derive from plan_store
      // (embeddings stay cached, only k-means re-runs).
      const forceRederive = opts.forceRederive ?? false;
      data = await api.getClusters($session.session_id, {
        k, recompute,
        savedOnly: !recompute && !forceRederive,
        anchors: opts.anchors ?? false,
        coherenceFloor: coherence,
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
      full_name: m.full_name || m.repo || m.name || '',
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

  // Stack columns vertically: each cluster is a flex-column with its own
  // scroll once it exceeds MAX_ROWS_BEFORE_SCROLL rows. The canvas flows
  // left-to-right by column; no absolute positioning, no per-cell math.
  function placeColumns() {
    // No-op placeholder — columns now self-size via CSS flex.
  }

  // Computed once per cluster render: how many rows tall the column needs
  // to be before its inner scroll takes over.
  function colMaxHeight() {
    return MAX_ROWS_BEFORE_SCROLL * (CELL_H + CELL_GAP) + PADDING;
  }

  // ── actions ─────────────────────────────────────────────────────────────
  async function doCluster(scratch) {
    busy = true; errorMsg = '';
    try {
      data = null; await load(true, { anchors: !scratch });
      msg = `${clusters.length} clusters · ${orphans.length} orphans (tightness ${coherence.toFixed(2)})`;
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  async function doThemes() {
    busy = true; errorMsg = '';
    try {
      data = null;
      data = await api.getClusters($session.session_id, {
        recompute: true, savedOnly: false, mode: 'themes',
      });
      build(data.clusters || [], []);
      msg = `${clusters.length} themes (LLM) · ${orphans.length} orphans`;
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  async function resetClusters() {
    if (!confirm('Forget the current clustering? Everything moves back to the orphan sidebar — hubs stay intact.')) return;
    busy = true; errorMsg = '';
    try {
      await api.resetClusters($session.session_id);
      data = null;
      await load(false);
      msg = 'Clustering reset — all repos are in the orphan sidebar.';
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
      await load(false, { forceRederive: true });
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
      // Snapshot is now stale (forbid entry dropped, plan verdict changed) —
      // force a re-derive on next load.
      await load(false, { forceRederive: true });
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  async function assignOrphanToCluster(orphan, clusterLabel) {
    if (!clusterLabel) return;                     // "(keep orphan)" — no-op
    busy = true; errorMsg = '';
    try {
      const col = clusters.find((c) => c.suggested_name === clusterLabel);
      if (!col) return;
      // Persist: clear forbids, then absorb into the target hub. Using form()
      // means the placement survives a reload (plan_store is the source of
      // truth); the local mirror just keeps the canvas responsive.
      await api.clearForbids(orphan.repo);
      const members = [
        ...col.owned.map((m) => m.repo),
        ...col.forks.map((m) => m.repo),
        ...col.stars.map((m) => m.repo),
        orphan.repo,
      ];
      await api.formHub($session.session_id, {
        hub_name: col.suggested_name,
        description: col.suggested_description || '',
        boundary: col.suggested_description || '',
        members,
      });
      clusters = clusters.map((c) => {
        if (c.suggested_name !== clusterLabel) return c;
        return { ...c, owned: [...c.owned, orphan], size: c.size + 1 };
      });
      orphans = orphans.filter((o) => o !== orphan);
      msg = `${orphan.repo} → ${clusterLabel}.`;
      // Snapshot is stale (absorb verdict written, forbids cleared) — re-derive.
      await load(false, { forceRederive: true });
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  // ── helpers ─────────────────────────────────────────────────────────────
  $: totalCount = clusters.reduce((n, c) => n + c.size, 0) + orphans.length;

  function borderKey(source) {
    return source === 'fork' ? 'F' : source === 'star' ? 'S' : 'O';
  }

  // Manual assessment link. Owned/fork → repo; star → the starrer's profile
  // (no repo page exists for a starred item). `m.full_name` is the GitHub
  // "<owner>/<name>" string when the scan stored it; fall back to owner/repo
  // if only the bare name is available.
  function ghUrl(m) {
    const fn = m.full_name || '';
    const repo = fn.includes('/') ? fn : '';
    if (m.source === 'star') {
      const owner = fn.split('/')[0] || '';
      return owner ? `https://github.com/${owner}` : 'https://github.com';
    }
    if (repo) return `https://github.com/${repo}`;
    return `https://github.com/${m.repo}`;
  }
</script>

<!-- One snippet per cell — used for owned/fork/star rows.
     `border` = outline class, `glyph` = src-tag char (cosmetic). -->
{#snippet cell(m, c, border, glyph)}
  <div class="cell {border}"
    on:mouseenter={() => (hoveredId = m.full_name || m.repo)}
    on:mouseleave={() => (hoveredId = null)}
    role="button" tabindex="0">
    <a class="cell-title" href={ghUrl(m)} target="_blank" rel="noopener"
       title={`Open ${m.full_name || m.repo} on GitHub`}>{m.repo}</a>
    <div class="cell-sub">
      <span class="src-tag">{glyph}</span>
      {#if m.language}<span class="lang">{m.language}</span>{/if}
      {#if m.stars}<span>★ {m.stars}</span>{/if}
    </div>
    {#if m.aim}<div class="cell-desc" title={m.aim}>{m.aim}</div>{/if}
    {#if hoveredId === (m.full_name || m.repo)}
      <div class="cell-actions">
        <button disabled={busy} on:click={() => promoteToHub(m)}>★ Promote</button>
        <a class="cell-view" href={ghUrl(m)} target="_blank" rel="noopener">↗ View repo</a>
        <button disabled={busy} class="remove"
          on:click={() => removeFromCluster(m, c)}>✕ Remove</button>
      </div>
    {/if}
  </div>
{/snippet}

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

{#if !loading && data && (!data.available || data.clusters?.length || data.saved === false)}
  <div class="layout">
    <aside class="rail">
      <div class="rail-stats">
        <b>{clusters.length}</b> clusters
        <br><b>{totalCount}</b> repos
        {#if orphans.length}<br><span class="stat-orphans">{orphans.length} orphans</span>{/if}
      </div>

      <label class="rail-in">
        <span># clusters</span>
        <input type="number" min="2" max="30" bind:value={k} />
      </label>

      <label class="rail-in" title="Applied to both passes (prime + orphan). Per-member cosine to cluster centroid — below this, the member is evicted to orphans. Higher = stricter = more orphans.">
        <span>Tightness <code>{coherence.toFixed(2)}</code></span>
        <input type="range" min="0.20" max="0.80" step="0.05" bind:value={coherence} />
      </label>

      <button class="primary" disabled={busy} on:click={() => doCluster(true)}
        title="Fresh k-means pass over the whole free pool">
        🧩 Cluster
      </button>

      <button class="primary soft" disabled={busy} on:click={() => doThemes()}
        title="Single LLM call across the whole portfolio — unique theme names, overlap allowed">
        ✨ Themes (LLM)
      </button>

      <button class="primary ghost" disabled={busy} on:click={() => doCluster(false)}
        title="Snap orphans into the existing columns; uses the Tightness slider">
        ➕ Cluster orphans
      </button>

      <button class="ghost danger" disabled={busy} on:click={resetClusters}
        title="Forget the current clustering; everything goes back to the orphan sidebar">
        🗑 Reset clustering
      </button>

      {#if data.saved}<span class="saved-pill">saved</span>{/if}

      <div class="rail-head">
        <b>Orphans</b>
        <span class="hint">{orphans.length}</span>
      </div>
      {#if orphans.length === 0}
        <p class="muted small">None left — every repo is in a column.</p>
      {:else}
        {#each orphans as o (o.full_name || o.repo)}
          <div class="orphan-row border-{borderKey(o.source)}" on:mouseenter={() => (hoveredId = o.full_name || o.repo)} on:mouseleave={() => (hoveredId = null)}>
            <a class="orphan-name" href={ghUrl(o)} target="_blank" rel="noopener"
               title="Open on GitHub">{o.repo}</a>
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
      {#if !data.available}
        <div class="info-msg" style="margin:2rem auto;max-width:520px;text-align:center">
          {#if data.saved === false}
            Not clustered yet — press <b>🧩 Cluster</b> on the left to start.
          {:else}
            {data.reason} <a href="/setup">Open Setup →</a>
          {/if}
        </div>
      {:else if clusters.length === 0}
        <p class="empty">No clusters remaining — every orphan is in the sidebar.</p>
      {:else}
        <div class="stage">
          {#each clusters as c (c.index)}
            <section class="col">
              <header class="col-head" title={c.suggested_name}>
                <div class="col-label">{c.suggested_name}</div>
                {#if c.anchored_to}
                  <div class="col-meta"><span class="anchor-pill">★ {c.anchored_to}</span></div>
                {/if}
              </header>
              <div class="col-body" style="max-height:{colMaxHeight()}px;">
                {#each c.owned as m (m.full_name || m.repo)}
                  {@render cell(m, c, 'border-O', 'O')}
                {/each}
                {#each c.forks as m (m.full_name || m.repo)}
                  {@render cell(m, c, 'border-F', 'F')}
                {/each}
                {#each c.stars as m (m.full_name || m.repo)}
                  {@render cell(m, c, 'border-S', 'S')}
                {/each}
              </div>
            </section>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<!-- borderKey lives in the live script above so the template can call it. -->

<style>
  .layout { display: grid; grid-template-columns: 240px 1fr; gap: 1rem;
    margin-top: 0.7rem; align-items: start; }

  .rail { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 0.7rem 0.75rem; position: sticky; top: 0.5rem;
    max-height: calc(100vh - 1rem); overflow-y: auto;
    display: flex; flex-direction: column; gap: 0.55rem; }
  .rail-stats { color: #374151; font-size: 0.86rem; line-height: 1.45;
    padding-bottom: 0.45rem; border-bottom: 1px solid #e5e7eb; }
  .stat-orphans { color: #b45309; font-weight: 600; }

  .rail-in { display: flex; flex-direction: column; gap: 0.25rem;
    font-size: 0.78rem; color: #4b5563; font-weight: 500; }
  .rail-in input[type=number] { width: 100%; padding: 0.32rem 0.4rem;
    border: 1px solid #d1d5db; border-radius: 5px; font-size: 0.9rem; }
  .rail-in input[type=range] { width: 100%; }
  .rail-in code { font-size: 0.74rem; color: #4338ca; background: #eef2ff;
    padding: 0.05em 0.35em; border-radius: 3px; font-weight: 600; }

  .primary { background: #4f46e5; color: #fff; border: none; border-radius: 6px;
    padding: 0.45rem 0.75rem; font-size: 0.84rem; font-weight: 600;
    cursor: pointer; width: 100%; }
  .primary.soft { background: #6366f1; }
  .primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .ghost.danger { background: #fff; color: #b91c1c; border: 1px solid #fecaca;
    padding: 0.4rem 0.75rem; border-radius: 6px; font-size: 0.82rem;
    cursor: pointer; width: 100%; font-weight: 500; }
  .ghost.danger:hover:not(:disabled) { background: #fef2f2; }
  .ghost.danger:disabled { opacity: 0.5; cursor: not-allowed; }

  .saved-pill { font-size: 0.72rem; background: #ecfdf5; color: #047857;
    border: 1px solid #a7f3d0; border-radius: 4px; padding: 0.1rem 0.5rem;
    align-self: flex-start; }

  .rail-head { display: flex; align-items: baseline; justify-content: space-between;
    margin-top: 0.5rem; padding: 0.45rem 0 0.35rem;
    border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb; }
  .rail-head .hint { color: #6b7280; font-size: 0.82rem; }

  .orphan-row { display: flex; align-items: center; gap: 0.35rem; padding: 0.28rem 0;
    border-left: 3px solid transparent; padding-left: 0.35rem; }
  .orphan-row.border-O { border-left-color: #111827; }
  .orphan-row.border-F { border-left-color: #d1d5db; }
  .orphan-row.border-S { border-left-color: #facc15; }
  .orphan-name { font-family: monospace; font-size: 0.74rem; color: #111827;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
    text-decoration: none; }
  .orphan-name:hover { color: #4f46e5; text-decoration: underline; }
  .orphan-pick { font-size: 0.72rem; padding: 0.15rem 0.25rem;
    border: 1px solid #d1d5db; border-radius: 4px; max-width: 110px; }

  .stage { border: 1px solid #e5e7eb; border-radius: 10px;
    background: radial-gradient(circle at 1px 1px, #f1f5f9 1px, transparent 0) 0 0 / 22px 22px;
    padding: 0.6rem; display: flex; flex-wrap: wrap; gap: 0.6rem;
    align-items: flex-start; min-height: 12rem; }
  .col { flex: 1 1 calc(25% - 0.6rem); min-width: 240px; max-width: 100%;
    display: flex; flex-direction: column;
    background: rgba(255,255,255,0.5); border-radius: 8px;
    border: 1px solid #e5e7eb; }
  .col-head { padding: 0.4rem 0.5rem 0.3rem; border-bottom: 1px solid #e5e7eb;
    background: rgba(255,255,255,0.6); border-radius: 8px 8px 0 0; }
  .col-label { font-size: 0.86rem; font-weight: 800; color: #4338ca;
    text-transform: uppercase; letter-spacing: 0.02em;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .col-meta { margin-top: 0.2rem; font-size: 0.7rem; color: #6b7280; }
  .anchor-pill { background: #fef3c7; color: #92400e; font-weight: 700;
    padding: 0.05em 0.4em; border-radius: 4px; font-size: 0.7rem; }
  /* Single-column grid forces vertical stack — no flex surprise can flip it
     to row. Each row is one cell. */
  .col-body { overflow-y: auto; padding: 0.35rem;
    display: grid; grid-template-columns: 1fr; row-gap: 0.35rem; }

  .cell { position: relative; border-radius: 6px; padding: 0.45rem 0.6rem;
    background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.08); cursor: default;
    overflow: hidden; }       /* block flow inside grid cell = stacks vertically */
  .cell.border-O { border: 2px solid #111827; }
  .cell.border-F { border: 2px solid #d1d5db; }
  .cell.border-S { border: 2px solid #facc15; }
  .cell-title { font-family: monospace; font-size: 0.78rem; font-weight: 600;
    color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    text-decoration: none; display: block; border-bottom: 1px dotted transparent; }
  .cell-title:hover { color: #4f46e5; border-bottom-color: #c7d2fe; }
  .cell-sub { display: flex; gap: 0.35rem; align-items: center; font-size: 0.7rem;
    color: #4b5563; }
  .src-tag { font-family: monospace; }
  .lang { background: #eff6ff; color: #1e40af; padding: 0 0.3em; border-radius: 3px; }
  .cell-desc { font-size: 0.78rem; color: #4b5563; line-height: 1.35;
    margin-top: 0.2rem;
    display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
    overflow: hidden; text-overflow: ellipsis; }
  .cell-title { margin-bottom: 0.2rem; }
  .cell-sub { line-height: 1.4; }
  .cell-actions { position: absolute; inset: 0; background: rgba(255,255,255,0.92);
    display: flex; flex-wrap: wrap; gap: 0.3rem; padding: 0.4rem;
    align-items: center; justify-content: center; }
  .cell-actions button, .cell-actions a.cell-view { font-size: 0.72rem;
    padding: 0.28rem 0.55rem; border-radius: 5px; border: 1px solid #4f46e5;
    color: #4f46e5; background: #fff; cursor: pointer; font-weight: 600;
    text-decoration: none; }
  .cell-actions button.remove { border-color: #d1d5db; color: #6b7280; }
  .cell-actions button.remove:hover { border-color: #dc2626; color: #dc2626; }
  .cell-actions button:disabled { opacity: 0.5; }

  .muted { color: #9ca3af; }
  .small { font-size: 0.78rem; }
</style>
