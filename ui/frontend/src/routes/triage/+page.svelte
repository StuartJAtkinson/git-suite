<script>
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // Design philosophy #3: the atomic unit of work is one repo needing a
  // verdict. This page is an inbox you process fast — keyboard-first.

  let data = null;          // full reconcile result
  let hubs = [];            // [{name, ...}] in emergent order (from reconcile)
  let loading = true;
  let errorMsg = '';
  let busy = '';            // repo currently being written

  let showDecided = false;  // default: only undecided (orphans)
  let activeIndex = 0;
  let recommendations = {};   // Step 6: repo -> rec object or null (prefetched on load)

  $: queue = data
    ? (showDecided ? data.repos : data.repos.filter((r) => r.verdict === 'orphan'))
    : [];
  $: active = queue[activeIndex] || null;
  $: stats = data?.stats ?? {};

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
    window.addEventListener('keydown', onKey);
  });
  onDestroy(() => {
    if (typeof window !== 'undefined') window.removeEventListener('keydown', onKey);
  });

  async function load() {
    loading = true;
    errorMsg = '';
    try {
      data = await api.reconcile($session.session_id);
      hubs = data.hubs;     // reconcile already returns emergent order
      // Step 6: prefetch recommendations for every orphan in parallel so the
      // card is filled by the time the user clicks into it. One LLM hiccup
      // mustn't break the queue load — allSettled + per-promise catch.
      const orphans = data.repos.filter((r) => r.verdict === 'orphan');
      await Promise.allSettled(orphans.map(async (r) => {
        try {
          const res = await api.getRecommendation($session.session_id, r.name);
          recommendations[r.name] = res.recommendation || null;
        } catch { recommendations[r.name] = null; }
      }));
      recommendations = recommendations;   // trigger reactivity
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }

  async function decide(repo, verdict, hub = null) {
    if (!repo || busy) return;
    busy = repo.name;
    errorMsg = '';
    try {
      await api.setVerdict(repo.name, verdict, hub);
      // local optimistic update so the queue advances instantly
      const prev = repo.verdict;
      repo.verdict = verdict;
      repo.hub = verdict === 'absorb' || verdict === 'archive' ? hub : null;
      if (stats[prev] != null) stats[prev]--;
      if (stats[verdict] != null) stats[verdict]++;
      stats.undecided = data.repos.filter((r) => r.verdict === 'orphan').length;
      data = data; // trigger reactivity
      // keep activeIndex pointing at the next item in the (possibly shrunk) queue
      if (activeIndex >= queue.length) activeIndex = Math.max(0, queue.length - 1);
    } catch (e) {
      errorMsg = e.message;
    } finally {
      busy = '';
    }
  }

  function skip() {
    if (queue.length > 1) activeIndex = (activeIndex + 1) % queue.length;
  }

  function onKey(e) {
    if (!active || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    const k = e.key.toLowerCase();
    if (k === 'a') { decide(active, 'archive', active.hub); e.preventDefault(); }
    else if (k === 'k') { decide(active, 'keep'); e.preventDefault(); }
    else if (k === 'o') { decide(active, 'orphan'); e.preventDefault(); }
    else if (k === 's' || k === 'j') { skip(); e.preventDefault(); }
    else if (/^[1-9]$/.test(k)) {
      const hub = hubs[Number(k) - 1];
      if (hub) { decide(active, 'absorb', hub.name); e.preventDefault(); }
    }
  }
</script>

<div class="page-header">
  <h1>Triage</h1>
  <p class="sub">Give every repo a verdict. Keyboard: <kbd>1–{hubs.length}</kbd> absorb · <kbd>a</kbd> archive · <kbd>k</kbd> keep · <kbd>o</kbd> un-decide · <kbd>s</kbd> skip</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Reconciling plan against latest scan…</p>{/if}

{#if data}
  <div class="statbar">
    <span class="stat"><b>{stats.live}</b> live</span>
    <span class="stat cat-absorb"><b>{stats.absorb}</b> absorb</span>
    <span class="stat cat-archive"><b>{stats.archive}</b> archive</span>
    <span class="stat cat-keep"><b>{stats.keep}</b> keep</span>
    <span class="stat cat-orphan"><b>{stats.undecided}</b> undecided</span>
    <span class="stat ghost-stat"><b>{stats.ghost}</b> ghosts</span>
    <button class="ghost sm" on:click={load}>↻ Re-reconcile</button>
  </div>

  <label class="toggle">
    <input type="checkbox" bind:checked={showDecided} on:change={() => (activeIndex = 0)} />
    Show already-decided repos too
  </label>

  {#if queue.length === 0}
    <div class="ok-msg" style="margin-top:1rem;">✓ Nothing left to triage — every repo has a verdict.</div>
  {:else}
    <!-- Active card -->
    {#if active}
      <div class="active-card">
        <div class="active-head">
          <span class="repo-name big">{active.name}</span>
          {#if active.language}<span class="lang-tag">{active.language}</span>{/if}
          <span class="badge cat-{active.verdict}">{active.label || active.verdict}{active.hub ? ` → ${active.hub}` : ''}</span>
          {#if active.stub_reason}<span class="badge stub-badge" title={active.stub_reason}>stub</span>{/if}
          {#if active.done}<span class="badge done-badge">{active.done}</span>{/if}
          <span class="counter">{activeIndex + 1} / {queue.length}</span>
        </div>
        <p class="active-aim">{active.aim || '(no description)'}</p>
        {#if active.url}<a class="active-url" href={active.url} target="_blank" rel="noreferrer">{active.url}</a>{/if}

        <!-- Step 6: recommendation row. Only for orphan cards — once a
             verdict is set the absorb action doesn't make sense. -->
        {#if active.verdict === 'orphan'}
          {@const rec = recommendations[active.name]}
          {#if active.is_star}
            <div class="recommend-row star-row">
              <span class="rec-mark">⭐</span>
              Starred repo — git-suite can't unstar on your behalf.
              <input class="url-input" readonly value={active.url}
                on:focus={(e) => e.target.select()} />
              <button class="ghost sm" type="button"
                on:click={() => navigator.clipboard?.writeText(active.url)}>Copy URL</button>
            </div>
          {:else if rec && rec.confidence >= 0.7}
            <div class="recommend-row action-row">
              <span class="rec-mark">✅</span>
              <strong>{rec.feature}</strong> fits hub <strong>{rec.target_hub}</strong>
              <span class="conf">confidence {rec.confidence.toFixed(2)}</span>
              <button class="success sm" type="button" disabled={busy === active.name}
                on:click={() => decide(active, 'absorb', rec.target_hub)}>
                Absorb into {rec.target_hub}
              </button>
            </div>
          {:else if rec && rec.confidence >= 0.5}
            <div class="recommend-row hint-row">
              <span class="rec-mark">💡</span>
              <strong>{rec.feature}</strong> fits hub <strong>{rec.target_hub}</strong>
              <span class="conf">confidence {rec.confidence.toFixed(2)}</span>
              <span class="signal-tag">{rec.signal}</span>
            </div>
          {/if}
        {/if}

        <div class="verdict-grid">
          {#each hubs as h, i}
            <button class="hub-btn" disabled={busy === active.name}
              on:click={() => decide(active, 'absorb', h.name)}>
              <span class="key">{i + 1}</span> {h.name}
            </button>
          {/each}
        </div>
        <div class="actions-row" style="margin-top:0.75rem;">
          <button class="archive-btn" disabled={busy === active.name} on:click={() => decide(active, 'archive', active.hub)}>
            <span class="key">a</span> Archive
          </button>
          <button class="success" disabled={busy === active.name} on:click={() => decide(active, 'keep')}>
            <span class="key">k</span> Keep as-is
          </button>
          <button class="ghost" disabled={busy === active.name} on:click={() => decide(active, 'orphan')}>
            <span class="key">o</span> Un-decide
          </button>
          <button class="secondary" on:click={skip}><span class="key">s</span> Skip</button>
        </div>
      </div>
    {/if}

    <!-- Remaining queue -->
    <div class="section">
      <div class="section-head"><h2>Queue ({queue.length})</h2></div>
      <div class="repo-list">
        {#each queue as r, i}
          <div class="repo-row" class:active-row={i === activeIndex} on:click={() => (activeIndex = i)}>
            <span class="repo-name">{r.name}</span>
            {#if r.language}<span class="lang-tag">{r.language}</span>{/if}
            <span class="badge cat-{r.verdict}">{r.label || r.verdict}{r.hub ? ` → ${r.hub}` : ''}</span>
            {#if r.stub_reason}<span class="badge stub-badge" title={r.stub_reason}>stub</span>{/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}
{/if}

<style>
  .statbar { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.75rem; }
  .stat { font-size: 0.8rem; padding: 0.2rem 0.55rem; border-radius: 5px; background: #eef1f6; color: #374151; }
  .stat b { font-size: 0.95rem; }
  .ghost-stat { background: #f3f4f6; color: #6b7280; }
  .toggle { flex-direction: row; align-items: center; gap: 0.4rem; font-weight: 400; color: #6b7280; margin-top: 0.9rem; }
  .toggle input { width: auto; }

  .active-card { background: #fff; border: 2px solid #0057b7; border-radius: 12px; padding: 1.25rem 1.4rem; margin-top: 1rem; box-shadow: 0 4px 18px rgba(0,87,183,0.12); }
  .active-head { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
  .repo-name.big { font-size: 1.15rem; font-weight: 700; flex: none; }
  .counter { margin-left: auto; font-size: 0.8rem; color: var(--quiet-text); }
  .active-aim { color: #4b5563; font-size: 0.9rem; margin: 0.6rem 0 0.3rem; }
  .active-url { font-size: 0.78rem; word-break: break-all; }
  .done-badge { background: #1a1a2e; color: #fff; }
  .stub-badge { background: #fee2e2; color: #991b1b; }

  .verdict-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 0.4rem; margin-top: 1rem; }
  .hub-btn { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; text-align: left; font-size: 0.82rem; }
  .hub-btn:hover:not(:disabled) { background: #dbeafe; }
  .archive-btn { background: #f59e0b; }
  .archive-btn:hover:not(:disabled) { background: #d97706; }
  .key { display: inline-block; min-width: 1.1em; text-align: center; font-family: var(--mono); font-weight: 700; background: rgba(0,0,0,0.12); border-radius: 3px; padding: 0 0.25em; margin-right: 0.35em; font-size: 0.8em; }

  .repo-row { cursor: pointer; }
  .repo-row.active-row { border-color: #0057b7; background: #eff6ff; }
  kbd { font-family: var(--mono); background: var(--border); border-radius: 3px; padding: 0 0.3em; font-size: 0.85em; }

  /* Step 6: recommendation row (one of three) */
  .recommend-row { display: flex; align-items: center; gap: 0.5rem;
                   flex-wrap: wrap; margin-top: 0.6rem; padding: 0.45rem 0.6rem;
                   border-radius: 6px; font-size: 0.85rem; }
  .recommend-row.hint-row    { background: #fefce8; border: 1px solid #fde68a; color: #78350f; }
  .recommend-row.action-row  { background: #ecfdf5; border: 1px solid #a7f3d0; color: #065f46; }
  .recommend-row.star-row    { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
  .rec-mark { font-size: 1rem; }
  .conf    { font-size: 0.75rem; opacity: 0.7; margin-left: auto;
             font-family: var(--mono); }
  .signal-tag { font-size: 0.7rem; background: rgba(0,0,0,0.06); padding: 0 0.4em;
                border-radius: 3px; }
  .url-input { flex: 1; min-width: 12ch; font-size: 0.75rem;
               background: #fff; border: 1px solid #d1d5db; border-radius: 4px;
               padding: 0.2rem 0.4rem; }
</style>
