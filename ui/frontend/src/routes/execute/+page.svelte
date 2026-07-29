<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // Philosophy #4: planning is cheap; execution is deliberate. Dry-run preview
  // of every outward action, explicit confirm for the destructive one, then
  // batch-apply. Idempotent — already-done items are skipped.

  let preview = null;
  let loading = true;
  let errorMsg = '';
  let msg = '';

  // archive (destructive — needs confirm)
  let selArchive = new Set();
  let confirmed = false;
  let runningArchive = false;
  // create hubs (additive)
  let selHubs = new Set();
  let runningHubs = false;
  // push readmes
  let selReadmes = new Set();
  let runningReadmes = false;

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true; errorMsg = ''; confirmed = false;
    try {
      preview = await api.executePreview($session.session_id);
      selArchive = new Set(preview.archive.will_archive.map((i) => i.repo));
      selHubs = new Set(preview.create_hubs);
      selReadmes = new Set(preview.readmes.filter((r) => r.needs_update).map((r) => r.hub));
      await loadMigration();
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  }

  const toggle = (set, key) => { set.has(key) ? set.delete(key) : set.add(key); return new Set(set); };

  async function runArchive() {
    if (!confirmed || selArchive.size === 0) return;
    runningArchive = true; errorMsg = ''; msg = '';
    try {
      const r = await api.executeArchive($session.session_id, [...selArchive]);
      msg = `Archived ${r.archived} repo(s).`;
      await load();
    } catch (e) { errorMsg = e.message; } finally { runningArchive = false; }
  }

  async function runCreateHubs() {
    if (selHubs.size === 0) return;
    runningHubs = true; errorMsg = ''; msg = '';
    try {
      const r = await api.executeCreateHubs($session.session_id, [...selHubs]);
      msg = `Created ${r.created} hub(s).`;
      await load();
    } catch (e) { errorMsg = e.message; } finally { runningHubs = false; }
  }

  async function runPushReadmes() {
    if (selReadmes.size === 0) return;
    runningReadmes = true; errorMsg = ''; msg = '';
    try {
      const r = await api.executePushReadmes($session.session_id, [...selReadmes]);
      msg = `Pushed ${r.pushed} README(s).`;
      await load();
    } catch (e) { errorMsg = e.message; } finally { runningReadmes = false; }
  }

  // finish absorbs (folded in from the old per-hub page — slim: mark-absorbed + push scaffold only)
  let migByHub = {};      // hub -> absorbs[]
  let absBusy = '';       // "hub/repo" in flight
  let pushMigBusy = '';
  // Absorb flow — git runbook for the user to run locally
  let absorbPlanByRepo = {};       // "hub/repo" -> {commands, notes, checklist, ...}
  let absorbBusy = '';
  let absorbOpen = '';             // "hub/repo" whose runbook is expanded
  let absorbUrlByRepo = {};        // "hub/repo" -> source URL the user typed

  async function loadMigration() {
    const hubs = (preview?.hubs_state ?? []).map((h) => h.hub);
    const entries = await Promise.all(hubs.map(async (h) => {
      try { return [h, (await api.migrationHub(h, $session.session_id)).absorbs]; }
      catch { return [h, []]; }
    }));
    migByHub = Object.fromEntries(entries.filter(([, a]) => a.length));
  }

  async function markAbsorbed(hub, repo) {
    absBusy = `${hub}/${repo}`; errorMsg = ''; msg = '';
    try { await api.markAbsorbed(hub, repo); await loadMigration(); }
    catch (e) { errorMsg = e.message; } finally { absBusy = ''; }
  }

  async function pushScaffold(hub) {
    pushMigBusy = hub; errorMsg = ''; msg = '';
    try {
      await api.pushMigration($session.session_id, hub);
      msg = `${hub}: pushed MIGRATION.md.`;
      await loadMigration();
    } catch (e) { errorMsg = e.message; } finally { pushMigBusy = ''; }
  }

  async function genAbsorbPlan(hub, repo) {
    const key = `${hub}/${repo}`;
    const url = absorbUrlByRepo[key] || `https://github.com/<you>/${repo}.git`;
    absorbBusy = key; errorMsg = '';
    try {
      const plan = await api.absorbPlan($session.session_id, { hub, repo, source_url: url });
      absorbPlanByRepo = { ...absorbPlanByRepo, [key]: plan };
      absorbOpen = key;
      msg = `${repo}: absorb plan ready (${plan.commands.length} commands, source=${plan.source}).`;
    } catch (e) { errorMsg = e.message; } finally { absorbBusy = ''; }
  }

  async function fetchAbsorbPlan(hub, repo) {
    const key = `${hub}/${repo}`;
    absorbBusy = key;
    try {
      const plan = await api.getAbsorbPlan(hub, repo, $session.session_id);
      absorbPlanByRepo = { ...absorbPlanByRepo, [key]: plan };
      absorbOpen = key;
    } catch { /* not cached yet — leave closed */ }
    finally { absorbBusy = ''; }
  }

  // hub lifecycle
  let hubBusy = '';
  async function hubAction(hub, action) {
    if (action === 'delete' && !confirm(`Delete the repo "${hub}" on GitHub? It must be archived first; this is irreversible.`)) return;
    if (action === 'archive' && !confirm(`Archive the hub repo "${hub}"?`)) return;
    hubBusy = hub; errorMsg = ''; msg = '';
    try {
      const fn = { archive: api.archiveHubs, return: api.unarchiveHubs, delete: api.deleteHubs }[action];
      const r = await fn($session.session_id, [hub]);
      msg = `${hub}: ${r.results[0].status}`;
      await load();
    } catch (e) { errorMsg = e.message; } finally { hubBusy = ''; }
  }

  $: c = preview?.counts ?? {};
  $: willList = preview?.archive.will_archive ?? [];
</script>

<div class="page-header">
  <h1>Execute</h1>
  <p class="sub">Apply plan decisions to GitHub. Preview is a dry run; nothing happens until you run a group.</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if msg}<div class="ok-msg" style="margin-top:0.6rem;">{msg}</div>{/if}
{#if loading}<p class="loading">Checking live GitHub state…</p>{/if}

{#if !loading && preview}
  <div class="statbar">
    <span class="stat will"><b>{c.will_archive}</b> to archive</span>
    <span class="stat make"><b>{c.create_hubs}</b> hubs to create</span>
    <span class="stat doc"><b>{c.readmes_stale}</b> READMEs stale</span>
    <button class="ghost sm" on:click={load}>↻ Re-check</button>
  </div>

  <!-- ── Archive (destructive) ── -->
  <div class="section">
    <div class="section-head"><h2>Archive ({willList.length})</h2></div>
    {#if willList.length === 0}
      <p class="empty">Nothing to archive — all targets already archived or gone. ✓</p>
    {:else}
      <div class="repo-list">
        {#each willList as i}
          <label class="repo-row sel">
            <input type="checkbox" checked={selArchive.has(i.repo)} on:change={() => (selArchive = toggle(selArchive, i.repo))} />
            <span class="repo-name">{i.repo}</span>
            {#if i.hub}<span class="tag arch">{i.hub}</span>{:else}<span class="tag none">no hub</span>{/if}
            <span class="aim">{i.aim || '(no description)'}</span>
          </label>
        {/each}
      </div>
      <div class="confirm-box">
        <label class="confirm">
          <input type="checkbox" bind:checked={confirmed} />
          I understand this archives {selArchive.size} repo(s) on GitHub.
        </label>
        <button class="danger" disabled={!confirmed || selArchive.size === 0 || runningArchive} on:click={runArchive}>
          {runningArchive ? 'Archiving…' : `Archive ${selArchive.size}`}
        </button>
      </div>
    {/if}
  </div>

  <!-- ── Create hubs (additive) ── -->
  <div class="section">
    <div class="section-head"><h2>Create missing hubs ({preview.create_hubs.length})</h2></div>
    {#if preview.create_hubs.length === 0}
      <p class="empty">All plan hubs exist on GitHub. ✓</p>
    {:else}
      <div class="repo-list">
        {#each preview.create_hubs as h}
          <label class="repo-row sel">
            <input type="checkbox" checked={selHubs.has(h)} on:change={() => (selHubs = toggle(selHubs, h))} />
            <span class="repo-name">{h}</span>
            <span class="tag make">will create (private)</span>
          </label>
        {/each}
      </div>
      <div class="actions-row" style="margin-top:0.75rem;">
        <button class="success" disabled={selHubs.size === 0 || runningHubs} on:click={runCreateHubs}>
          {runningHubs ? 'Creating…' : `Create ${selHubs.size} hub(s)`}
        </button>
      </div>
    {/if}
  </div>

  <!-- ── Push READMEs ── -->
  <div class="section">
    <div class="section-head"><h2>Push hub READMEs ({c.readmes_stale} stale / {preview.readmes.length})</h2></div>
    {#if preview.readmes.length === 0}
      <p class="empty">No existing hubs to document yet — create them first.</p>
    {:else}
      <div class="repo-list">
        {#each preview.readmes as r}
          <label class="repo-row sel" class:dim={!r.needs_update}>
            <input type="checkbox" checked={selReadmes.has(r.hub)} on:change={() => (selReadmes = toggle(selReadmes, r.hub))} />
            <span class="repo-name">{r.hub}</span>
            {#if r.needs_update}
              <span class="tag doc">{r.reason}</span>
            {:else}
              <span class="tag ok">up to date</span>
            {/if}
          </label>
        {/each}
      </div>
      <div class="actions-row" style="margin-top:0.75rem;">
        <button disabled={selReadmes.size === 0 || runningReadmes} on:click={runPushReadmes}>
          {runningReadmes ? 'Pushing…' : `Push ${selReadmes.size} README(s)`}
        </button>
      </div>
    {/if}
  </div>

  <!-- ── Finish absorbs ── -->
  {#if Object.keys(migByHub).length}
  <div class="section">
    <div class="section-head"><h2>Finish absorbs</h2></div>
    <p class="hint">Mark each planned absorb as migrated, or push a MIGRATION.md guide to the hub repo. This is what the old per-hub page tracked.</p>
    {#each Object.entries(migByHub) as [hub, absorbs]}
      {@const done = absorbs.filter((a) => a.done).length}
      <div class="mig-hub">
        <div class="mig-hub-head">
          <span class="repo-name">{hub}</span>
          <span class="tag {done === absorbs.length ? 'ok' : 'doc'}">{done}/{absorbs.length} absorbed</span>
          <button class="sm" style="margin-left:auto" disabled={pushMigBusy === hub} on:click={() => pushScaffold(hub)}>
            {pushMigBusy === hub ? 'Pushing…' : 'Push MIGRATION.md'}
          </button>
        </div>
        <div class="repo-list">
          {#each absorbs as a}
            {@const absorbKey = `${hub}/${a.repo}`}
            <div class="repo-row" class:dim={a.done}>
              <span class="repo-name">{a.repo}</span>
              {#if !a.live}<span class="tag none">not live</span>{/if}
              {#if a.done}
                <span class="tag ok">absorbed</span>
              {:else}
                <input
                  type="text"
                  placeholder={`https://github.com/<you>/${a.repo}.git`}
                  bind:value={absorbUrlByRepo[absorbKey]}
                  class="absorb-url"
                  style="margin-left:auto;font-size:0.72rem;width:18rem;"
                />
                <button class="sm" disabled={absorbBusy === absorbKey} on:click={() => genAbsorbPlan(hub, a.repo)}>
                  {absorbBusy === absorbKey ? '…' : 'Absorb plan'}
                </button>
                <button class="sm" style="margin-left:auto" disabled={absBusy === absorbKey} on:click={() => markAbsorbed(hub, a.repo)}>
                  {absBusy === absorbKey ? '…' : 'Mark absorbed'}
                </button>
              {/if}
            </div>
            {#if absorbOpen === absorbKey && absorbPlanByRepo[absorbKey]}
              {@const p = absorbPlanByRepo[absorbKey]}
              <div class="absorb-runbook">
                <div class="absorb-meta">
                  <span class="tag doc">{p.strategy}</span>
                  <span class="muted">source={p.source_branch} → {p.target_branch}</span>
                  <span class="muted">modules/{p.module}/</span>
                  {#if p.cached}<span class="tag ok">cached</span>{:else}<span class="tag doc">fresh</span>{/if}
                  <button class="sm" style="margin-left:auto" on:click={() => (absorbOpen = '')}>Hide</button>
                </div>
                {#if p.notes?.length}
                  <ul class="absorb-notes">
                    {#each p.notes as n}<li>{n}</li>{/each}
                  </ul>
                {/if}
                <details open>
                  <summary>Runbook ({p.commands.length} lines)</summary>
                  <pre class="absorb-cmds">{p.commands.join('\n')}</pre>
                </details>
                {#if p.checklist?.length}
                  <details>
                    <summary>Post-merge checklist ({p.checklist.length})</summary>
                    <ol class="absorb-checklist">
                      {#each p.checklist as s}<li>{s}</li>{/each}
                    </ol>
                  </details>
                {/if}
                <p class="hint" style="margin-top:0.4rem;">Run the runbook locally — git-suite never runs git for you. Mark the row absorbed when the push lands.</p>
              </div>
            {/if}
          {/each}
        </div>
      </div>
    {/each}
  </div>
  {/if}

  <!-- ── Hub lifecycle ── -->
  {#if preview.hubs_state}
  <div class="section">
    <div class="section-head"><h2>Hub lifecycle</h2></div>
    <p class="hint">Archive empty hub stubs now; later <b>return</b> the one that becomes the real hub, or <b>delete</b> a hub once its content is absorbed (delete requires it be archived first).</p>
    <div class="repo-list">
      {#each preview.hubs_state as h}
        <div class="repo-row">
          <span class="repo-name">{h.hub}</span>
          {#if !h.exists}<span class="tag none">absent</span>
          {:else if h.archived}<span class="tag arch">archived</span>
          {:else}<span class="tag ok">active</span>{/if}
          <span class="hub-life-actions">
            {#if h.exists && !h.archived}
              <button class="sm" disabled={hubBusy === h.hub} on:click={() => hubAction(h.hub, 'archive')}>Archive</button>
            {/if}
            {#if h.exists && h.archived}
              <button class="sm success" disabled={hubBusy === h.hub} on:click={() => hubAction(h.hub, 'return')}>Return</button>
              <button class="sm danger" disabled={hubBusy === h.hub} on:click={() => hubAction(h.hub, 'delete')}>Delete</button>
            {/if}
          </span>
        </div>
      {/each}
    </div>
  </div>
  {/if}
{/if}

<style>
  .statbar { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.75rem; }
  .stat { font-size: 0.8rem; padding: 0.2rem 0.55rem; border-radius: 5px; background: #eef1f6; color: #374151; }
  .stat.will { background: #fef3c7; color: #92400e; }
  .stat.make { background: #dcfce7; color: #166534; }
  .stat.doc { background: #e0e7ff; color: #3730a3; }
  .stat b { font-size: 0.95rem; }
  .repo-row.sel { cursor: pointer; gap: 0.6rem; }
  .repo-row.sel input { width: auto; }
  .repo-row.dim { opacity: 0.55; }
  .tag { font-size: 0.7rem; border-radius: 4px; padding: 0.1em 0.45em; font-family: monospace; }
  .tag.arch { background: #fef3c7; color: #92400e; }
  .tag.make { background: #dcfce7; color: #166534; }
  .tag.doc { background: #e0e7ff; color: #3730a3; }
  .tag.ok { background: #d1fae5; color: #065f46; }
  .tag.none { background: #f3f4f6; color: #9ca3af; }
  .aim { font-size: 0.78rem; color: #6b7280; margin-left: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 45%; }
  .confirm-box { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: 1rem; padding: 0.9rem 1.1rem; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; }
  .confirm { flex-direction: row; align-items: center; gap: 0.5rem; font-weight: 500; color: #92400e; }
  .confirm input { width: auto; }
  .hint { font-size: 0.8rem; color: #6b7280; margin: 0 0 0.75rem; }
  .hub-life-actions { margin-left: auto; display: flex; gap: 0.3rem; }
  .mig-hub { margin-bottom: 0.9rem; }
  .mig-hub-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem; }
  .absorb-runbook { margin: 0.4rem 0 0.6rem 1.1rem; padding: 0.7rem 0.9rem; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 0.82rem; }
  .absorb-meta { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.4rem; }
  .absorb-cmds { background: #0f172a; color: #e2e8f0; padding: 0.6rem 0.8rem; border-radius: 5px; font-size: 0.75rem; line-height: 1.4; overflow-x: auto; margin: 0.4rem 0 0; }
  .absorb-notes { margin: 0.2rem 0 0.5rem 1.1rem; color: #475569; }
  .absorb-checklist { margin: 0.3rem 0 0 1.3rem; }
  .absorb-url { padding: 0.18rem 0.4rem; border: 1px solid #e5e7eb; border-radius: 4px; font-family: monospace; background: #fafafa; }
</style>
