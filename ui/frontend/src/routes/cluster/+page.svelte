<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // The page does ONE thing: send the whole enriched scan to the LLM in one
  // shot and render the resulting theme columns. No promote/remove/reset,
  // no k-means fallback, no orphan sidebar — the user inspects the result,
  // then promotes hubs elsewhere (Promote / Hubs pages).

  let data = null;
  let themes = [];             // [{suggested_name, suggested_description, members, size}]
  let orphans = [];            // repos the LLM didn't place in any theme
  let loading = true;
  let busy = false;
  let exporting = false;
  let exportMsg = '';
  let errorMsg = '';
  let msg = '';
  let bundleInfo = null;       // meta block from themes_bundle (token est, iters)
  const MAX_ROWS_BEFORE_SCROLL = 50;

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    // Rehydrate: ask for the cached result WITHOUT firing the LLM. If there
    // isn't one, the page shows the single CTA button instead of "Loading…".
    try {
      data = await api.getClusters($session.session_id, { savedOnly: true });
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  });

  async function groupNow() {
    busy = true; errorMsg = '';
    try {
      data = null;
      data = await api.getClusters($session.session_id, { recompute: true });
      build(data);
      msg = `${themes.length} themes · ${orphans.length} unplaced`;
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  async function copyPrompt() {
    exporting = true; exportMsg = ''; errorMsg = '';
    try {
      const url = `/api/cluster/${$session.session_id}/prompt`;
      const r = await fetch(url);
      if (!r.ok) throw new Error((await r.text()) || r.statusText);
      const text = await r.text();
      const bytes = new Blob([text]).size;
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        exportMsg = `Copied ${bytes.toLocaleString()} chars to clipboard`;
      } else {
        // Fallback for non-secure-context: download the file
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
        a.download = `themes-prompt-${new Date().toISOString().slice(0,10)}.txt`;
        a.click();
        URL.revokeObjectURL(a.href);
        exportMsg = `Downloaded themes-prompt.txt (${bytes.toLocaleString()} chars)`;
      }
    } catch (e) { errorMsg = e.message; }
    finally { exporting = false; }
  }

  function build(d) {
    themes = (d.clusters || []).map((c) => ({
      suggested_name: c.suggested_name,
      suggested_description: c.suggested_description || '',
      members: (c.members || []).map((m) => ({
        repo: m.repo || m.name || m.full_name,
        full_name: m.full_name || m.repo || m.name || '',
        source: m.source || 'owned',
        stars: m.stars || 0,
        domain: m.domain || '',
        entities: m.entities || [],
        purpose: m.purpose || '',
        aim: m.aim || m.description || '',
      })),
      size: c.size || (c.members || []).length,
    }));
    orphans = (d.orphans_returned || []).map((m) => ({
      repo: m.repo || m.name || m.full_name,
      full_name: m.full_name || m.repo || m.name || '',
      source: m.source || 'owned',
      aim: m.aim || m.description || '',
    }));
    bundleInfo = d.bundle || null;
  }

  // Manual assessment link. Owned/fork → repo; star → the starrer's profile
  // (no repo page exists for a starred item).
  function ghUrl(m) {
    const fn = m.full_name || '';
    if (m.source === 'star') {
      const owner = fn.split('/')[0] || '';
      return owner ? `https://github.com/${owner}` : 'https://github.com';
    }
    if (fn.includes('/')) return `https://github.com/${fn}`;
    return `https://github.com/${m.repo}`;
  }
</script>

<div class="page-header">
  <h1>Themes</h1>
  <p class="sub">
    Two ways to group the scan: <b>✨ use my LLM</b> fires the configured
    provider chain; <b>📋 copy prompt</b> exports the exact system+user prompt
    so you can paste it into any chat LLM (Claude.ai, ChatGPT, Gemini, …).
    The model groups every repo into <strong>themes</strong> — the real-world
    activity, hobby, or line of work the repos serve. <em>Not</em> tech-stack
    buckets (no "python", "data", "tools", "libraries", "APIs"). Read-only
    here; promote hubs from the <a href="/promote">Promote</a> or
    <a href="/hubs">Hubs</a> pages.
  </p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if msg}<div class="ok-msg" style="margin-top:0.6rem">{msg}</div>{/if}
{#if loading}<p class="loading">Loading…</p>{/if}

{#if !loading && data && (!data.available || themes.length || data.saved === false)}
  <div class="layout">
    <aside class="rail">
      <div class="rail-stats">
        {#if data.available}
          <b>{themes.length}</b> themes<br>
          <b>{themes.reduce((n, t) => n + t.size, 0)}</b> grouped<br>
          {#if orphans.length}<span class="stat-orphans">{orphans.length} unplaced</span>{/if}
        {:else}
          <span class="muted">Not yet grouped.</span>
        {/if}
      </div>

      <button class="primary" disabled={busy || exporting} on:click={groupNow}
        title="Bundle the scan + READMEs and ask your configured LLM chain to group by activity, not tech">
        ✨ {busy ? 'Grouping…' : 'Group by themes (use my LLM)'}
      </button>
      <button class="secondary" disabled={busy || exporting} on:click={copyPrompt}
        title="Build the same prompt, but copy it as text so you can paste it into any chat LLM (Claude.ai, ChatGPT, …). Includes the system prompt + full README scrape + clickable links.">
        📋 {exporting ? 'Exporting…' : 'Copy prompt (use external LLM)'}
      </button>
      {#if exportMsg}<div class="ok-msg" style="margin:0;font-size:0.74rem">{exportMsg}</div>{/if}

      {#if bundleInfo}
        <div class="bundle-info">
          <div><b>{bundleInfo.size_bytes?.toLocaleString() || 0}</b> bytes</div>
          <div>target {bundleInfo.target_tokens?.toLocaleString() || 0} tokens
            ({Math.round((bundleInfo.target_tokens || 0)
                         / (bundleInfo.context_window || 1) * 100)}% of
            {bundleInfo.context_window?.toLocaleString() || 0} ctx)</div>
          {#if bundleInfo.iterations?.length}
            <div>{bundleInfo.iterations.length} fit-pass{bundleInfo.iterations.length === 1 ? '' : 'es'}
              · {bundleInfo.iterations.at(-1).tokens.toLocaleString()} final tokens</div>
          {/if}
          {#if bundleInfo.summarised_repos?.length}
            <div>{bundleInfo.summarised_repos.length} README{bundleInfo.summarised_repos.length === 1 ? '' : 's'}
              summarised to fit</div>
          {/if}
          <div class="muted small" title={bundleInfo.path}>saved to {bundleInfo.path}</div>
        </div>
      {/if}

      {#if data.saved}<span class="saved-pill">cached</span>{/if}
    </aside>

    <div class="canvas">
      {#if !data.available}
        <div class="info-msg" style="margin:2rem auto;max-width:520px;text-align:center">
          {data.reason}
        </div>
      {:else if themes.length === 0}
        <p class="empty">No themes — every repo was unplaced.</p>
      {:else}
        <div class="stage">
          {#each themes as t (t.suggested_name)}
            <section class="col">
              <header class="col-head" title={t.suggested_name}>
                <div class="col-label">{t.suggested_name}</div>
                <div class="col-count">{t.size} repo{t.size === 1 ? '' : 's'}</div>
                {#if t.suggested_description}
                  <div class="col-desc">{t.suggested_description}</div>
                {/if}
              </header>
              <div class="col-body"
                style="max-height:{MAX_ROWS_BEFORE_SCROLL * 96}px;">
                {#each t.members as m (m.full_name || m.repo)}
                  <div class="cell">
                    <a class="cell-title" href={ghUrl(m)} target="_blank" rel="noopener"
                       title={`Open ${m.full_name || m.repo} on GitHub`}>{m.repo}</a>
                    <div class="cell-sub">
                      {#if m.domain}<span class="domain-pill">{m.domain}</span>{/if}
                      {#if m.stars}<span>★ {m.stars}</span>{/if}
                    </div>
                    {#if m.aim}<div class="cell-desc" title={m.aim}>{m.aim}</div>{/if}
                  </div>
                {/each}
              </div>
            </section>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .layout { display: grid; grid-template-columns: 240px 1fr; gap: 1rem;
    margin-top: 0.7rem; align-items: start; }

  .rail { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 0.7rem 0.75rem; position: sticky; top: 0.5rem;
    max-height: calc(100vh - 1rem); overflow-y: auto;
    display: flex; flex-direction: column; gap: 0.55rem; }
  .rail-stats { color: #374151; font-size: 0.86rem; line-height: 1.45;
    padding-bottom: 0.45rem; border-bottom: 1px solid #e5e7eb; }
  .stat-orphans { color: #b45309; font-weight: 600; }
  .muted { color: #9ca3af; }
  .small { font-size: 0.74rem; }

  .primary { background: #4f46e5; color: #fff; border: none; border-radius: 6px;
    padding: 0.6rem 0.75rem; font-size: 0.88rem; font-weight: 700;
    cursor: pointer; width: 100%; }
  .primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .secondary { width: 100%; text-align: center; padding: 0.5rem 0.6rem;
    font-size: 0.82rem; font-weight: 600; }

  .bundle-info { background: #f8fafc; border: 1px solid #e5e7eb;
    border-radius: 6px; padding: 0.5rem 0.6rem; font-size: 0.76rem;
    color: #374151; display: flex; flex-direction: column; gap: 0.18rem; }
  .bundle-info .muted { font-family: monospace; font-size: 0.66rem;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .saved-pill { font-size: 0.72rem; background: #ecfdf5; color: #047857;
    border: 1px solid #a7f3d0; border-radius: 4px; padding: 0.1rem 0.5rem;
    align-self: flex-start; }

  .stage { border: 1px solid #e5e7eb; border-radius: 10px;
    background: radial-gradient(circle at 1px 1px, #f1f5f9 1px, transparent 0) 0 0 / 22px 22px;
    padding: 0.6rem; display: flex; flex-wrap: wrap; gap: 0.6rem;
    align-items: flex-start; min-height: 12rem; }
  .col { flex: 1 1 calc(25% - 0.6rem); min-width: 280px; max-width: 100%;
    display: flex; flex-direction: column;
    background: rgba(255,255,255,0.5); border-radius: 8px;
    border: 1px solid #e5e7eb; }
  .col-head { padding: 0.45rem 0.55rem 0.4rem; border-bottom: 1px solid #e5e7eb;
    background: rgba(255,255,255,0.6); border-radius: 8px 8px 0 0; }
  .col-label { font-size: 0.92rem; font-weight: 800; color: #4338ca;
    text-transform: lowercase; letter-spacing: 0.01em;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .col-count { font-size: 0.7rem; color: #6b7280; margin-top: 0.15rem; }
  .col-desc { font-size: 0.76rem; color: #4b5563; margin-top: 0.25rem;
    line-height: 1.35; }
  .col-body { overflow-y: auto; padding: 0.35rem;
    display: grid; grid-template-columns: 1fr; row-gap: 0.35rem; }

  .cell { border-radius: 6px; padding: 0.45rem 0.6rem;
    background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    border: 2px solid #111827; overflow: hidden; }
  .cell-title { font-family: monospace; font-size: 0.78rem; font-weight: 600;
    color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    text-decoration: none; display: block; margin-bottom: 0.2rem; }
  .cell-title:hover { color: #4f46e5; text-decoration: underline; }
  .cell-sub { display: flex; gap: 0.4rem; align-items: center; font-size: 0.7rem;
    color: #4b5563; line-height: 1.4; }
  .domain-pill { background: #eef2ff; color: #4338ca; padding: 0 0.35em;
    border-radius: 3px; font-size: 0.68rem; }
  .cell-desc { font-size: 0.78rem; color: #4b5563; line-height: 1.35;
    margin-top: 0.2rem;
    display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
    overflow: hidden; text-overflow: ellipsis; }
</style>
