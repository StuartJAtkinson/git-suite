<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let hubs = [];
  let errorMsg = '';
  let loading = true;

  // add/edit-hub form. editing = name of the hub being edited (name locked), or '' to add.
  let showAdd = false;
  let saving = false;
  let editing = '';
  let form = { name: '', layer: 3, priority: 3, description: '', boundary: '' };

  const LAYER_NAMES = {
    0: 'Event Bus & Dispatch', 1: 'Ontological Backbone', 2: 'Automation & Workflow',
    3: 'Knowledge & RAG', 4: 'Media & Archiving', 5: 'GIS & Maps',
    6: 'Game & Entertainment', 7: 'Dev & Code Tools', 8: 'Homelab & Infra',
    9: 'Creative & Graphics',
  };
  const PRIORITY = ['', 'Critical', 'High', 'Medium', 'Low'];

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true; errorMsg = '';
    try { hubs = await api.getHubs(); }
    catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  }

  function startEdit(h) {
    editing = h.name;
    form = { name: h.name, layer: h.layer, priority: h.priority,
             description: h.description ?? '', boundary: h.boundary ?? '' };
    showAdd = true;
  }

  function resetForm() {
    form = { name: '', layer: 3, priority: 3, description: '', boundary: '' };
    editing = ''; showAdd = false;
  }

  async function addHub() {
    if (!form.name.trim()) return;
    saving = true; errorMsg = '';
    try {
      await api.upsertHub({ ...form, layer: Number(form.layer), priority: Number(form.priority) });
      resetForm();
      await load();
    } catch (e) { errorMsg = e.message; }
    finally { saving = false; }
  }

  async function removeHub(name) {
    if (!confirm(`Remove the hub "${name}" from the plan? (The GitHub repo is untouched.)`)) return;
    try { await api.removeHub(name); await load(); }
    catch (e) { errorMsg = e.message; }
  }
</script>

<div class="page-header">
  <div class="header-row">
    <div>
      <h1>Hubs</h1>
      <p class="sub">Click a hub to manage absorbs, benchmarks and README. Hubs are plan definitions — add or remove them as the portfolio takes shape.</p>
    </div>
    <button on:click={() => (showAdd ? resetForm() : (showAdd = true))}>{showAdd ? 'Cancel' : '+ Add hub'}</button>
  </div>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}

{#if showAdd}
  <div class="card add-hub">
    <div class="row">
      <label>Name<input bind:value={form.name} placeholder="e.g. media-hub" readonly={!!editing} title={editing ? 'Name is the hub key — create a new hub to rename' : ''} /></label>
      <label>Layer
        <select bind:value={form.layer}>
          {#each Object.entries(LAYER_NAMES) as [n, name]}<option value={n}>L{n} — {name}</option>{/each}
        </select>
      </label>
      <label>Priority
        <select bind:value={form.priority}>
          <option value={1}>Critical</option><option value={2}>High</option>
          <option value={3}>Medium</option><option value={4}>Low</option>
        </select>
      </label>
    </div>
    <label>Description<input bind:value={form.description} placeholder="What this hub unifies" /></label>
    <label>Boundary<textarea rows="2" bind:value={form.boundary} placeholder="Scope: what's in, what's delegated to other hubs (fed to the LLM)"></textarea></label>
    <div><button disabled={saving || !form.name.trim()} on:click={addHub}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Create hub'}</button></div>
  </div>
{/if}

{#if loading}<p class="loading">Loading hubs...</p>{/if}

{#if !loading && hubs.length === 0}
  <p class="empty">No hubs yet — the plan is empty. Add a hub above, then triage repos into it.</p>
{/if}

<div class="hub-grid">
  {#each hubs as h}
    <div class="hub-card-wrap">
      <a href="/hubs/{h.name}" class="hub-card">
        <div class="hub-layer-tag">L{h.layer} — {LAYER_NAMES[h.layer] ?? ''}</div>
        <h3>{h.name}</h3>
        <p class="desc">{h.description}</p>
        <div class="hub-meta">
          <span class="repo-count">{h.absorbs.length} repos</span>
          <span class="badge p{h.priority}">{PRIORITY[h.priority]}</span>
        </div>
      </a>
      <a class="order-link" href="/order?hub={encodeURIComponent(h.name)}" title="Order this hub's repos (Tree of Knowledge layout)">→ Order</a>
      <button class="edit" title="Edit hub meta (layer/priority/description/boundary)" on:click={() => startEdit(h)}>✎</button>
      <button class="del" title="Remove hub from plan" on:click={() => removeHub(h.name)}>✕</button>
    </div>
  {/each}
</div>

<style>
  .header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
  .add-hub { margin: 1rem 0; display: flex; flex-direction: column; gap: 0.6rem; }
  .add-hub .row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .add-hub .row label { flex: 1; min-width: 140px; }
  .add-hub label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.8rem; color: #374151; }
  .hub-card-wrap { position: relative; }
  .del { position: absolute; top: 0.5rem; right: 0.5rem; background: transparent; color: #9ca3af; border: none; padding: 0.1rem 0.4rem; font-size: 0.85rem; cursor: pointer; }
  .del:hover { color: #dc2626; background: #fef2f2; }
  .edit { position: absolute; top: 0.5rem; right: 1.9rem; background: transparent; color: #9ca3af; border: none; padding: 0.1rem 0.4rem; font-size: 0.85rem; cursor: pointer; }
  .edit:hover { color: #4f46e5; background: #eef2ff; }
  .order-link { position: absolute; top: 0.5rem; right: 3.3rem; font-size: 0.78rem; color: #4f46e5; text-decoration: none; padding: 0.15rem 0.45rem; border-radius: 4px; }
  .order-link:hover { background: #eef2ff; }
</style>
