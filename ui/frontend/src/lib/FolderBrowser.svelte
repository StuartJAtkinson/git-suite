<script>
  import { onMount, createEventDispatcher } from 'svelte';
  import { api } from './api.js';

  export let initialPath = '';
  const dispatch = createEventDispatcher();

  let current = { path: '', parent: null, entries: [] };
  let loading = true;
  let error = '';

  onMount(() => navigate(initialPath || ''));

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
</script>

<div class="overlay" on:click|self={() => dispatch('cancel')} role="dialog" aria-modal="true">
  <div class="modal">

    <div class="header">
      <span class="title">Select folder</span>
      <button class="close" on:click={() => dispatch('cancel')}>✕</button>
    </div>

    <div class="toolbar">
      <button
        class="up"
        disabled={current.parent === null || loading}
        on:click={() => navigate(current.parent)}
      >↑ Up</button>
      <span class="cur-path">{current.path || 'Drives'}</span>
    </div>

    <div class="list">
      {#if loading}
        <div class="msg">Loading…</div>
      {:else if error}
        <div class="msg err">{error}</div>
      {:else if current.entries.length === 0}
        <div class="msg">No subfolders here</div>
      {:else}
        {#each current.entries as entry}
          <button class="entry" on:click={() => navigate(entry.path)}>
            <span class="icon">📁</span>{entry.name}
          </button>
        {/each}
      {/if}
    </div>

    <div class="footer">
      <code class="sel-path">{current.path || ''}</code>
      <div class="btns">
        <button class="cancel" on:click={() => dispatch('cancel')}>Cancel</button>
        <button class="ok" disabled={!current.path} on:click={select}>Select</button>
      </div>
    </div>

  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,.5);
    display: flex; align-items: center; justify-content: center;
    z-index: 999;
  }
  .modal {
    background: #fff; border-radius: 10px;
    width: 500px; max-width: 95vw; max-height: 80vh;
    display: flex; flex-direction: column;
    box-shadow: 0 24px 60px rgba(0,0,0,.3);
    overflow: hidden;
  }
  .header {
    display: flex; align-items: center; justify-content: space-between;
    padding: .75rem 1rem; border-bottom: 1px solid #e5e7eb;
    font-weight: 600;
  }
  .close {
    background: none; border: none; cursor: pointer;
    font-size: 1rem; color: #6b7280; padding: .25rem .4rem;
  }
  .toolbar {
    display: flex; align-items: center; gap: .75rem;
    padding: .5rem 1rem; background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
  }
  .up {
    background: none; border: 1px solid #d1d5db; border-radius: 5px;
    padding: .2rem .6rem; font-size: .82rem; cursor: pointer; white-space: nowrap;
  }
  .up:disabled { opacity: .4; cursor: default; }
  .cur-path {
    font-family: monospace; font-size: .8rem; color: #374151;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .list {
    flex: 1; overflow-y: auto; padding: .4rem .5rem; min-height: 220px;
  }
  .entry {
    display: flex; align-items: center; gap: .5rem;
    width: 100%; padding: .4rem .65rem;
    background: none; border: none; border-radius: 5px;
    text-align: left; font-size: .875rem; cursor: pointer; color: #1a1a2e;
  }
  .entry:hover { background: #eff6ff; color: #1e40af; }
  .icon { font-size: 1rem; }
  .msg { padding: 2rem; text-align: center; color: #9ca3af; font-size: .875rem; }
  .err { color: #dc2626; }
  .footer {
    display: flex; align-items: center; gap: .75rem;
    padding: .65rem 1rem; border-top: 1px solid #e5e7eb; background: #f9fafb;
  }
  .sel-path {
    flex: 1; font-size: .78rem; color: #374151;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .btns { display: flex; gap: .4rem; }
  .cancel {
    padding: .35rem .8rem; border: 1px solid #d1d5db; border-radius: 6px;
    background: #fff; cursor: pointer; font-size: .875rem;
  }
  .ok {
    padding: .35rem .8rem; border-radius: 6px; border: none;
    background: #16a34a; color: #fff; cursor: pointer; font-size: .875rem; font-weight: 500;
  }
  .ok:disabled { opacity: .45; cursor: default; }
</style>
