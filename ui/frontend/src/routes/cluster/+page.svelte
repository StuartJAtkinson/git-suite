<script>
  import { onMount, onDestroy } from 'svelte';
  import { browser } from '$app/environment';
  import { goto } from '$app/navigation';
  import { forceSimulation, forceManyBody, forceCollide, forceX, forceY } from 'd3-force';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';
  import { SOURCE_GLYPH } from '$lib/columns';

  // Every repo (owned + forks + stars) is a node, force-grouped by semantic
  // cluster. The suggested cluster name is only a faint centre LABEL — never the
  // hub name. You PROMOTE a real repo as the hub (preferred) or CREATE one
  // (label is just a last-resort placeholder). Drag nodes to arrange/pin; click
  // to select which repos a hub draws from. Classification is set later
  // on Order (source/process/viz).

  let data = null;
  let nodes = [];          // one per repo
  let clusters = [];       // {index, name, description, lx, ly}  (centre labels)
  let loading = true;
  let errorMsg = '';
  let msg = '';
  let k = 8;               // target number of clusters (k-means)
  let busy = false;
  let refreshing = false;
  let source = 'mixed';
  let hoveredId = null;
  let selected = new Set();
  let newHubName = '';
  let width = 960;
  const HEIGHT = 700;
  const R = 8;             // node radius
  let sim = null;
  let stageEl;
  let drag = null;         // {node, moved}

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  });
  onDestroy(() => {
    sim?.stop();
    if (browser) {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    }
  });

  async function load(recompute = false) {
    loading = true; errorMsg = ''; selected = new Set(); hoveredId = null;
    try {
      // On mount (recompute=false) read saved-only — NEVER auto-compute, so
      // landing here never spends embedding tokens. Clustering happens only on
      // an explicit action (Re-cluster / slider / source / refresh) -> recompute.
      data = await api.getClusters($session.session_id, { k, source, recompute, savedOnly: !recompute });
      if (data.k) k = data.k;   // reflect the saved pass
      build(data.clusters || []);
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  }

  function clusterAnchor(i, total) {
    const cols = Math.ceil(Math.sqrt(total));
    const rows = Math.ceil(total / cols);
    const col = i % cols, row = Math.floor(i / cols);
    return { x: ((col + 0.5) / cols) * width, y: ((row + 0.5) / rows) * HEIGHT };
  }

  function build(cl) {
    sim?.stop();
    clusters = cl.map((c, i) => {
      const a = clusterAnchor(i, cl.length || 1);
      return { index: i, name: c.suggested_name, description: c.suggested_description, ax: a.x, ay: a.y, lx: a.x, ly: a.y };
    });
    nodes = [];
    cl.forEach((c, ci) => {
      c.members.forEach((m) => {
        const a = clusterAnchor(ci, cl.length || 1);
        nodes.push({
          id: nodes.length, cluster: ci,
          repo: m.repo, aim: m.aim, domain: m.domain,
          entities: m.entities || [], purpose: m.purpose || "",
          source: m.source,
          language: m.language, stars: m.stars,
          x: a.x + (Math.random() - 0.5) * 60, y: a.y + (Math.random() - 0.5) * 60,
        });
      });
    });
    if (!nodes.length) return;
    sim = forceSimulation(nodes)
      .force('collide', forceCollide(R + 3))
      .force('charge', forceManyBody().strength(-22))
      .force('x', forceX((n) => clusters[n.cluster].ax).strength(0.22))
      .force('y', forceY((n) => clusters[n.cluster].ay).strength(0.22))
      .on('tick', tick);
  }

  function tick() {
    // recompute each cluster's label position as the centroid of its nodes
    for (const c of clusters) { c._sx = 0; c._sy = 0; c._n = 0; }
    for (const n of nodes) { const c = clusters[n.cluster]; c._sx += n.x; c._sy += n.y; c._n++; }
    for (const c of clusters) if (c._n) { c.lx = c._sx / c._n; c.ly = c._sy / c._n; }
    nodes = nodes; clusters = clusters;
  }

  // ── drag (sets fx/fy; stays pinned so manual arrangement sticks) ──
  function onDown(n, e) {
    drag = { node: n, moved: false };
    n.fx = n.x; n.fy = n.y;
    sim?.alphaTarget(0.3).restart();
    e.target.setPointerCapture?.(e.pointerId);
  }
  function onMove(e) {
    if (!drag) return;
    drag.moved = true;
    const r = stageEl.getBoundingClientRect();
    drag.node.fx = e.clientX - r.left;
    drag.node.fy = e.clientY - r.top;
  }
  function onUp() {
    if (!drag) return;
    if (!drag.moved) toggleSelect(drag.node);   // a click, not a drag
    sim?.alphaTarget(0);
    drag = null;                                  // keep fx/fy → pinned in place
  }

  function toggleSelect(n) {
    selected.has(n.repo) ? selected.delete(n.repo) : selected.add(n.repo);
    selected = selected;
  }
  function clearSel() { selected = new Set(); }

  // dominant cluster label among the current selection — the last-resort name
  function suggestedLabel() {
    if (!selected.size) return '';
    const tally = {};
    for (const n of nodes) if (selected.has(n.repo)) tally[n.cluster] = (tally[n.cluster] || 0) + 1;
    const best = Object.entries(tally).sort((a, b) => b[1] - a[1])[0];
    return best ? clusters[best[0]].name : '';
  }

  async function form(promote) {
    const members = new Set(selected);
    if (promote) members.add(promote);
    const hub_name = (promote || newHubName || suggestedLabel() || '').trim();
    if (!hub_name) { errorMsg = 'Name the hub, or promote a repo.'; return; }
    if (members.size === 0) { errorMsg = 'Select the repos this hub draws from.'; return; }
    busy = true; errorMsg = ''; msg = '';
    try {
      const desc = clusters.find((c) => c.name === suggestedLabel())?.description || '';
      const r = await api.formHub($session.session_id, {
        hub_name, description: desc, boundary: desc,
        members: [...members], promote: promote || null,
      });
      msg = `${promote ? 'Promoted' : 'Created'} ${r.hub} — absorbed ${r.absorbed.length} repo(s).`;
      const gone = new Set([...members, r.hub]);
      nodes = nodes.filter((n) => !gone.has(n.repo)).map((n, i) => ({ ...n, id: i }));
      selected = new Set(); newHubName = '';
      sim?.nodes(nodes).alpha(0.4).restart();
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }
</script>

<div class="page-header">
  <h1>Cluster — form hubs</h1>
  <p class="sub">Every repo is a node, grouped by function. The grey label is just the cluster's theme — <b>promote a real repo</b> as the hub, or select repos and <b>create</b> one. Drag to arrange &amp; pin.</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if msg}<div class="ok-msg" style="margin-top:0.6rem">{msg}</div>{/if}
{#if loading}<p class="loading">Embedding &amp; clustering repos…</p>{/if}

{#if !loading && data && !data.available}
  <div class="info-msg" style="margin-top:1rem">
    {#if data.saved === false}
      Not clustered yet — clustering runs only when you ask.
      <button class="ghost sm" style="margin-left:0.5rem" on:click={() => load(true)}>🧩 Cluster now</button>
    {:else}
      {data.reason} <a href="/setup">Open Setup →</a>
    {/if}
  </div>
{/if}

{#if !loading && data && data.available}
  <div class="bar">
    <span>
      {nodes.length} repos · {clusters.length} clusters
      {#if data.source === 'mixed' && data.counts}
        · <span class="src-pill src-O">{data.counts.owned} owned</span>
        <span class="src-pill src-F">{data.counts.forks} forks</span>
        <span class="src-pill src-S">{data.counts.stars} stars</span>
      {/if}
    </span>
    <label class="src">source
      <select bind:value={source} on:change={() => load(true)}>
        <option value="mixed">mixed (owned + forks + stars)</option>
        <option value="owned">owned only</option>
      </select>
    </label>
    <label class="thr"># clusters
      <input type="range" min="2" max="30" step="1" bind:value={k} on:change={() => load(true)} />
      {k}
    </label>
    {#if data.saved}<span class="saved-pill">saved</span>{/if}
    <button class="ghost sm" on:click={() => load(true)}>↻ Re-cluster</button>
    <button class="ghost sm" disabled={refreshing} on:click={async () => {
      refreshing = true; errorMsg = ''; msg = '';
      try {
        const [f, s] = await Promise.all([api.refreshForks($session.session_id), api.refreshStars($session.session_id)]);
        msg = `Refreshed ${f.count} fork(s) and ${s.count ?? 0} star(s).`; await load(true);
      } catch (e) { errorMsg = e.message; } finally { refreshing = false; }
    }}>{refreshing ? 'Refreshing…' : '↻ Refresh forks/stars'}</button>
  </div>

  <!-- selection action bar -->
  <div class="selbar" class:active={selected.size > 0}>
    {#if selected.size > 0}
      <b>{selected.size} selected</b>
      <input class="hub-in" bind:value={newHubName} placeholder={suggestedLabel() || 'new hub name'} />
      <button class="create" disabled={busy} on:click={() => form(null)}>
        {busy ? 'Forming…' : '✚ Create hub'}
      </button>
      <span class="seltip">…or hover a selected repo and hit ★ Promote (preferred)</span>
      <button class="ghost sm" on:click={clearSel}>Clear</button>
    {:else}
      <span class="muted">Click repos to select which a hub draws from · drag to arrange · hover for details.</span>
    {/if}
  </div>

  {#if nodes.length === 0}
    <p class="empty">No repos to cluster — nothing unassigned at this tightness.</p>
  {:else}
    <div class="stage" bind:this={stageEl} bind:clientWidth={width} style="height:{HEIGHT}px">
      {#each clusters as c (c.index)}
        <div class="clabel" style="left:{c.lx}px; top:{c.ly}px">{c.name}</div>
      {/each}
      {#each nodes as n (n.id)}
        <div class="node src-{n.source?.[0]?.toUpperCase() || 'O'}"
             class:sel={selected.has(n.repo)} class:hov={hoveredId === n.id}
             style="left:{n.x}px; top:{n.y}px; z-index:{hoveredId === n.id ? 60 : (selected.has(n.repo) ? 20 : 2)}"
             on:pointerdown={(e) => onDown(n, e)}
             on:mouseenter={() => (hoveredId = n.id)}
             on:mouseleave={() => (hoveredId = n.id === hoveredId ? null : hoveredId)}
             role="button" tabindex="0">
          <span class="dot"></span>
          {#if hoveredId === n.id}
            <div class="card" on:pointerdown|stopPropagation>
              <div class="c-name">{SOURCE_GLYPH[n.source] || SOURCE_GLYPH.owned} {n.repo}</div>
              {#if n.purpose}<div class="c-purpose">{n.purpose}</div>{/if}
              {#if n.domain}<div class="c-domain">{n.domain}</div>{/if}
              {#if n.entities && n.entities.length}
                <div class="c-entities">{n.entities.join(' · ')}</div>
              {/if}
              {#if n.aim}<div class="c-aim">{n.aim}</div>{/if}
              <div class="c-meta">
                {#if n.language}<span class="c-lang">{n.language}</span>{/if}
                {#if n.stars}<span>★ {n.stars}</span>{/if}
              </div>
              <button class="promote" disabled={busy} on:click|stopPropagation={() => form(n.repo)}>★ Promote as hub</button>
            </div>
          {:else}
            <span class="ntitle">{n.repo}</span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
{/if}

<style>
  .bar { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin: 0.75rem 0 0.5rem; font-size: 0.85rem; color: #6b7280; }
  .thr { display: flex; align-items: center; gap: 0.4rem; }
  .src { font-size: 0.85rem; display: flex; align-items: center; gap: 0.4rem; }
  .src-pill { display: inline-block; font-family: monospace; font-size: 0.72rem; padding: 0.05em 0.45em; border-radius: 4px; font-weight: 600; }
  .src-pill.src-O { background: #eff6ff; color: #1e40af; }
  .src-pill.src-F { background: #fef3c7; color: #92400e; }
  .src-pill.src-S { background: #f3e8ff; color: #6b21a8; }
  .saved-pill { font-size: 0.7rem; background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; border-radius: 4px; padding: 0.05em 0.45em; }

  .selbar { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap; min-height: 38px;
    padding: 0.4rem 0.7rem; border-radius: 8px; background: #f8fafc; border: 1px solid #e5e7eb; margin-bottom: 0.5rem; font-size: 0.85rem; }
  .selbar.active { background: #eef2ff; border-color: #c7d2fe; }
  .selbar .muted { color: #9ca3af; }
  .hub-in { font-family: monospace; min-width: 200px; }
  .create { background: #4f46e5; color: #fff; border: none; border-radius: 6px; padding: 0.4rem 0.8rem; font-weight: 600; cursor: pointer; }
  .create:disabled { opacity: 0.5; }
  .seltip { font-size: 0.76rem; color: #6b7280; }

  .stage { position: relative; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;
    background: radial-gradient(circle at 1px 1px, #f1f5f9 1px, transparent 0) 0 0 / 22px 22px;
    touch-action: none; user-select: none; }

  .clabel { position: absolute; transform: translate(-50%, -50%); pointer-events: none;
    font-size: 0.95rem; font-weight: 800; color: #cbd5e1; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; z-index: 1; }

  .node { position: absolute; transform: translate(-50%, -50%); cursor: grab; display: flex; align-items: center; gap: 4px; }
  .node:active { cursor: grabbing; }
  .dot { width: 12px; height: 12px; border-radius: 50%; background: #6366f1; border: 2px solid #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.25); flex: none; }
  .node.src-F .dot { background: #d97706; }
  .node.src-S .dot { background: #9333ea; }
  .node.sel .dot { background: #16a34a; box-shadow: 0 0 0 3px #bbf7d0; }
  .ntitle { font-size: 0.66rem; color: #475569; background: rgba(255,255,255,0.75); padding: 0 3px; border-radius: 3px;
    max-width: 92px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .node.sel .ntitle { color: #166534; font-weight: 700; }

  .card { position: absolute; left: 14px; top: -6px; width: 230px; background: #fff;
    border: 2px solid #818cf8; border-radius: 9px; box-shadow: 0 10px 28px rgba(0,0,0,0.22); padding: 0.55rem 0.65rem; cursor: default; }
  .c-name { font-family: monospace; font-weight: 700; font-size: 0.82rem; word-break: break-word; }
  .c-purpose { font-size: 0.78rem; color: #1e293b; font-weight: 600; margin: 0.2rem 0; }
  .c-domain { font-size: 0.74rem; color: #4338ca; background: #eef2ff; border-radius: 4px; padding: 0.15em 0.4em; display: inline-block; margin: 0.15rem 0; }
  .c-entities { font-size: 0.72rem; color: #6b7280; margin: 0.1rem 0 0.25rem; }
  .c-aim { font-size: 0.76rem; color: #4b5563; margin: 0.25rem 0; max-height: 4.5em; overflow: hidden; }
  .c-meta { display: flex; gap: 0.5rem; font-size: 0.7rem; color: #6b7280; margin-bottom: 0.4rem; }
  .c-lang { background: #eff6ff; color: #1e40af; border-radius: 4px; padding: 0.03em 0.35em; }
  .promote { width: 100%; font-size: 0.76rem; padding: 0.3rem; border: 1px solid #4f46e5; color: #4f46e5;
    background: #fff; border-radius: 6px; cursor: pointer; font-weight: 700; }
  .promote:hover { background: #4f46e5; color: #fff; }
  .promote:disabled { opacity: 0.5; }
</style>
