<script>
  // Placeholder — the real Order page arrives in stage 4.
  // This stub exists so the nav link doesn't 404 once stage 3 lands.
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let loading = true;
  let hubs = [];
  let error = '';
  let selectedHub = null;

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    try {
      hubs = await api.getHubs();
    } catch (e) { error = e.message; }
    finally { loading = false; }
  });
</script>

<div class="page-header">
  <h1>Order</h1>
  <p class="sub">Tree-of-Knowledge ordering for hub repos. Coming in the next stage — pick a hub to preview the layout.</p>
</div>

{#if error}<div class="error-msg">{error}</div>{/if}
{#if loading}<p class="loading">Loading hubs…</p>{/if}

{#if !loading && hubs.length === 0}
  <p class="empty">No hubs yet — add one on the <a href="/hubs">Hubs</a> page first.</p>
{/if}

{#if !loading && hubs.length}
  <div class="hub-grid">
    {#each hubs as h}
      <a class="hub-card" href="/order?hub={encodeURIComponent(h.name)}">
        <h3>{h.name}</h3>
        <p class="desc">{h.description || '(no description)'}</p>
        <div class="hub-meta">
          <span class="repo-count">{h.absorbs.length} repos</span>
        </div>
      </a>
    {/each}
  </div>
{/if}

<style>
  .hub-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; }
  .hub-card { display: block; padding: 0.8rem 1rem; border: 1px solid #e5e7eb; border-radius: 8px; text-decoration: none; color: inherit; background: #fff; transition: border-color 0.15s; }
  .hub-card:hover { border-color: #4f46e5; }
  .desc { color: #6b7280; font-size: 0.85rem; }
  .hub-meta { margin-top: 0.5rem; font-size: 0.78rem; color: #9ca3af; }
</style>
