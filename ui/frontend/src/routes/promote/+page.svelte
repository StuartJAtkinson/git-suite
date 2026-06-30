<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let loading = true;
  let errorMsg = '';
  let forks = [];
  let hubs = [];
  let busy = '';          // `${repo}` while a decision is in flight
  let checklists = {};    // repo -> { steps, source } | 'loading'
  let pickHub = {};       // repo -> selected hub ('' = standalone keep)

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true; errorMsg = '';
    try {
      const data = await api.listForks($session.session_id);
      forks = data.forks;
      hubs = data.hubs;
      for (const f of forks) pickHub[f.name] = f.hub || '';
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }

  async function decide(fork, decision) {
    busy = fork.name;
    try {
      const hub = decision === 'promote' ? (pickHub[fork.name] || null) : null;
      await api.decideFork(fork.name, decision, hub);
      fork.verdict = decision === 'drop' ? 'archive' : (hub ? 'absorb' : 'keep');
      fork.hub = hub;
      forks = forks;
    } catch (e) { errorMsg = e.message; }
    finally { busy = ''; }
  }

  async function genChecklist(fork) {
    checklists[fork.name] = 'loading'; checklists = checklists;
    try {
      const res = await api.promoteChecklist(
        $session.session_id, fork.name, pickHub[fork.name] || null,
        fork.parent_full_name || null);
      checklists[fork.name] = res; checklists = checklists;
    } catch (e) {
      checklists[fork.name] = { steps: [`Error: ${e.message}`], source: 'error' };
      checklists = checklists;
    }
  }

  const verdictClass = (v) =>
    v === 'absorb' ? 'v-absorb' : v === 'keep' ? 'v-keep'
    : v === 'archive' ? 'v-archive' : 'v-orphan';
</script>

<div class="page-header">
  <h1>Own — promote forks to first-class repos</h1>
  <p class="sub">
    Step 3. A fork you rely on should become <em>your own</em> repo, not a
    dependency on someone else's tree. GitHub has no API to detach a fork, so
    <strong>promote</strong> records the decision (keep, or absorb into a hub) and
    gives you a git checklist to run; <strong>drop</strong> marks it to archive.
  </p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Loading forks…</p>{/if}

{#if !loading}
<div class="section">
  <div class="section-head"><h2>Owned forks ({forks.length})</h2></div>
  {#if forks.length === 0}
    <p class="empty">No owned forks in the latest scan. (Run a Scan first if this looks wrong.)</p>
  {:else}
    {#each forks as fork (fork.name)}
      <div class="fork">
        <div class="fork-row">
          <span class="fork-name">{fork.name}</span>
          <span class="verdict {verdictClass(fork.verdict)}">
            {fork.verdict}{#if fork.hub} → {fork.hub}{/if}
          </span>
          {#if fork.parent_full_name}
            <span class="parent">forked from {fork.parent_full_name}</span>
          {/if}
          {#if fork.parent_private}
            <span class="warn" title={fork.message}>⚠ upstream private</span>
          {/if}
          {#if fork.cluster}<span class="cluster">⛁ {fork.cluster}</span>{/if}
        </div>
        <div class="fork-actions">
          <select bind:value={pickHub[fork.name]}>
            <option value="">(standalone — keep)</option>
            {#each hubs as h}<option value={h}>→ {h}</option>{/each}
          </select>
          <button class="sm" disabled={busy === fork.name}
                  on:click={() => decide(fork, 'promote')}>Promote</button>
          <button class="sm ghost" disabled={busy === fork.name}
                  on:click={() => decide(fork, 'drop')}>Drop</button>
          <button class="sm" style="margin-left:auto"
                  on:click={() => genChecklist(fork)}>Detach checklist</button>
        </div>
        {#if checklists[fork.name] === 'loading'}
          <p class="loading sm">Generating…</p>
        {:else if checklists[fork.name]}
          <ol class="checklist">
            {#each checklists[fork.name].steps as s}<li>{s}</li>{/each}
          </ol>
          <span class="src">source: {checklists[fork.name].source}</span>
        {/if}
      </div>
    {/each}
  {/if}
</div>
{/if}

<style>
.fork { border: 1px solid #dde1e9; border-radius: 10px; padding: 0.7rem 0.85rem; margin-bottom: 0.7rem; background: #fff; }
.fork-row { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
.fork-name { font-weight: 600; font-family: monospace; }
.verdict { font-size: 0.7rem; border-radius: 4px; padding: 0.1em 0.45em; text-transform: uppercase; letter-spacing: 0.04em; }
.v-absorb { background: #eff6ff; color: #1e40af; }
.v-keep { background: #ecfdf5; color: #047857; }
.v-archive { background: #fef2f2; color: #b91c1c; }
.v-orphan { background: #f3f4f6; color: #6b7280; }
.parent { font-size: 0.78rem; color: #6b7280; }
.warn { font-size: 0.72rem; color: #b45309; background: #fffbeb; border-radius: 4px; padding: 0.1em 0.4em; }
.cluster { font-size: 0.72rem; color: #4b5563; margin-left: auto; }
.fork-actions { display: flex; align-items: center; gap: 0.4rem; margin-top: 0.55rem; }
.fork-actions select { font-size: 0.8rem; padding: 0.2rem 0.4rem; }
.checklist { margin: 0.6rem 0 0.2rem; padding-left: 1.3rem; font-size: 0.85rem; line-height: 1.5; }
.src { font-size: 0.68rem; color: #9ca3af; }
.loading.sm { font-size: 0.8rem; }
</style>
