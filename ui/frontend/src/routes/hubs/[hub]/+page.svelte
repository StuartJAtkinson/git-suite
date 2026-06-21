<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  const hub = $page.params.hub;

  let status = null;     // hub status from API
  let hubMeta = null;    // from /api/hubs
  let loading = true;
  let errorMsg = '';

  // Archive / absorb per-repo loading states
  let archiving = {};
  let absorbing = {};

  // Commercial scrape
  let scrapeUrl = '';
  let scraping = false;
  let scrapeError = '';
  let scrapeResult = null;

  // README
  let preview = '';
  let previewing = false;
  let pushing = false;
  let pushMsg = '';

  // Migration assist
  let migration = null;
  let genning = {};
  let expanded = {};
  let pushingMig = false;
  let migMsg = '';

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true;
    errorMsg = '';
    try {
      const hubs = await api.getHubs();
      hubMeta = hubs.find((h) => h.name === hub);
      status = await api.getHubStatus(hub);
      migration = await api.migrationHub(hub, $session.session_id);
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }

  async function doArchive(repo) {
    archiving = { ...archiving, [repo]: true };
    errorMsg = '';
    try {
      await api.archiveRepo($session.session_id, hub, repo);
      await load();
    } catch (e) {
      errorMsg = `Archive failed for ${repo}: ${e.message}`;
    } finally {
      archiving = { ...archiving, [repo]: false };
    }
  }

  async function doAbsorb(repo) {
    absorbing = { ...absorbing, [repo]: true };
    try {
      await api.markAbsorbed(hub, repo);
      await load();
    } catch (e) {
      errorMsg = e.message;
    } finally {
      absorbing = { ...absorbing, [repo]: false };
    }
  }

  async function doScrape() {
    scraping = true;
    scrapeError = '';
    scrapeResult = null;
    try {
      scrapeResult = await api.scrapeUrl(hub, scrapeUrl);
      scrapeUrl = '';
      await load();
    } catch (e) {
      scrapeError = e.message;
    } finally {
      scraping = false;
    }
  }

  async function removeAlt(kind, name) {
    try {
      await api.removeHubAlternative(hub, name, kind);
      await load();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function deleteRef(ref_id) {
    try {
      await api.deleteRef(ref_id);
      await load();
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function doPreview() {
    previewing = true;
    preview = '';
    try {
      const res = await api.previewReadme(hub, $session.session_id);
      preview = res.section;
    } catch (e) {
      errorMsg = e.message;
    } finally {
      previewing = false;
    }
  }

  async function doPush() {
    pushing = true;
    pushMsg = '';
    errorMsg = '';
    try {
      await api.pushReadme($session.session_id, hub);
      pushMsg = 'README pushed to GitHub.';
    } catch (e) {
      errorMsg = e.message;
    } finally {
      pushing = false;
    }
  }

  async function genChecklist(repo, regenerate = false) {
    genning = { ...genning, [repo]: true };
    errorMsg = '';
    try {
      await api.genChecklist($session.session_id, hub, repo, regenerate);
      migration = await api.migrationHub(hub, $session.session_id);
      expanded = { ...expanded, [repo]: true };
    } catch (e) {
      errorMsg = `Checklist failed for ${repo}: ${e.message}`;
    } finally {
      genning = { ...genning, [repo]: false };
    }
  }

  async function pushMigration() {
    pushingMig = true; migMsg = ''; errorMsg = '';
    try {
      const r = await api.pushMigration($session.session_id, hub);
      migMsg = `Pushed MIGRATION.md (${r.bytes} bytes).`;
    } catch (e) {
      errorMsg = e.message;
    } finally {
      pushingMig = false;
    }
  }

  const LAYER = {
    0: 'Event Bus', 1: 'Ontology', 2: 'Automation', 3: 'Knowledge & RAG',
    4: 'Media', 5: 'GIS & Maps', 6: 'Gaming', 7: 'Dev Tools', 8: 'Homelab',
    9: 'Creative & Graphics',
  };

  // styles for alternative chips live in app.css-adjacent block below
  $: absorbs   = status?.absorbs  ?? [];
  $: archives  = status?.archives ?? [];
  $: refs      = status?.commercial_refs ?? [];
  $: doneAbsorbs  = absorbs.filter(r => r.done).length;
  $: doneArchives = archives.filter(r => r.done).length;
</script>

<!-- Breadcrumb / title -->
<div class="page-header">
  <div class="crumb"><a href="/hubs">Hubs</a> / {hub}</div>
  <h1>{hub}</h1>
  {#if hubMeta}
    <p class="sub">L{hubMeta.layer} — {LAYER[hubMeta.layer] ?? ''} &nbsp;|&nbsp; {hubMeta.description}</p>
  {/if}
</div>

{#if loading}<p class="loading">Loading...</p>{/if}
{#if errorMsg}<div class="error-msg" style="margin-bottom:0.75rem">{errorMsg}</div>{/if}

<!-- ── Absorbs ── -->
{#if absorbs.length}
<div class="section">
  <div class="section-head">
    <h2>Absorbs — {doneAbsorbs}/{absorbs.length} done</h2>
  </div>
  <div class="repo-list">
    {#each absorbs as item}
      <div class="repo-row" class:done={item.done}>
        <span class="repo-name">{item.repo}</span>
        {#if item.done}
          <span style="color:#16a34a; font-size:0.85rem;">✓ absorbed</span>
        {:else}
          <button
            class="sm success"
            disabled={absorbing[item.repo]}
            on:click={() => doAbsorb(item.repo)}
          >
            {absorbing[item.repo] ? '...' : 'Mark absorbed'}
          </button>
        {/if}
      </div>
    {/each}
  </div>
</div>
{/if}

<!-- ── Migration assist ── -->
{#if migration && migration.absorbs.length}
<div class="section">
  <div class="section-head">
    <h2>Migration plan</h2>
    <button class="sm secondary" disabled={pushingMig} on:click={pushMigration}>
      {pushingMig ? 'Pushing…' : 'Push MIGRATION.md'}
    </button>
  </div>
  {#if migMsg}<div class="ok-msg" style="margin-bottom:0.6rem">{migMsg}</div>{/if}
  <div class="repo-list">
    {#each migration.absorbs as m}
      <div class="mig-item">
        <div class="mig-head">
          <span class="repo-name">{m.repo}</span>
          {#if m.language}<span class="lang-tag">{m.language}</span>{/if}
          <code class="mig-path">{m.path}</code>
          {#if m.done}<span class="mig-badge done">absorbed</span>
          {:else if !m.live}<span class="mig-badge gone">not on GitHub</span>
          {:else}<span class="mig-badge ready">ready</span>{/if}
          <span class="mig-actions">
            {#if m.has_checklist}
              <button class="sm ghost" on:click={() => (expanded = { ...expanded, [m.repo]: !expanded[m.repo] })}>
                {expanded[m.repo] ? 'Hide' : 'Steps'}
              </button>
              <button class="sm ghost" disabled={genning[m.repo]} on:click={() => genChecklist(m.repo, true)}>
                {genning[m.repo] ? '…' : 'Regenerate'}
              </button>
            {:else}
              <button class="sm" disabled={genning[m.repo]} on:click={() => genChecklist(m.repo)}>
                {genning[m.repo] ? 'Generating…' : 'Generate checklist'}
              </button>
            {/if}
          </span>
        </div>
        {#if m.has_checklist && expanded[m.repo]}
          <ol class="mig-steps">
            {#each m.steps as s}<li>{s}</li>{/each}
          </ol>
          {#if m.source}<div class="mig-source">via {m.source}</div>{/if}
        {/if}
      </div>
    {/each}
  </div>
</div>
{/if}

<!-- ── Archive queue ── -->
{#if archives.length}
<div class="section">
  <div class="section-head">
    <h2>Archive queue — {doneArchives}/{archives.length} done</h2>
  </div>
  <div class="repo-list">
    {#each archives as item}
      <div class="repo-row" class:done={item.done}>
        <span class="repo-name">{item.repo}</span>
        {#if item.done}
          <span style="color:#6b7280; font-size:0.85rem;">archived</span>
        {:else}
          <button
            class="sm danger"
            disabled={archiving[item.repo]}
            on:click={() => doArchive(item.repo)}
          >
            {archiving[item.repo] ? '...' : 'Archive'}
          </button>
        {/if}
      </div>
    {/each}
  </div>
</div>
{/if}

<!-- ── Reference alternatives (from the plan) ── -->
{#if hubMeta?.alternatives && (hubMeta.alternatives.oss?.length || hubMeta.alternatives.commercial?.length)}
<div class="section">
  <div class="section-head"><h2>Reference alternatives</h2></div>
  {#if hubMeta.alternatives.oss?.length}
    <div class="alt-row">
      <span class="alt-label oss">OSS</span>
      <div class="alt-chips">
        {#each hubMeta.alternatives.oss as a}<span class="alt-chip">{a}<button class="chip-x" title="Remove" on:click={() => removeAlt('oss', a)}>×</button></span>{/each}
      </div>
    </div>
  {/if}
  {#if hubMeta.alternatives.commercial?.length}
    <div class="alt-row">
      <span class="alt-label comm">Commercial</span>
      <div class="alt-chips">
        {#each hubMeta.alternatives.commercial as a}<span class="alt-chip">{a}<button class="chip-x" title="Remove" on:click={() => removeAlt('commercial', a)}>×</button></span>{/each}
      </div>
    </div>
  {/if}
</div>
{/if}

<!-- ── Commercial benchmarks (scraped) ── -->
<div class="section">
  <div class="section-head">
    <h2>Commercial benchmarks ({refs.length})</h2>
  </div>

  <!-- Add URL form -->
  <div class="inline-form" style="margin-bottom: 1rem;">
    <input
      type="url"
      bind:value={scrapeUrl}
      placeholder="https://example.com/product"
      on:keydown={(e) => e.key === 'Enter' && scrapeUrl && doScrape()}
    />
    <button disabled={scraping || !scrapeUrl} on:click={doScrape}>
      {scraping ? 'Scraping...' : 'Add URL'}
    </button>
  </div>
  {#if scrapeError}<div class="error-msg" style="margin-bottom:0.5rem">{scrapeError}</div>{/if}
  {#if scrapeResult}
    <div class="ok-msg" style="margin-bottom:0.5rem">
      Added: <strong>{scrapeResult.name}</strong> — {scrapeResult.features.length} features extracted
    </div>
  {/if}

  {#if refs.length === 0}
    <p class="empty">No commercial refs yet. Paste a product URL above to scrape features.</p>
  {:else}
    {#each refs as ref}
      <div class="ref-card">
        <div class="ref-head">
          <div>
            <h4>{ref.name}</h4>
            <div class="ref-url">{ref.url}</div>
          </div>
          <button class="sm danger" on:click={() => deleteRef(ref.id)}>Remove</button>
        </div>
        {#if ref.features.length}
          <ul>
            {#each ref.features as f}<li>{f}</li>{/each}
          </ul>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<!-- ── README ── -->
<div class="section">
  <div class="section-head"><h2>Integration Roadmap README</h2></div>
  <div class="actions-row">
    <button class="secondary" disabled={previewing} on:click={doPreview}>
      {previewing ? 'Loading...' : 'Preview section'}
    </button>
    <button class="success" disabled={pushing} on:click={doPush}>
      {pushing ? 'Pushing...' : 'Push to GitHub'}
    </button>
  </div>
  {#if pushMsg}<div class="ok-msg" style="margin-top:0.5rem">{pushMsg}</div>{/if}
  {#if preview}
    <div class="preview-box" style="margin-top:0.75rem">{preview}</div>
  {/if}
</div>

<style>
  .alt-row { display: flex; align-items: flex-start; gap: 0.6rem; margin-bottom: 0.5rem; }
  .alt-label { font-size: 0.7rem; font-weight: 700; border-radius: 4px; padding: 0.15em 0.5em; white-space: nowrap; }
  .alt-label.oss { background: #d1fae5; color: #065f46; }
  .alt-label.comm { background: #e0e7ff; color: #3730a3; }
  .alt-chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .alt-chip { font-size: 0.78rem; background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 4px; padding: 0.1rem 0.5rem; display: inline-flex; align-items: center; gap: 0.3rem; }
  .chip-x { background: transparent; border: none; color: #9ca3af; cursor: pointer; padding: 0; font-size: 0.9rem; line-height: 1; }
  .chip-x:hover { color: #dc2626; }

  .mig-item { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 0.55rem 0.75rem; }
  .mig-head { display: flex; align-items: center; gap: 0.55rem; flex-wrap: wrap; }
  .mig-path { font-size: 0.75rem; background: #eef2ff; color: #3730a3; border-radius: 4px; padding: 0.1em 0.4em; }
  .lang-tag { font-size: 0.72rem; background: #eff6ff; color: #1e40af; border-radius: 4px; padding: 0.1em 0.4em; }
  .mig-badge { font-size: 0.7rem; border-radius: 4px; padding: 0.1em 0.45em; font-weight: 600; }
  .mig-badge.ready { background: #dbeafe; color: #1e40af; }
  .mig-badge.done { background: #d1fae5; color: #065f46; }
  .mig-badge.gone { background: #f3f4f6; color: #9ca3af; }
  .mig-actions { margin-left: auto; display: flex; gap: 0.3rem; }
  .mig-steps { margin: 0.6rem 0 0.2rem; padding-left: 1.4rem; font-size: 0.85rem; color: #374151; line-height: 1.5; }
  .mig-steps li { margin-bottom: 0.25rem; }
  .mig-source { font-size: 0.72rem; color: #9ca3af; }
</style>
