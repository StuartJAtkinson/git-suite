<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // One reconcile call backs the whole cycle summary (philosophy #2 + #6:
  // the summary reads the audit-derived rollup, not a separate source).

  let data = null;
  let loading = true;
  let errorMsg = '';

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true;
    errorMsg = '';
    try {
      data = await api.reconcile($session.session_id);
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }

  const sum = (arr, k) => arr.reduce((a, h) => a + (h[k] || 0), 0);

  $: hubs = data?.hubs ?? [];
  $: stats = data?.stats ?? {};
  $: absorbDone = sum(hubs, 'absorb_done');
  $: absorbTotal = sum(hubs, 'absorb_total');
  $: archiveDone = sum(hubs, 'archive_done');
  $: archiveTotal = sum(hubs, 'archive_total');
  $: orphans = data?.orphans ?? [];
  $: cycleDone = data !== null && stats.undecided === 0 &&
    absorbDone === absorbTotal && archiveDone === archiveTotal;
</script>

<div class="page-header">
  <h1>Cycle Summary</h1>
  <p class="sub">Intent vs reality for the current portfolio — and what's next.</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Reconciling…</p>{/if}

{#if !loading && data}
<div class="summary-grid">
  <div class="stat-card">
    <div class="stat-value">{stats.live}</div>
    <div class="stat-label">Live repos</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{absorbDone}/{absorbTotal}</div>
    <div class="stat-label">Repos absorbed</div>
    <div class="progress-bar"><div class="progress-fill" style="width:{absorbTotal ? absorbDone/absorbTotal*100 : 0}%"/></div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{archiveDone}/{archiveTotal}</div>
    <div class="stat-label">Repos archived</div>
    <div class="progress-bar"><div class="progress-fill" style="width:{archiveTotal ? archiveDone/archiveTotal*100 : 0}%"/></div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{stats.undecided}</div>
    <div class="stat-label">Undecided (orphans)</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{stats.ghost}</div>
    <div class="stat-label">Ghosts (planned, not live)</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">{stats.stub ?? 0}</div>
    <div class="stat-label">Stub repos (drop candidates)</div>
  </div>
</div>

<div class="section">
  <div class="section-head"><h2>Hub progress</h2></div>
  <div class="hub-progress-list">
    {#each hubs as hub}
      <div class="hub-progress-row">
        <div class="hub-info">
          <span class="hub-name">{hub.name}</span>
          <span class="layer-tag-sm">L{hub.layer}</span>
        </div>
        <div class="hub-bars">
          {#if hub.absorb_total > 0}
            <div class="mini-bar-group" title="Absorbed: {hub.absorb_done}/{hub.absorb_total}">
              <span class="mini-label">absorb</span>
              <div class="mini-bar"><div class="mini-fill absorb" style="width:{hub.absorb_done/hub.absorb_total*100}%"/></div>
              <span class="mini-count">{hub.absorb_done}/{hub.absorb_total}</span>
            </div>
          {/if}
          {#if hub.archive_total > 0}
            <div class="mini-bar-group" title="Archived: {hub.archive_done}/{hub.archive_total}">
              <span class="mini-label">arch</span>
              <div class="mini-bar"><div class="mini-fill archive" style="width:{hub.archive_done/hub.archive_total*100}%"/></div>
              <span class="mini-count">{hub.archive_done}/{hub.archive_total}</span>
            </div>
          {/if}
          {#if hub.ghosts.length > 0}
            <span class="ghost-note" title="Planned absorbs that don't exist live">{hub.ghosts.length} ghost{hub.ghosts.length > 1 ? 's' : ''}</span>
          {/if}
          {#if hub.absorb_total === 0 && hub.archive_total === 0}
            <span class="empty-small">—</span>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>

<div class="section">
  <div class="section-head"><h2>Recommended next actions</h2></div>
  <div class="actions-list">
    {#if cycleDone}
      <div class="ok-msg">✓ Cycle complete — nothing undecided, all absorbs and archives done.</div>
      <button class="success" on:click={() => goto('/scan')}>Start new scan</button>
    {:else}
      {#if stats.undecided > 0}
        <div class="action-item">
          <span class="action-num">1</span>
          <span>Triage {stats.undecided} undecided repo{stats.undecided > 1 ? 's' : ''} — give each a verdict</span>
          <a href="/triage"><button class="sm secondary">Go to Triage</button></a>
        </div>
      {/if}
      {#if (stats.stub ?? 0) > 0}
        <div class="action-item">
          <span class="action-num">!</span>
          <span>{stats.stub} stub repo{stats.stub > 1 ? 's' : ''} flagged — review for archiving</span>
          <a href="/triage"><button class="sm secondary">Review in Triage</button></a>
        </div>
      {/if}
      {#if absorbDone < absorbTotal}
        <div class="action-item">
          <span class="action-num">2</span>
          <span>Finish absorbs — {absorbTotal - absorbDone} remaining</span>
          <a href="/hubs"><button class="sm secondary">Go to Hubs</button></a>
        </div>
      {/if}
      {#if archiveDone < archiveTotal}
        <div class="action-item">
          <span class="action-num">3</span>
          <span>Clear archive queue — {archiveTotal - archiveDone} remaining</span>
          <a href="/execute"><button class="sm secondary">Go to Execute</button></a>
        </div>
      {/if}
    {/if}
  </div>
</div>
{/if}

<style>
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
  margin-top: 1rem;
}
.stat-card {
  background: #fff;
  border: 1px solid #dde1e9;
  border-radius: 10px;
  padding: 1.25rem;
}
.stat-value { font-size: 2rem; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 0.8rem; color: #6b7280; margin-top: 0.2rem; }
.progress-bar { height: 4px; background: #e5e7eb; border-radius: 2px; overflow: hidden; margin-top: 0.5rem; }
.progress-fill { height: 100%; background: #0057b7; transition: width 0.3s; }
.hub-progress-list { display: flex; flex-direction: column; gap: 0.5rem; }
.hub-progress-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.6rem 0.875rem;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}
.hub-info { display: flex; align-items: center; gap: 0.5rem; min-width: 160px; }
.hub-name { font-size: 0.875rem; font-weight: 500; font-family: monospace; }
.layer-tag-sm { font-size: 0.68rem; background: #eff6ff; color: #1e40af; border-radius: 4px; padding: 0.1em 0.4em; }
.hub-bars { flex: 1; display: flex; gap: 1rem; align-items: center; }
.mini-bar-group { display: flex; align-items: center; gap: 0.35rem; flex: 1; }
.mini-label { font-size: 0.7rem; color: #6b7280; width: 38px; }
.mini-bar { flex: 1; height: 4px; background: #e5e7eb; border-radius: 2px; overflow: hidden; }
.mini-fill.absorb { background: #0057b7; height: 100%; }
.mini-fill.archive { background: #d97706; height: 100%; }
.mini-count { font-size: 0.72rem; color: #6b7280; width: 36px; text-align: right; }
.ghost-note { font-size: 0.72rem; color: #9ca3af; }
.empty-small { color: #9ca3af; font-size: 0.85rem; }
.actions-list { display: flex; flex-direction: column; gap: 0.6rem; }
.action-item { display: flex; align-items: center; gap: 0.75rem; font-size: 0.875rem; }
.action-num { width: 24px; height: 24px; background: #e5e7eb; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600; color: #374151; flex-shrink: 0; }
</style>
