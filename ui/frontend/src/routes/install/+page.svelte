<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // Read-only renderer for Step 8 (Guided installer). git-suite does NOT
  // build or download the hubs — it exports the install plan and the
  // user (or a downstream hub-standards agent) does the rest. This page
  // is the "see what would happen" surface: hand-off copy, the hub DAG
  // in topological install order, and one-click export of the three
  // manifest formats the backend exposes.

  let loading = true;
  let busy = false;
  let error = '';
  let manifest = null;     // JSON manifest from GET /install/{sid}

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    try {
      manifest = await fetchRawManifest();
    } catch (e) { error = e.message; }
    finally { loading = false; }
  });

  async function fetchRawManifest() {
    const r = await fetch(`/api/install/${$session.session_id}`);
    if (!r.ok) throw new Error(await r.text() || r.statusText);
    return r.json();
  }

  async function download(kind) {
    busy = true; error = '';
    try {
      const map = { text: '/text', compose: '/compose' };
      const mime = kind === 'compose'
        ? 'text/x-yaml;charset=utf-8'
        : 'text/plain;charset=utf-8';
      const ext = kind === 'compose' ? 'yaml' : 'txt';
      const r = await fetch(`/api/install/${$session.session_id}${map[kind]}`);
      if (!r.ok) throw new Error(await r.text() || r.statusText);
      const body = await r.text();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([body], { type: mime }));
      a.download = `install-${$session.session_id.slice(0, 8)}-${new Date().toISOString().slice(0, 10)}.${ext}`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { error = e.message; }
    finally { busy = false; }
  }
</script>

<div class="page-header">
  <h1>Install</h1>
  <p class="sub">
    Step 8 — the install plan, exported as a hand-off. git-suite is the
    install <b>brain</b>, not the installer. The hub DAG below is what a
    downstream hub-standards agent (or you) consumes to actually build /
    deploy each hub. Read-only here; nothing on this page pushes to
    GitHub, runs a Dockerfile, or mutates <code>plan.json</code>.
  </p>
</div>

{#if error}<div class="error-msg">{error}</div>{/if}
{#if loading}<p class="loading">Loading…</p>{/if}

{#if !loading}
  {#if !manifest || !manifest.nodes?.length}
    <div class="info-msg" style="max-width:560px;margin:2rem auto;text-align:center">
      No hubs in plan.json. Form one on the <a href="/cluster">Cluster</a>
      page first — Step 8 plans emerge from Step 7's hub DAG.
    </div>
  {:else}
    <div class="bar">
      <span class="meta">
        <b>{manifest.nodes.length}</b> hub{manifest.nodes.length === 1 ? '' : 's'} ·
        generated <code>{manifest.generated_at}</code>
      </span>
      <button disabled={busy} on:click={() => download('text')}>
        {busy ? 'Saving…' : '⬇ Save install order (.txt)'}
      </button>
      <button disabled={busy} on:click={() => download('compose')}>
        ⬇ Save compose fragment (.yaml)
      </button>
      <button disabled={busy} on:click={async () => {
        const r = await fetchRawManifest();                       // re-pull
        const text = JSON.stringify(r, null, 2);
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
        a.download = `install-${$session.session_id.slice(0, 8)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      }}>
        ⬇ Save manifest (.json)
      </button>
    </div>

    <h2>Install order</h2>
    <ol class="install-order">
      {#each manifest.install_order as name, i}
        {@const hub = manifest.nodes.find((n) => n.name === name)}
        {@const deps = manifest.edges.filter((e) => e.to === name).map((e) => e.from)}
        <li>
          <div class="step-head">
            <span class="step-num">{i + 1}.</span> <code>{name}</code>
            <a class="hub-url" href={hub?.url} target="_blank" rel="noopener">↗ GitHub</a>
          </div>
          {#if hub?.description}
            <div class="hub-desc">{hub.description}</div>
          {/if}
          {#if deps.length}
            <div class="hub-deps">depends on: {deps.join(', ')}</div>
          {/if}
          {#if hub?.absorbs?.length}
            <div class="hub-members">
              absorbs ({hub.absorbs.length}):
              {#each hub.absorbs as r}
                <code>{r}</code>
              {/each}
            </div>
          {/if}
        </li>
      {/each}
    </ol>

    {#if manifest.edges?.length}
      <h2>Hub-on-hub edges</h2>
      <p class="muted small">A row appears here only when one hub's name appears as an absorbed repo of another.</p>
      <ul class="edges">
        {#each manifest.edges as e}
          <li><code>{e.from}</code> is a prerequisite of <code>{e.to}</code></li>
        {/each}
      </ul>
    {/if}
  {/if}
{/if}

<style>
  .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem;
    background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 0.65rem 0.85rem; margin-bottom: 1rem; }
  .meta { font-size: 0.84rem; color: #4b5563; flex: 1 1 240px; min-width: 0; }
  .meta code { background: #f3f4f6; padding: 0.05rem 0.35rem;
    border-radius: 3px; font-size: 0.74rem; }

  .install-order { list-style: none; padding: 0; margin: 0; display: flex;
    flex-direction: column; gap: 0.7rem; }
  .install-order li { background: #fff; border: 1px solid #e5e7eb;
    border-radius: 8px; padding: 0.7rem 0.9rem; }
  .step-head { display: flex; align-items: center; gap: 0.5rem; }
  .step-num { font-weight: 700; color: #111827; min-width: 1.7rem; }
  .step-head code { font-size: 1rem; font-weight: 700; color: #4338ca; }
  .hub-url { margin-left: auto; font-size: 0.8rem; text-decoration: none;
    color: #4f46e5; }
  .hub-url:hover { text-decoration: underline; }
  .hub-desc { font-size: 0.86rem; color: #4b5563; margin-top: 0.35rem;
    line-height: 1.45; }
  .hub-deps { font-size: 0.78rem; color: #b45309; margin-top: 0.3rem; }
  .hub-members { font-size: 0.8rem; color: #4b5563; margin-top: 0.4rem;
    display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
  .hub-members code { font-size: 0.74rem; background: #f3f4f6;
    padding: 0.1rem 0.4rem; border-radius: 3px; }

  .edges { list-style: none; padding: 0; margin: 0.5rem 0; }
  .edges li { background: #fffbeb; border: 1px solid #fde68a;
    border-radius: 6px; padding: 0.4rem 0.7rem; margin-bottom: 0.3rem;
    font-size: 0.84rem; }
  .edges code { font-size: 0.84rem; }
</style>
