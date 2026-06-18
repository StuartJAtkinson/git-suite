<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';
  import { SOURCE_GLYPH } from '$lib/columns';

  // Assisted group formation: cluster the unassigned repos by function, then
  // for each cluster name a new hub OR promote a member as the hub, with a
  // description that becomes the hub's LLM-alignment guide.

  let data = null;
  let clusters = [];      // editable view models
  let loading = true;
  let errorMsg = '';
  let msg = '';
  let threshold = 0.6;
  let busy = null;
  let source = 'mixed';   // 'mixed' (default) | 'owned' (legacy)

  const LAYER_NAMES = {
    0: 'Event Bus', 1: 'Ontology', 2: 'Automation', 3: 'Knowledge & RAG',
    4: 'Media', 5: 'GIS & Maps', 6: 'Gaming', 7: 'Dev Tools', 8: 'Homelab', 9: 'Creative',
  };

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true; errorMsg = '';
    try {
      data = await api.getClusters($session.session_id, threshold, source);
      clusters = (data.clusters || []).map((c, i) => ({
        id: i,
        members: c.members,
        size: c.size,
        mode: 'new',                       // new | promote | existing
        hubName: c.suggested_name,
        promote: c.members[0]?.repo || '',
        existing: (data.hubs || [])[0] || '',
        description: c.suggested_description,
        layer: 9, priority: 3,
        selected: new Set(c.members.map((m) => m.repo)),
      }));
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  }

  function toggle(c, repo) {
    c.selected.has(repo) ? c.selected.delete(repo) : c.selected.add(repo);
    clusters = clusters;
  }

  function resolvedName(c) {
    if (c.mode === 'promote') return c.promote;
    if (c.mode === 'existing') return c.existing;
    return c.hubName;
  }

  async function formHub(c) {
    const hub_name = (resolvedName(c) || '').trim();
    if (!hub_name || c.selected.size === 0) return;
    busy = c.id; errorMsg = ''; msg = '';
    try {
      const r = await api.formHub($session.session_id, {
        hub_name, layer: Number(c.layer), priority: Number(c.priority),
        description: c.description, boundary: c.description,   // description doubles as LLM guide
        members: [...c.selected],
        promote: c.mode === 'promote' ? c.promote : null,
      });
      msg = `Formed ${r.hub} — absorbed ${r.absorbed.length} repo(s).`;
      clusters = clusters.filter((x) => x.id !== c.id);   // consumed
    } catch (e) { errorMsg = e.message; }
    finally { busy = null; }
  }
</script>

<div class="page-header">
  <h1>Cluster — form groups</h1>
  <p class="sub">Unassigned repos grouped by function. Name a new hub or promote a member as the hub; the description guides LLM alignment later.</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if msg}<div class="ok-msg" style="margin-top:0.6rem">{msg}</div>{/if}
{#if loading}<p class="loading">Embedding &amp; clustering repos…</p>{/if}

{#if !loading && data && !data.available}
  <div class="info-msg" style="margin-top:1rem">{data.reason} <a href="/setup">Open Setup →</a></div>
{/if}

{#if !loading && data && data.available}
  <div class="bar">
    <span>
      {data.orphan_count} unassigned · {clusters.length} clusters
      {#if data.source === 'mixed' && data.counts}
        · <span class="src-pill src-O">{data.counts.owned} owned</span>
        <span class="src-pill src-F">{data.counts.forks} forks</span>
        <span class="src-pill src-S">{data.counts.stars} stars</span>
      {/if}
    </span>
    <label class="src">source
      <select bind:value={source} on:change={load}>
        <option value="mixed">mixed (owned + forks + stars)</option>
        <option value="owned">owned only (legacy)</option>
      </select>
    </label>
    <label class="thr">tightness
      <input type="range" min="0.45" max="0.8" step="0.05" bind:value={threshold} on:change={load} />
      {threshold}
    </label>
    <button class="ghost sm" on:click={load}>↻ Re-cluster</button>
  </div>

  <div class="legend">
    Prefix symbols mark each node's source so type is scannable without a hover:
    <span class="src-pill src-O">{SOURCE_GLYPH.owned} owned</span>
    <span class="src-pill src-F">{SOURCE_GLYPH.fork} fork</span>
    <span class="src-pill src-S">{SOURCE_GLYPH.star} star</span>
  </div>

  {#if clusters.length === 0}
    <p class="empty">No clusters — nothing unassigned, or everything is a singleton at this tightness. Lower it to group more loosely.</p>
  {/if}

  {#each clusters as c (c.id)}
    <div class="cluster card">
      <div class="cl-top">
        <div class="modes">
          <label><input type="radio" bind:group={c.mode} value="new" /> New hub</label>
          <label><input type="radio" bind:group={c.mode} value="promote" /> Promote member</label>
          {#if (data.hubs || []).length}
            <label><input type="radio" bind:group={c.mode} value="existing" /> Existing hub</label>
          {/if}
        </div>
        <span class="size">{c.selected.size}/{c.size} selected</span>
      </div>

      <div class="cl-form">
        {#if c.mode === 'new'}
          <input class="hub-in" bind:value={c.hubName} placeholder="hub name" />
        {:else if c.mode === 'promote'}
          <select class="hub-in" bind:value={c.promote}>
            {#each c.members as m}<option value={m.repo}>{m.repo}</option>{/each}
          </select>
        {:else}
          <select class="hub-in" bind:value={c.existing}>
            {#each data.hubs as h}<option value={h}>{h}</option>{/each}
          </select>
        {/if}
        <select class="lay" bind:value={c.layer}>
          {#each Object.entries(LAYER_NAMES) as [n, nm]}<option value={n}>L{n} {nm}</option>{/each}
        </select>
        <select class="lay" bind:value={c.priority}>
          <option value={1}>Critical</option><option value={2}>High</option>
          <option value={3}>Medium</option><option value={4}>Low</option>
        </select>
        <button disabled={busy === c.id} on:click={() => formHub(c)}>
          {busy === c.id ? 'Forming…' : 'Form hub'}
        </button>
      </div>

      {#if c.mode !== 'existing'}
        <textarea class="desc" rows="2" bind:value={c.description}
          placeholder="Description / scope — guides LLM alignment"></textarea>
      {/if}

      <div class="members">
        {#each c.members as m}
          <label class="mem" class:off={!c.selected.has(m.repo)}>
            <input type="checkbox" checked={c.selected.has(m.repo)} on:change={() => toggle(c, m.repo)} />
            <span class="src-pill src-{m.source?.[0]?.toUpperCase() || 'O'}"
                  title={m.source || 'owned'}>{SOURCE_GLYPH[m.source] || SOURCE_GLYPH.owned}</span>
            <span class="mname">{m.repo}</span>
            {#if m.language}<span class="lt">{m.language}</span>{/if}
            <span class="maim">{m.aim || ''}</span>
          </label>
        {/each}
      </div>
    </div>
  {/each}
{/if}

<style>
  .bar { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin: 0.75rem 0 1rem; font-size: 0.85rem; color: #6b7280; }
  .thr { display: flex; align-items: center; gap: 0.4rem; }
  .cluster { margin-bottom: 1rem; }
  .cl-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
  .modes { display: flex; gap: 1rem; font-size: 0.85rem; }
  .modes label { display: flex; align-items: center; gap: 0.3rem; }
  .size { font-size: 0.78rem; color: #9ca3af; }
  .cl-form { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.5rem; }
  .hub-in { flex: 1; min-width: 180px; font-family: monospace; }
  .lay { font-size: 0.85rem; }
  .desc { width: 100%; margin-bottom: 0.5rem; font-size: 0.82rem; resize: vertical; }
  .members { display: flex; flex-direction: column; gap: 0.2rem; }
  .mem { display: flex; align-items: center; gap: 0.5rem; font-size: 0.83rem; padding: 0.2rem 0.4rem; border-radius: 4px; }
  .mem:hover { background: #f9fafb; }
  .mem.off { opacity: 0.45; }
  .mname { font-family: monospace; font-weight: 600; }
  .lt { font-size: 0.7rem; background: #eff6ff; color: #1e40af; border-radius: 4px; padding: 0.05em 0.35em; }
  .maim { color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .src { font-size: 0.85rem; display: flex; align-items: center; gap: 0.4rem; }
  .legend { font-size: 0.78rem; color: #6b7280; margin: 0.4rem 0 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
  .src-pill { display: inline-block; font-family: monospace; font-size: 0.72rem; padding: 0.05em 0.45em; border-radius: 4px; font-weight: 600; }
  .src-pill.src-O { background: #eff6ff; color: #1e40af; }
  .src-pill.src-F { background: #fef3c7; color: #92400e; }
  .src-pill.src-S { background: #f3e8ff; color: #6b21a8; }
</style>
