<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';
  import {
    forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide,
  } from 'd3-force';

  // Read-only renderer for Step 8 (Guided installer). git-suite does NOT
  // build or download the hubs — it exports the install plan and the
  // user (or a downstream hub-standards agent) does the rest. This page
  // is the "see what would happen" surface: hand-off copy, the hub DAG
  // in topological install order, and one-click export of the three
  // manifest formats the backend exposes.

  let loading = true;
  let busy = false;
  let error = '';
  let manifest = null;     // JSON manifest from GET /install/{sid}
  let activeHub = '';      // hub name whose install-order + DAG is shown

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    try {
      manifest = await fetchRawManifest();
      if (manifest?.install_order?.length) activeHub = manifest.install_order[0];
    } catch (e) { error = e.message; }
    finally { loading = false; }
  });

  async function fetchRawManifest() {
    const r = await fetch(`/api/install/${$session.session_id}`);
    if (!r.ok) throw new Error(await r.text() || r.statusText);
    return r.json();
  }

  // Localise the backend's ISO timestamp to the user's locale (was rendered
  // raw `…Z`; every other timestamp in the app is localised).
  function formatGeneratedAt(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString();
  }

  async function download(kind) {
    busy = true; error = '';
    try {
      const map = { text: '/text', compose: '/compose' };
      const mime = kind === 'compose'
        ? 'text/x-yaml;charset=utf-8'
        : 'text/plain;charset=utf-8';
      const ext = kind === 'compose' ? 'yaml' : 'txt';
      const r = await fetch(`/api/install/${$session.session_id}${map[kind]}`);
      if (!r.ok) throw new Error(await r.text() || r.statusText);
      const body = await r.text();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([body], { type: mime }));
      a.download = `install-${$session.session_id.slice(0, 8)}-${new Date().toISOString().slice(0, 10)}.${ext}`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { error = e.message; }
    finally { busy = false; }
  }

  // Re-fetch the active hub's DAG (e.g. after annotating wikidata_id).
  async function refreshActiveDag() {
    if (!activeHub || !$session) return;
    try {
      const dag = await api.getWikidataDag($session.session_id, activeHub);
      manifest.dags[activeHub] = dag;
      manifest = manifest;  // trigger reactivity
    } catch (e) { error = e.message; }
  }

  // -- DAG rendering (D3-force) --------------------------------------------

  // Reactive state passed to the SVG template.
  let simNodes = [];
  let simEdges = [];
  let simMeta = { source: 'local', note: '', root: '' };
  let svgEl;                    // <svg> bind:this

  // d3-force mutates the node objects in place; we rebuild on every
  // activeHub / dag change so the layout is fresh. The old simulation is
  // stopped before the new one starts to avoid a zombie tick loop.
  let currentSim = null;

  $: rebuildSim(activeHub, manifest?.dags?.[activeHub], svgEl);

  function rebuildSim(hub, dag, svg) {
    if (currentSim) { currentSim.stop(); currentSim = null; }
    if (!dag || !svg) { simNodes = []; simEdges = []; return; }
    simMeta = {
      source: dag.source || 'local',
      note: dag.note || '',
      root: dag.root || '',
      cache: dag.cache || '',
    };
    if (dag.source !== 'wikidata') { simNodes = []; simEdges = []; return; }

    // d3 mutates the nodes; pass a fresh shallow copy keyed by qid.
    const byId = new Map();
    const nodes = (dag.nodes || []).map((n) => {
      const copy = { ...n };
      byId.set(n.qid, copy);
      return copy;
    });
    const edges = (dag.edges || []).map((e) => ({
      source: byId.get(e.from) || { qid: e.from },
      target: byId.get(e.to) || { qid: e.to },
      prop: e.prop || 'P279/P361',
    }));

    const width = Math.max(svg.clientWidth || 600, 480);
    const height = 540;
    const sim = forceSimulation(nodes)
      .force('link', forceLink(edges).id((d) => d.qid).distance(80).strength(0.7))
      .force('charge', forceManyBody().strength(-260))
      .force('center', forceCenter(width / 2, height / 2))
      .force('collide', forceCollide().radius(34))
      .alpha(0.9)
      .alphaDecay(0.05);
    sim.on('tick', () => { simNodes = nodes; simEdges = edges; });
    currentSim = sim;
  }
</script>

<div class="page-header">
  <h1>Install</h1>
  <p class="sub">
    Step 8 — the install plan, exported as a hand-off. git-suite is the
    install <b>brain</b>, not the installer. The hub DAG below is what a
    downstream hub-standards agent (or you) consumes to actually build /
    deploy each hub. Read-only here; nothing on this page pushes to
    GitHub, runs a Dockerfile, or mutates <code>plan.json</code>.
  </p>
</div>

{#if error}<div class="error-msg">{error}</div>{/if}
{#if loading}<p class="loading">Loading…</p>{/if}

{#if !loading}
  {#if !manifest || !manifest.nodes?.length}
    <div class="info-msg centered">
      No hubs in plan.json. Form one on the <a href="/cluster">Cluster</a>
      page first — Step 8 plans emerge from Step 7's hub DAG.
    </div>
  {:else}
    <div class="bar">
      <span class="meta">
        <b>{manifest.nodes.length}</b> hub{manifest.nodes.length === 1 ? '' : 's'} ·
        generated <code>{formatGeneratedAt(manifest.generated_at)}</code>
        {#if manifest.dags}
          ·
          <b>{Object.values(manifest.dags).filter((d) => d.source === 'wikidata').length}</b>
          with Wikidata DAG
        {/if}
      </span>
      <button disabled={busy} on:click={() => download('text')}>
        {busy ? 'Saving…' : '⬇ Save install order (.txt)'}
      </button>
      <button disabled={busy} on:click={() => download('compose')}>
        ⬇ Save compose fragment (.yaml)
      </button>
      <button disabled={busy} on:click={async () => {
        const r = await fetchRawManifest();                       // re-pull
        const text = JSON.stringify(r, null, 2);
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
        a.download = `install-${$session.session_id.slice(0, 8)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      }}>
        ⬇ Save manifest (.json)
      </button>
    </div>

    <div class="hub-tabs" role="tablist">
      {#each manifest.install_order as name}
        <button
          class="hub-tab"
          class:is-active={name === activeHub}
          role="tab"
          aria-selected={name === activeHub}
          on:click={() => activeHub = name}
        >
          {name}
          {#if manifest.dags?.[name]?.source === 'wikidata'}
            <span class="badge">W</span>
          {/if}
        </button>
      {/each}
    </div>

    {#if activeHub}
      {@const hub = manifest.nodes.find((n) => n.name === activeHub)}
      {@const deps = manifest.edges.filter((e) => e.to === activeHub).map((e) => e.from)}
      {@const dag = manifest.dags?.[activeHub]}

      <h2>Install order — {activeHub}</h2>
      <ol class="install-order">
        <li>
          <div class="step-head">
            <span class="step-num">1.</span> <code>{activeHub}</code>
            <a class="hub-url" href={hub?.url} target="_blank" rel="noopener">↗ GitHub</a>
          </div>
          {#if hub?.description}
            <div class="hub-desc">{hub.description}</div>
          {/if}
          {#if deps.length}
            <div class="hub-deps">depends on: {deps.join(', ')}</div>
          {/if}
          {#if hub?.absorbs?.length}
            <div class="hub-members">
              group into hub ({hub.absorbs.length}):
              {#each hub.absorbs as r}
                <code>{r}</code>
              {/each}
            </div>
          {/if}
          {#if hub?.wikidata_id}
            <div class="hub-wd">
              Wikidata: <a href={`https://www.wikidata.org/wiki/${hub.wikidata_id}`}
                          target="_blank" rel="noopener">{hub.wikidata_id}</a>
              <button class="link-btn" on:click={refreshActiveDag}>↻ refresh DAG</button>
            </div>
          {/if}
        </li>
      </ol>

      <h2>DAG — {activeHub}</h2>
      {#if dag?.source === 'wikidata'}
        <p class="muted small">
          Sourced from Wikidata (P279/P361 over
          <a href={`https://www.wikidata.org/wiki/${simMeta.root}`} target="_blank" rel="noopener">{simMeta.root}</a>).
          {#if simMeta.cache === 'hit'} Served from cache.{/if}
          {#if simMeta.cache === 'miss'} Freshly fetched.{/if}
        </p>
        <div class="hub-dag">
          <svg bind:this={svgEl} viewBox="0 0 0 0" xmlns="http://www.w3.org/2000/svg">
            <g class="edges">
              {#each simEdges as e}
                {@const sx = (e.source && e.source.x) ?? 0}
                {@const sy = (e.source && e.source.y) ?? 0}
                {@const tx = (e.target && e.target.x) ?? 0}
                {@const ty = (e.target && e.target.y) ?? 0}
                <line x1={sx} y1={sy} x2={tx} y2={ty} stroke="var(--quiet-text)" stroke-width="1" />
              {/each}
            </g>
            <g class="nodes">
              {#each simNodes as n (n.qid)}
                {@const isRoot = n.qid === simMeta.root}
                {@const isRepo = n.kind === 'repo'}
                <g transform={`translate(${n.x ?? 0}, ${n.y ?? 0})`}>
                  <circle r={isRoot ? 22 : isRepo ? 14 : 16}
                          fill={isRoot ? '#0057b7' : isRepo ? '#f59e0b' : '#fff'}
                          stroke={isRoot ? '#0057b7' : '#6b7280'}
                          stroke-width="1" />
                  <text y="4" text-anchor="middle" font-size="11"
                        fill={isRoot ? '#fff' : '#111827'}>
                    {(n.label || n.qid).slice(0, 12)}
                    <tspan x="0" dy="13" font-size="9"
                           fill={isRoot ? '#e0f2fe' : '#6b7280'}>{n.qid}</tspan>
                  </text>
                </g>
              {/each}
            </g>
          </svg>
        </div>
      {:else if dag}
        <div class="info-msg">
          <b>Wikidata DAG not available.</b> {dag.note || 'no Wikidata id annotated on this hub.'}
          {#if !hub?.wikidata_id}
            Set it via the API (<code>api.setHubWikidataId(session_id, hub, 'Q####')</code>) and click ↻ refresh.
          {:else}
            (Wikidata SPARQL endpoint may be unreachable.)
          {/if}
        </div>
      {:else}
        <div class="info-msg">No DAG payload for this hub.</div>
      {/if}
    {/if}

    {#if manifest.edges?.length}
      <h2>Hub-on-hub edges</h2>
      <p class="muted small">A row appears here only when one hub's name appears as an absorbed repo of another.</p>
      <ul class="edges">
        {#each manifest.edges as e}
          <li><code>{e.from}</code> is a prerequisite of <code>{e.to}</code></li>
        {/each}
      </ul>
    {/if}
  {/if}
{/if}

<style>
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem;
    background: #fff; border: 1px solid var(--border); border-radius: 8px;
    padding: 0.65rem 0.85rem; margin-bottom: 1rem;
    font-size: 0.85rem; }
  .meta { font-size: 0.84rem; color: #4b5563; flex: 1 1 240px; min-width: 0; }
  .meta code { background: #f3f4f6; padding: 0.05rem 0.35rem;
    border-radius: 3px; font-size: 0.74rem; }

  /* Tab strip — one per hub. */
  .hub-tabs { display: flex; flex-wrap: wrap; gap: 0.25rem;
    border-bottom: 1px solid var(--border); margin-bottom: 1rem; }
  .hub-tab { background: #fff; border: 1px solid var(--border);
    border-bottom: none; border-radius: 6px 6px 0 0;
    padding: 0.4rem 0.9rem; font-size: 0.85rem; cursor: pointer;
    color: #4b5563; display: inline-flex; align-items: center; gap: 0.35rem; }
  .hub-tab:hover { background: #f3f4f6; }
  .hub-tab.is-active { background: #0057b7; color: #fff;
    border-color: #0057b7; font-weight: 600; }
  .hub-tab.is-active .badge { background: #fff; color: #0057b7; }
  .badge { background: #0057b7; color: #fff; font-size: 0.65rem;
    padding: 0.05rem 0.4rem; border-radius: 3px; font-weight: 700; }

  .install-order { list-style: none; padding: 0; margin: 0;
    display: flex; flex-direction: column; gap: 0.7rem; }
  .install-order li { background: #fff; border: 1px solid var(--border);
    border-radius: 8px; padding: 0.7rem 0.9rem; }
  .step-head { display: flex; align-items: center; gap: 0.5rem; }
  .step-num { font-weight: 700; color: #111827; min-width: 1.7rem; }
  .step-head code { font-size: 1rem; font-weight: 700; color: #0057b7; }
  .hub-url { margin-left: auto; font-size: 0.8rem; text-decoration: none;
    color: #0057b7; }
  .hub-url:hover { text-decoration: underline; }
  .hub-desc { font-size: 0.86rem; color: #4b5563; margin-top: 0.35rem;
    line-height: 1.45; }
  .hub-deps { font-size: 0.78rem; color: #6b7280; margin-top: 0.3rem; }
  .hub-members { font-size: 0.8rem; color: #4b5563; margin-top: 0.4rem;
    display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .hub-members code { font-size: 0.74rem; background: #f3f4f6;
    padding: 0.1rem 0.4rem; border-radius: 3px; }
  .hub-wd { font-size: 0.78rem; color: #4b5563; margin-top: 0.4rem;
    display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .hub-wd a { color: #0057b7; text-decoration: none; }
  .hub-wd a:hover { text-decoration: underline; }
  .link-btn { background: none; border: none; padding: 0; cursor: pointer;
    color: #0057b7; font-size: 0.78rem; text-decoration: underline; }

  /* DAG canvas. */
  .hub-dag { background: #fff; border: 1px solid var(--border);
    border-radius: 8px; height: 540px; overflow: hidden; }
  .hub-dag svg { width: 100%; height: 100%; display: block; }
  .hub-dag text { user-select: none; pointer-events: none; }

  .edges { list-style: none; padding: 0; margin: 0.5rem 0; }
  .edges li { background: #fffbeb; border: 1px solid #fde68a;
    border-radius: 6px; padding: 0.4rem 0.7rem; margin-bottom: 0.3rem;
    font-size: 0.84rem; }
  .edges code { font-size: 0.84rem; }
</style>
