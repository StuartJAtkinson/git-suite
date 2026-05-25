<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from './api.js';

  export let initialPath = '';

  const dispatch = createEventDispatcher();

  let current = { path: '', parent: null, dirs: [] };
  let loading = false;
  let error = '';

  onMount(() => navigate(initialPath));

  async function navigate(path) {
    loading = true;
    error = '';
    try {
      current = await api.browse(path);
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  function select() {
    dispatch('select', current.path);
  }

  function cancel() {
    dispatch('cancel');
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="picker-overlay" on:click|self={cancel}>
  <div class="picker-modal">
    <div class="picker-header">
      <span class="picker-title">Select folder</span>
      <button class="ghost sm" on:click={cancel}>✕</button>
    </div>

    <div class="picker-path">
      {#if current.parent !== null}
        <button class="ghost sm" on:click={() => navigate(current.parent)}>↑ Up</button>
      {:else}
        <button class="ghost sm" disabled>↑ Up</button>
      {/if}
      <code>{current.path || 'Drives'}</code>
    </div>

    <div class="picker-list">
      {#if loading}
        <div class="picker-empty">Loading...</div>
      {:else if error}
        <div class="picker-empty" style="color:#dc2626">{error}</div>
      {:else if current.dirs.length === 0}
        <div class="picker-empty">No subdirectories</div>
      {:else}
        {#each current.dirs as dir}
          <button class="picker-dir" on:click={() => navigate(dir.path)}>
            <span class="folder-icon">📁</span>
            <span>{dir.name}</span>
          </button>
        {/each}
      {/if}
    </div>

    <div class="picker-footer">
      <span style="font-size:0.8rem; color:#6b7280; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
        {current.path || ''}
      </span>
      <button class="ghost sm" on:click={cancel}>Cancel</button>
      <button class="sm success" disabled={!current.path} on:click={select}>
        Select
      </button>
    </div>
  </div>
</div>

<style>
  .picker-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .picker-modal {
    background: #fff;
    border-radius: 10px;
    width: 480px;
    max-width: 95vw;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.25);
    overflow: hidden;
    max-height: 80vh;
  }

  .picker-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.85rem 1rem;
    border-bottom: 1px solid #e5e7eb;
  }

  .picker-title {
    font-weight: 600;
    font-size: 0.95rem;
  }

  .picker-path {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 1rem;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    font-size: 0.82rem;
  }

  .picker-path code {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #374151;
  }

  .picker-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.4rem 0.5rem;
    min-height: 200px;
  }

  .picker-dir {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.45rem 0.65rem;
    background: transparent;
    color: #1a1a2e;
    border: none;
    border-radius: 5px;
    text-align: left;
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.1s;
  }

  .picker-dir:hover {
    background: #eff6ff;
    color: #1e40af;
  }

  .folder-icon { font-size: 1rem; }

  .picker-empty {
    padding: 2rem;
    text-align: center;
    color: #9ca3af;
    font-size: 0.875rem;
    font-style: italic;
  }

  .picker-footer {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-top: 1px solid #e5e7eb;
    background: #f9fafb;
  }
</style>
