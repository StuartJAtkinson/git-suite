<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let hubs = [];
  let archiveState = {}; // hub -> { repo: bool }
  let loading = true;
  let errorMsg = '';
  let archivingHub = null;

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true;
    errorMsg = '';
    try {
      hubs = await api.getHubs();
      // Load all hub statuses in parallel
      await Promise.all(hubs.map(async (h) => {
        try {
          h._status = await api.getHubStatus(h.name);
        } catch (e) {
          h._status = { archives: [] };
        }
      }));
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }

  async function archiveRepo(hubName, repo) {
    archiveState[`${hubName}:${repo}`] = true;
    errorMsg = '';
    try {
      await api.archiveRepo($session.session_id, hubName, repo);
      const hub = hubs.find(h => h.name === hubName);
      if (hub?._status) {
        const item = hub._status.archives.find(a => a.repo === repo);
        if (item) item.done = true;
      }
    } catch (e) {
      errorMsg = `Archive failed for ${repo}: ${e.message}`;
    } finally {
      archiveState[`${hubName}:${repo}`] = false;
    }
  }

  async function archiveAll(hubName) {
    archivingHub = hubName;
    const hub = hubs.find(h => h.name === hubName);
    const pending = hub?._status?.archives.filter(a => !a.done) ?? [];
    for (const item of pending) {
      await archiveRepo(hubName, item.repo);
    }
    archivingHub = null;
  }

  $: allArchives = hubs.map(h => ({
    hub: h.name,
    layer: h.layer,
    repos: h._status?.archives ?? [],
  })).filter(g => g.repos.length > 0);
</script>

<div class="page-header">
  <h1>Archive Queue</h1>
  <p class="sub">Repos queued for archiving, grouped by target hub.</p>
</div>

{#if errorMsg}<div class="error-msg" style="margin-bottom:1rem">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Loading...</p>{/if}

{#each allArchives as group}
<div class="section">
  <div class="section-head">
    <h2>{group.hub} <span class="layer-tag">L{group.layer}</span></h2>
    {#if group.repos.some(r => !r.done)}
      <button
        class="sm danger"
        disabled={archivingHub === group.hub}
        on:click={() => archiveAll(group.hub)}
      >
        {archivingHub === group.hub ? 'Archiving...' : `Archive all (${group.repos.filter(r => !r.done).length})`}
      </button>
    {/if}
  </div>
  <div class="repo-list">
    {#each group.repos as item}
      <div class="repo-row" class:done={item.done}>
        <span class="repo-name">{item.repo}</span>
        {#if item.done}
          <span style="color:#6b7280;font-size:0.8rem">archived</span>
        {:else}
          <button
            class="sm danger"
            disabled={!!archiveState[`${group.hub}:${item.repo}`]}
            on:click={() => archiveRepo(group.hub, item.repo)}
          >
            {archiveState[`${group.hub}:${item.repo}`] ? '...' : 'Archive'}
          </button>
        {/if}
      </div>
    {/each}
  </div>
</div>
{/each}

{#if !loading && allArchives.length === 0}
<p class="empty">No repos queued for archiving.</p>
{/if}