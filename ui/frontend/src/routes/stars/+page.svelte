<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let count = 0;
  let fetchedAt = null;
  let loading = true;
  let refreshing = false;
  let deduping = false;
  let errorMsg = '';
  let dedup = null;          // { method, duplicates, hub_suggestions, star_count }
  let verdictBusy = {};      // repo -> bool

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await loadStatus();
    loading = false;
  });

  async function loadStatus() {
    try {
      const res = await api.getStars();
      count = res.count;
      fetchedAt = res.fetched_at;
    } catch (e) {
      errorMsg = e.message;
    }
  }

  async function refresh() {
    refreshing = true;
    errorMsg = '';
    try {
      const res = await api.refreshStars($session.session_id);
      count = res.count;
      await loadStatus();
    } catch (e) {
      errorMsg = e.message;
    } finally {
      refreshing = false;
    }
  }

  async function runDedup() {
    deduping = true;
    errorMsg = '';
    try {
      dedup = await api.getStarsDedup($session.session_id);
      if (dedup.available === false) errorMsg = dedup.reason || 'Dedup unavailable';
    } catch (e) {
      errorMsg = e.message;
    } finally {
      deduping = false;
    }
  }

  async function archiveMine(dup) {
    verdictBusy[dup.repo] = true;
    try {
      await api.setVerdict(dup.repo, 'archive');
      dup.verdict = 'archive';
      dedup = dedup; // trigger reactivity
    } catch (e) {
      errorMsg = e.message;
    } finally {
      verdictBusy[dup.repo] = false;
    }
  }

  let added = {};   // `${hub}|${full_name}` -> true (accepted into the hub's alternatives)

  async function addAlt(hub, m) {
    const key = `${hub}|${m.full_name}`;
    try {
      await api.addHubAlternative(hub, m.full_name);
      added = { ...added, [key]: true };
    } catch (e) { errorMsg = e.message; }
  }

  $: hubSuggestions = Object.entries(dedup?.hub_suggestions ?? {});
</script>

<div class="page-header">
  <h1>Stars</h1>
  <p class="sub">Starred repos as a dedup input — flag owned repos a starred project already covers, and surface starred alternatives per hub.</p>
</div>

{#if errorMsg}<div class="error-msg" style="margin-bottom:1rem">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Loading…</p>{/if}

{#if !loading}
<div class="section">
  <div class="section-head">
    <h2>Snapshot</h2>
    <button class="sm secondary" disabled={refreshing} on:click={refresh}>
      {refreshing ? 'Fetching stars…' : (count ? 'Refresh stars' : 'Fetch stars')}
    </button>
  </div>
  {#if count}
    <p class="snap-line">{count} starred repos{fetchedAt ? ` · fetched ${fetchedAt}` : ''}</p>
  {:else}
    <p class="empty">No starred snapshot yet — fetch first.</p>
  {/if}
</div>

<div class="section">
  <div class="section-head">
    <h2>Duplication check</h2>
    <div style="display:flex; gap:0.5rem; align-items:center;">
      {#if dedup?.method}
        <span class="method-badge" class:kw={dedup.method === 'keyword'}>
          {dedup.method === 'semantic' ? 'semantic (embeddings)' : 'keyword fallback'}
        </span>
      {/if}
      <button class="sm" disabled={deduping || !count} on:click={runDedup}>
        {deduping ? 'Matching…' : 'Run dedup'}
      </button>
    </div>
  </div>

  {#if dedup && dedup.available !== false}
    {#if dedup.duplicates.length === 0}
      <p class="empty">No owned repo crosses the duplication threshold. Nothing you own is obviously re-implementing something you starred.</p>
    {:else}
      <p class="hint-line">{dedup.duplicates.length} owned repo{dedup.duplicates.length > 1 ? 's' : ''} match a starred project — consider adopting the starred one and archiving yours.</p>
      <div class="dup-list">
        {#each dedup.duplicates as dup}
          <div class="dup-row">
            <div class="dup-owned">
              <span class="repo-name">{dup.repo}</span>
              <span class="verdict-tag {dup.verdict}">{dup.verdict}{dup.hub ? ` → ${dup.hub}` : ''}</span>
              {#if dup.verdict !== 'archive'}
                <button class="sm danger" disabled={!!verdictBusy[dup.repo]}
                  on:click={() => archiveMine(dup)}>
                  {verdictBusy[dup.repo] ? '…' : 'Archive mine'}
                </button>
              {/if}
            </div>
            <div class="dup-matches">
              {#each dup.matches as m}
                <div class="match">
                  <span class="match-score">{m.score}</span>
                  <a href={m.url} target="_blank" rel="noreferrer" class="match-name">{m.full_name}</a>
                  <span class="match-stars">★ {m.stars}</span>
                  {#if m.description}<span class="match-desc">{m.description}</span>{/if}
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {:else if !dedup}
    <p class="empty">Run dedup to match the latest scan against the starred snapshot. Needs a scan; uses embeddings when configured, keyword overlap otherwise.</p>
  {/if}
</div>

{#if hubSuggestions.length > 0}
<div class="section">
  <div class="section-head"><h2>Starred alternatives per hub</h2></div>
  <p class="hint-line">Starred projects whose scope matches a hub — candidates for the hub's OSS-alternatives list (or for adopting instead of building).</p>
  {#each hubSuggestions as [hub, picks]}
    <div class="hub-sugg">
      <span class="hub-name">{hub}</span>
      <div class="sugg-list">
        {#each picks as m}
          <div class="match">
            <span class="match-score">{m.score}</span>
            <a href={m.url} target="_blank" rel="noreferrer" class="match-name">{m.full_name}</a>
            <span class="match-stars">★ {m.stars}</span>
            {#if m.description}<span class="match-desc">{m.description}</span>{/if}
            {#if added[`${hub}|${m.full_name}`]}
              <span class="alt-added">✓ in plan</span>
            {:else}
              <button class="sm ghost alt-add" on:click={() => addAlt(hub, m)}>+ alternative</button>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/each}
</div>
{/if}
{/if}

<style>
.snap-line { font-size: 0.875rem; color: #374151; }
.hint-line { font-size: 0.82rem; color: #6b7280; margin: 0 0 0.75rem; }
.method-badge { font-size: 0.72rem; background: #cffafe; color: #155e75; border-radius: 4px; padding: 0.15em 0.5em; }
.method-badge.kw { background: #fef3c7; color: #92400e; }
.dup-list { display: flex; flex-direction: column; gap: 0.6rem; }
.dup-row { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 0.7rem 0.9rem; }
.dup-owned { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.45rem; }
.repo-name { font-family: monospace; font-size: 0.875rem; font-weight: 600; }
.verdict-tag { font-size: 0.7rem; border-radius: 4px; padding: 0.12em 0.45em; background: #e5e7eb; color: #374151; }
.verdict-tag.archive { background: #fef3c7; color: #92400e; }
.verdict-tag.absorb { background: #dbeafe; color: #1e40af; }
.verdict-tag.keep { background: #dcfce7; color: #166534; }
.verdict-tag.orphan { background: #fee2e2; color: #991b1b; }
.dup-matches, .sugg-list { display: flex; flex-direction: column; gap: 0.25rem; }
.match { display: flex; align-items: baseline; gap: 0.5rem; font-size: 0.8rem; }
.match-score { font-family: monospace; font-size: 0.72rem; color: #0057b7; width: 42px; flex-shrink: 0; }
.match-name { font-family: monospace; font-weight: 500; }
.match-stars { color: #b45309; font-size: 0.72rem; flex-shrink: 0; }
.match-desc { color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alt-add { margin-left: auto; flex-shrink: 0; }
.alt-added { margin-left: auto; flex-shrink: 0; font-size: 0.72rem; color: #16a34a; }
.hub-sugg { display: flex; gap: 1rem; padding: 0.6rem 0.9rem; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 0.5rem; }
.hub-sugg .hub-name { font-family: monospace; font-size: 0.85rem; font-weight: 600; min-width: 140px; }
.sugg-list { flex: 1; }
</style>
