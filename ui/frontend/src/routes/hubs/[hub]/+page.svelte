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

  const LAYER = {
    0: 'Event Bus', 1: 'Ontology', 2: 'Automation', 3: 'Knowledge & RAG',
    4: 'Media', 5: 'GIS & Maps', 6: 'Gaming', 7: 'Dev Tools', 8: 'Homelab',
  };

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

<!-- ── Commercial benchmarks ── -->
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
