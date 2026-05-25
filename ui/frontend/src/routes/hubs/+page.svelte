<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let hubs = [];
  let errorMsg = '';
  let loading = true;

  const LAYER = {
    0: 'Event Bus', 1: 'Ontology', 2: 'Automation', 3: 'Knowledge & RAG',
    4: 'Media', 5: 'GIS & Maps', 6: 'Gaming', 7: 'Dev Tools', 8: 'Homelab',
  };
  const PRIORITY = ['', 'Critical', 'High', 'Medium', 'Low'];

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    try {
      hubs = await api.getHubs();
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  });
</script>

<div class="page-header">
  <h1>Hubs</h1>
  <p class="sub">Click a hub to manage absorbs, archives, commercial benchmarks and README.</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Loading hubs...</p>{/if}

<div class="hub-grid">
  {#each hubs as h}
    <a href="/hubs/{h.name}" class="hub-card">
      <div class="hub-layer-tag">L{h.layer} — {LAYER[h.layer] ?? ''}</div>
      <h3>{h.name}</h3>
      <p class="desc">{h.description}</p>
      <div class="hub-meta">
        <span class="repo-count">{h.absorbs.length} repos</span>
        <span class="badge p{h.priority}">{PRIORITY[h.priority]}</span>
      </div>
    </a>
  {/each}
</div>
