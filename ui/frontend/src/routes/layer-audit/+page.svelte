<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let loading = true;
  let errorMsg = '';
  let orphans = [];
  let hubs = [];

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true;
    errorMsg = '';
    try {
      // Reconcile is authoritative: hubs come back in emergent order (size).
      const data = await api.reconcile($session.session_id);
      orphans = data.orphans;
      hubs = data.hubs;
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="page-header">
  <h1>Hub Audit</h1>
  <p class="sub">Orphan repos and each hub's members (ordered by hub size).</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Loading scan data...</p>{/if}

{#if !loading}
<div class="section">
  <div class="section-head"><h2>Orphan repos ({orphans.length})</h2></div>
  {#if orphans.length === 0}
    <p class="empty">No orphan repos — all repos are assigned.</p>
  {:else}
    <div class="repo-list">
      {#each orphans as r}
        <div class="repo-row">
          <span class="repo-name">{r.name}</span>
          {#if r.language}<span class="lang-tag">{r.language}</span>{/if}
          <span class="orphan-desc">{r.aim || '(no description)'}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

<div class="section">
  <div class="section-head"><h2>Hubs</h2></div>
  <div class="hub-grid">
    {#each hubs as hub}
      <div class="hub-col">
        <div class="hub-header">
          <span class="hub-name">{hub.name}</span>
          <span class="hub-count">{hub.repos.length} repos</span>
        </div>
        <div class="hub-repos">
          {#if hub.repos.length === 0}
            <span class="empty-small">—</span>
          {:else}
            {#each hub.repos as name}
              <span class="repo-chip">{name}</span>
            {/each}
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>
{/if}

<style>
.hub-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
}
.hub-col {
  background: #fff;
  border: 1px solid #dde1e9;
  border-radius: 10px;
  overflow: hidden;
}
.hub-header {
  background: #1a1a2e;
  color: #fff;
  padding: 0.5rem 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.hub-name { font-size: 0.8rem; font-weight: 500; }
.hub-count { margin-left: auto; font-size: 0.68rem; font-family: monospace; color: #9fb3d8; }
.hub-repos { padding: 0.6rem; display: flex; flex-direction: column; gap: 0.25rem; min-height: 60px; }
.repo-chip {
  font-size: 0.75rem;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  padding: 0.2rem 0.5rem;
  font-family: monospace;
}
.lang-tag {
  font-size: 0.72rem;
  background: #eff6ff;
  color: #1e40af;
  border-radius: 4px;
  padding: 0.1em 0.4em;
}
.orphan-desc { font-size: 0.78rem; color: #6b7280; margin-left: auto; }
.empty-small { color: #9ca3af; font-size: 0.85rem; }
</style>