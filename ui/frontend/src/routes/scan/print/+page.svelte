<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';
  import { SOURCE_GLYPH } from '$lib/columns';

  // Print-friendly view of the scan records: one card per repo, an even
  // --cols-wide grid (flex-basis, no per-card width games). Everything in a
  // card stacks vertically and is compact by default — only entities and
  // purpose are prose, so only they word-wrap; the card's height is just
  // whatever that content needs, nothing padded out to a fixed row count.
  let owned = [];
  let stars = [];
  let records = {};
  let hubMap = {};
  let loaded = false;
  let cols = 3;
  let fontSize = 100; // % — base size everything else in a card scales from (em-based)
  const SOURCE_ORDER = { owned: 0, fork: 1, star: 2 };

  onMount(() => { if (!$session) goto('/'); load(); });

  async function load() {
    const [scan, s] = await Promise.all([
      api.latestScan($session.session_id).catch(() => null),
      api.getStars().catch(() => ({ stars: [] })),
    ]);
    owned = scan?.repos || [];
    stars = s.stars || [];
    records = (await api.distillRecords($session.session_id).catch(() => ({}))) || {};
    const recon = await api.reconcile($session.session_id).catch(() => ({ repos: [] }));
    hubMap = {};
    for (const r of recon.repos || []) if (r.hub) hubMap[r.name] = r.hub;
    loaded = true;
  }

  $: cols = Math.min(6, Math.max(1, cols || 1));
  $: fontSize = Math.min(300, Math.max(50, fontSize || 100));

  $: cards = [
    ...owned.map((r) => {
      const fn = r.full_name || r.name;
      return {
        key: fn, name: r.name, full_name: fn, source: r.is_fork ? 'fork' : 'owned',
        hub: hubMap[r.name] || r.mid_cat || '', stars: r.stars,
        lang: r.language || '', url: r.url,
        rec: records[fn] || records[r.name] || null,
      };
    }),
    ...stars.map((r) => ({
      key: r.full_name, name: r.name, full_name: r.full_name, source: 'star',
      hub: '', stars: r.stars, lang: r.language || '',
      url: r.full_name ? `https://github.com/${r.full_name}` : '',
      rec: records[r.full_name] || null,
    })),
  ].sort((a, b) =>
    (SOURCE_ORDER[a.source] ?? 9) - (SOURCE_ORDER[b.source] ?? 9)
    || (a.name || '').localeCompare(b.name || ''));
</script>

<div class="no-print toolbar">
  <a href="/scan">&larr; Back to Scan</a>
  <h2>Print preview — {cards.length} repos</h2>
  <label class="cols-field">
    Columns
    <input type="number" min="1" max="6" bind:value={cols} />
  </label>
  <label class="cols-field">
    Font size
    <input type="number" min="50" max="300" step="10" bind:value={fontSize} />%
  </label>
  <button on:click={() => window.print()}>Print / Save as PDF</button>
</div>

{#if loaded}
  <div class="sheet" style="--cols: {cols}; font-size: {fontSize}%">
    {#each cards as c (c.key)}
      <div class="repo-card">
        <div class="repo-card-head">
          <div class="title-block">
            <span class="glyph">{SOURCE_GLYPH[c.source] || ''}</span>
            <span class="name">{c.name}</span>
            {#if c.full_name && c.full_name !== c.name}
              <span class="full-name">({c.full_name})</span>
            {/if}
          </div>
          <span class="stars">&#9733; {c.stars ?? 0}</span>
        </div>
        <div class="tag-row">
          {#if c.rec?.domain}<span class="tag doc">{c.rec.domain}</span>{/if}
          {#if c.hub}<span class="tag arch">{c.hub}</span>{/if}
          {#if c.lang}<span class="lang-tag">{c.lang}</span>{/if}
        </div>
        {#if c.rec?.entities?.length}
          <p class="entities">{c.rec.entities.join(' · ')}</p>
        {/if}
        <p class="purpose">{c.rec?.purpose || '—'}</p>
      </div>
    {/each}
  </div>
{:else}
  <p class="no-print">Loading…</p>
{/if}

<style>
  .toolbar {
    display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;
  }
  .toolbar h2 { margin: 0; flex: 1; font-size: 1rem; color: #374151; }
  .cols-field {
    display: flex; align-items: center; gap: 0.4em;
    font-size: 0.85rem; color: #374151;
  }
  .cols-field input { width: 3.5em; padding: 0.3rem 0.5rem; }

  .sheet {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3cm;
  }
  .repo-card {
    flex: 1 1 calc((100% - (var(--cols, 3) - 1) * 0.3cm) / var(--cols, 3));
    min-width: 0;
    border: 1px solid #e5e7eb; border-radius: 6px; padding: 0.25cm 0.3cm;
    break-inside: avoid; page-break-inside: avoid;
    display: flex; flex-direction: column; gap: 0.1cm;
  }
  .repo-card-head {
    display: flex; align-items: baseline; justify-content: space-between; gap: 0.4em;
    flex-wrap: nowrap; white-space: nowrap; overflow: hidden;
  }
  .title-block {
    display: flex; align-items: baseline; gap: 0.3em;
    min-width: 0; overflow: hidden;
  }
  .title-block .name {
    font-weight: 600; font-size: 0.8em;
    overflow: hidden; text-overflow: ellipsis;
  }
  .full-name {
    font-size: 0.6em; color: #9ca3af;
    overflow: hidden; text-overflow: ellipsis;
  }
  .stars { flex: 0 0 auto; font-size: 0.65em; color: #9ca3af; white-space: nowrap; }

  .tag-row { display: flex; flex-wrap: wrap; gap: 0.2em; }
  /* app.css sets .tag/.lang-tag in rem (root-relative) — override to em here
     so they scale with the Font size control like everything else on the page */
  .tag-row :global(.tag) { font-size: 0.7em; }
  .tag-row :global(.lang-tag) { font-size: 0.72em; }
  .entities { margin: 0; font-size: 0.62em; color: #6b7280; overflow-wrap: break-word; }
  .purpose {
    margin: 0; font-size: 0.7em; color: #374151; line-height: 1.3;
    overflow-wrap: break-word;
  }

  @media print {
    .no-print { display: none !important; }
    @page { size: A4; margin: 1cm; }
    .sheet { gap: 0.25cm; }
    .repo-card { border-color: #ccc; }
  }
</style>
