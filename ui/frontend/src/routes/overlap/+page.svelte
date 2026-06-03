<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // Hub overlap "venn" (matrix) + boundary-case repos + editable boundaries.
  let data = null;
  let loading = true;
  let errorMsg = '';
  let edited = {};        // hub -> boundary text being edited
  let savingHub = '';

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true; errorMsg = '';
    try {
      data = await api.getOverlap($session.session_id);
      edited = { ...data.boundaries };
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  }

  async function saveBoundary(hub) {
    savingHub = hub; errorMsg = '';
    try {
      await api.setHubBoundary(hub, edited[hub] ?? '');
    } catch (e) { errorMsg = e.message; }
    finally { savingHub = ''; }
  }

  $: hubs = data?.hubs ?? [];
  $: matrix = data?.matrix ?? {};
  // max cell value for heatmap shading
  $: maxCell = Math.max(1, ...hubs.flatMap((a) => hubs.map((b) => (a !== b ? (matrix[a]?.[b] ?? 0) : 0))));
  function shade(v) {
    if (!v) return 'transparent';
    const t = v / maxCell;                       // 0..1
    return `rgba(220,38,38,${0.12 + t * 0.55})`; // red intensity = more overlap
  }
  const short = (h) => h.replace(/-/g, '­-'); // allow wrapping
</script>

<div class="page-header">
  <h1>Hub overlap</h1>
  <p class="sub">Where hub scopes bleed together, which repos straddle two hubs, and the boundary rules fed to the LLM.</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Scoring repos against hub profiles…</p>{/if}

{#if !loading && data}
  <!-- Overlap matrix -->
  <div class="section">
    <div class="section-head"><h2>Overlap matrix</h2></div>
    <p class="hint">Cell = number of repos that score for both hubs (a straddle). Darker = more overlap.</p>
    <div class="matrix-wrap">
      <table class="matrix">
        <thead>
          <tr><th></th>{#each hubs as h}<th class="col">{short(h)}</th>{/each}</tr>
        </thead>
        <tbody>
          {#each hubs as a}
            <tr>
              <th class="row">{a}</th>
              {#each hubs as b}
                {@const v = a === b ? null : (matrix[a]?.[b] ?? 0)}
                <td class:diag={a === b} style="background:{a === b ? '#f3f4f6' : shade(v)}" title="{a} ∩ {b}: {v ?? '—'}">
                  {a === b ? '' : (v || '')}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Boundary cases -->
  <div class="section">
    <div class="section-head"><h2>Boundary cases ({data.cases.length})</h2></div>
    {#if data.cases.length === 0}
      <p class="empty">No repos straddle two hubs by the current scoring. ✓</p>
    {:else}
      <div class="repo-list">
        {#each data.cases as c}
          <div class="repo-row">
            <span class="repo-name">{c.repo}</span>
            {#if c.assigned_hub}<span class="assigned">→ {c.assigned_hub}</span>{/if}
            <span class="scores">
              {#each c.top as t, i}<span class="score s{i}">{t.hub} {t.score}</span>{/each}
            </span>
            <span class="gap" title="score gap between top two">Δ{c.gap}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Editable boundaries -->
  <div class="section">
    <div class="section-head"><h2>Hub boundaries</h2></div>
    <p class="hint">These scope rules are sent to the LLM during replan and migration so it assigns repos to the right hub.</p>
    {#each hubs as h}
      <div class="bnd">
        <div class="bnd-head">
          <span class="repo-name">{h}</span>
          <button class="sm" disabled={savingHub === h || edited[h] === data.boundaries[h]} on:click={() => saveBoundary(h)}>
            {savingHub === h ? 'Saving…' : (edited[h] === data.boundaries[h] ? 'Saved' : 'Save')}
          </button>
        </div>
        <textarea class="bnd-text" rows="2" bind:value={edited[h]}></textarea>
      </div>
    {/each}
  </div>
{/if}

<style>
  .hint { font-size: 0.8rem; color: #6b7280; margin: 0 0 0.75rem; }
  .matrix-wrap { overflow-x: auto; }
  .matrix { border-collapse: collapse; font-size: 0.75rem; }
  .matrix th, .matrix td { border: 1px solid #e5e7eb; padding: 0.3rem 0.4rem; text-align: center; }
  .matrix th.col { writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; font-family: monospace; font-weight: 600; height: 90px; }
  .matrix th.row { text-align: right; font-family: monospace; font-weight: 600; white-space: nowrap; }
  .matrix td { min-width: 30px; font-weight: 600; color: #1a1a2e; }
  .matrix td.diag { color: #d1d5db; }

  .assigned { font-size: 0.75rem; font-family: monospace; color: #065f46; background: #d1fae5; border-radius: 4px; padding: 0.1em 0.4em; }
  .scores { display: flex; gap: 0.35rem; margin-left: auto; }
  .score { font-size: 0.72rem; font-family: monospace; border-radius: 4px; padding: 0.1em 0.4em; background: #f3f4f6; color: #4b5563; }
  .score.s0 { background: #dbeafe; color: #1e40af; }
  .gap { font-size: 0.72rem; color: #9ca3af; width: 48px; text-align: right; }

  .bnd { margin-bottom: 0.7rem; }
  .bnd-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem; }
  .bnd-text { width: 100%; font-size: 0.82rem; resize: vertical; }
</style>
