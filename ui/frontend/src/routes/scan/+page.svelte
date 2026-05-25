<script>
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { session, currentScanId } from '$lib/stores';
  import { api, scanWs } from '$lib/api';

  let repos = [];
  let status = 'idle'; // idle | scanning | done | error
  let errorMsg = '';
  let ws;

  onMount(() => {
    if (!$session) goto('/');
  });

  onDestroy(() => { if (ws) ws.close(); });

  async function startScan() {
    status = 'scanning';
    repos = [];
    errorMsg = '';
    try {
      const { scan_id } = await api.startScan($session.session_id);
      currentScanId.set(scan_id);
      ws = scanWs(
        scan_id,
        (repo) => (repos = [...repos, repo]),
        () => (status = 'done'),
        (msg) => { status = 'error'; errorMsg = msg; }
      );
    } catch (e) {
      status = 'error';
      errorMsg = e.message;
    }
  }

  $: counts = repos.reduce((acc, r) => {
    acc[r.super_cat] = (acc[r.super_cat] || 0) + 1;
    return acc;
  }, {});

  $: catOrder = ['absorb', 'archive', 'keep', 'orphan'];
</script>

<div class="page-header">
  <h1>Repo Scan</h1>
  <p class="sub">Fetch all your GitHub repos and categorise them against the hub plan.</p>
</div>

{#if status === 'idle'}
  <button on:click={startScan}>Start scan</button>
{:else if status === 'scanning'}
  <div class="info-msg">
    <span class="spinner">⟳</span> Scanning — {repos.length} repos found...
  </div>
  <div class="progress-bar"><div class="progress-fill" style="width: {Math.min(repos.length * 2, 95)}%" /></div>
{:else if status === 'done'}
  <div class="ok-msg">Done — {repos.length} repos scanned and saved.</div>
  <div class="actions-row">
    <button on:click={startScan} class="secondary">Re-scan</button>
    <a href="/hubs"><button class="success">Go to Hubs</button></a>
  </div>
{:else}
  <div class="error-msg">{errorMsg}</div>
  <button on:click={startScan} class="secondary" style="margin-top: 0.5rem">Retry</button>
{/if}

{#if repos.length > 0}
  <div class="section">
    <div class="section-head"><h2>Summary</h2></div>
    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
      {#each catOrder as cat}
        {#if counts[cat]}
          <span class="badge cat-{cat}">{cat}: {counts[cat]}</span>
        {/if}
      {/each}
    </div>
  </div>

  <div class="section">
    <div class="section-head">
      <h2>Repos ({repos.length})</h2>
    </div>
    <div>
      {#each repos as r}
        <div class="scan-row">
          <span class="repo-name" style="flex:1; font-family: monospace; font-size:0.85rem;">{r.name}</span>
          <span class="badge cat-{r.super_cat}">{r.super_cat}</span>
          {#if r.mid_cat}
            <span style="font-size: 0.78rem; color: #6b7280; min-width: 140px;">{r.mid_cat}</span>
          {/if}
          {#if r.language}
            <span style="font-size: 0.78rem; color: #9ca3af; min-width: 80px;">{r.language}</span>
          {/if}
        </div>
      {/each}
    </div>
  </div>
{/if}
