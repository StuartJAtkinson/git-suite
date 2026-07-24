<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // Refinement surface between the raw scan and hub promotion: the LLM
  // proposes clusters, the user merges/splits/moves/renames until every
  // pair's margin reads comfortably wide, then promotes from Promote/Hubs.

  let data = null;
  let themes = [];             // [{id, suggested_name, suggested_description, members, size, nearest}]
  let orphans = [];            // repos in zero clusters
  let loading = true;
  let busy = false;            // group/import in flight
  let mutating = false;        // merge/split/move/rename/delete in flight
  let exporting = false;
  let exportMsg = '';
  let importing = false;
  let importText = '';
  let showImport = false;
  let errorMsg = '';
  let msg = '';
  let bundleInfo = null;

  let editingId = null;
  let editingValue = '';
  let splitSelect = {};        // clusterId -> Set(memberKey)

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    try {
      data = await api.getClusters($session.session_id, { savedOnly: true });
      if (data) build(data);
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

  async function downloadPrompt() {
    exporting = true; exportMsg = ''; errorMsg = '';
    try {
      const url = `/api/cluster/${$session.session_id}/prompt`;
      const r = await fetch(url);
      if (!r.ok) throw new Error((await r.text()) || r.statusText);
      const text = await r.text();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
      a.download = `themes-prompt-${new Date().toISOString().slice(0,10)}.txt`;
      a.click();
      URL.revokeObjectURL(a.href);
      exportMsg = `Downloaded ${new Blob([text]).size.toLocaleString()} bytes — ` +
                  `feed it to any chat LLM, then paste its JSON reply below.`;
    } catch (e) { errorMsg = e.message; }
    finally { exporting = false; }
  }

  async function importThemes() {
    if (!importText.trim()) return;
    importing = true; errorMsg = ''; msg = '';
    try {
      data = await api.importThemes($session.session_id, importText);
      build(data);
      msg = `Imported: ${themes.length} themes · ${orphans.length} unplaced`;
      importText = ''; showImport = false;
    } catch (e) { errorMsg = e.message; }
    finally { importing = false; }
  }

  function build(d) {
    themes = (d.clusters || []).map((c) => ({
      id: c.id,
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
      })).sort((a, b) => b.stars - a.stars),
      size: c.size ?? (c.members || []).length,
      nearest: c.nearest || null,
    }));
    themes = themes
      .map((t) => ({ ...t, totalStars: t.members.reduce((n, m) => n + (m.stars || 0), 0) }))
      .sort((a, b) => b.totalStars - a.totalStars);
    orphans = (d.orphans_returned || []).map((m) => ({
      repo: m.repo || m.name || m.full_name,
      full_name: m.full_name || m.repo || m.name || '',
      source: m.source || 'owned',
      aim: m.aim || m.description || '',
    }));
    bundleInfo = d.bundle || null;
    splitSelect = {};
  }

  function memberKey(m) { return m.full_name || m.repo; }

  function lowestMargin() {
    let lowest = null;
    for (const t of themes) {
      if (t.nearest && (lowest === null || t.nearest.score < lowest.score)) lowest = t.nearest;
    }
    return lowest;
  }

  async function afterMutation(promise) {
    mutating = true; errorMsg = '';
    try {
      data = await promise;
      build(data);
    } catch (e) { errorMsg = e.message; }
    finally { mutating = false; }
  }

  function startRename(t) { editingId = t.id; editingValue = t.suggested_name; }
  function cancelRename() { editingId = null; editingValue = ''; }
  async function saveRename(t) {
    const name = editingValue.trim();
    editingId = null;
    if (!name || name === t.suggested_name) return;
    await afterMutation(api.renameCluster($session.session_id, t.id, name));
  }

  async function mergeWithNearest(t) {
    if (!t.nearest) return;
    await afterMutation(api.mergeClusters($session.session_id, t.id, t.nearest.id));
  }

  function toggleSplitMember(clusterId, key) {
    const set = splitSelect[clusterId] || new Set();
    if (set.has(key)) set.delete(key); else set.add(key);
    splitSelect = { ...splitSelect, [clusterId]: set };
  }

  async function doSplit(t) {
    const set = splitSelect[t.id];
    if (!set || set.size === 0) return;
    await afterMutation(api.splitCluster($session.session_id, t.id, [...set]));
  }

  async function deleteCluster(t) {
    if (!confirm(`Delete "${t.suggested_name}"? Its ${t.size} member(s) become unplaced.`)) return;
    await afterMutation(api.deleteCluster($session.session_id, t.id));
  }

  async function moveMemberTo(m, fromId, toId) {
    if (!toId || toId === fromId) return;
    await afterMutation(api.moveMember($session.session_id, memberKey(m), fromId, toId));
  }

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
    A refinement surface, not a decision. Group by themes, then merge near-
    duplicates, split bloated clusters, move a stray member, or rename —
    until the lowest margin between any two clusters reads
    <b>wide</b>. Promote hubs from the <a href="/promote">Promote</a> or
    <a href="/hubs">Hubs</a> pages once boundaries feel real.
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
          {#if themes.length > 1}
            {@const low = lowestMargin()}
            {#if low}
              <div class="margin-summary flag-{low.flag}">
                lowest margin: <b>{low.flag}</b> ({(1 - low.score).toFixed(2)} similar)
              </div>
            {/if}
          {/if}
        {:else}
          <span class="muted">Not yet grouped.</span>
        {/if}
      </div>

      <button class="primary" disabled={busy || exporting || mutating} on:click={groupNow}
        title="Bundle the scan + READMEs and ask your configured LLM chain to group by activity, not tech">
        ✨ {busy ? 'Grouping…' : 'Group by themes (use my LLM)'}
      </button>
      <button class="secondary" disabled={busy || exporting} on:click={downloadPrompt}
        title="Download the same prompt as a .txt file so you can paste it into any chat LLM.">
        ⬇ {exporting ? 'Downloading…' : 'Download prompt (.txt)'}
      </button>
      {#if exportMsg}<div class="ok-msg" style="margin:0;font-size:0.74rem">{exportMsg}</div>{/if}

      <button class="secondary" disabled={importing} on:click={() => showImport = !showImport}
        title="Paste the JSON an external LLM returned to build theme cards from it.">
        ↥ Import result
      </button>
      {#if showImport}
        <div class="import-box">
          <textarea bind:value={importText} rows="6"
            placeholder="Paste the themes JSON the external LLM returned…"></textarea>
          <button class="primary" disabled={importing || !importText.trim()} on:click={importThemes}>
            {importing ? 'Importing…' : 'Import'}
          </button>
        </div>
      {/if}

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

      {#if orphans.length}
        <div class="orphans-box">
          <div class="orphans-head">unplaced ({orphans.length})</div>
          {#each orphans as o (memberKey(o))}
            <div class="orphan-row">
              <a class="orphan-name" href={ghUrl(o)} target="_blank" rel="noopener">{o.repo}</a>
              <select disabled={mutating}
                on:change={(e) => { moveMemberTo(o, 'orphans', e.target.value); e.target.value=''; }}>
                <option value="">add to…</option>
                {#each themes as t (t.id)}
                  <option value={t.id}>{t.suggested_name}</option>
                {/each}
              </select>
            </div>
          {/each}
        </div>
      {/if}
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
          {#each themes as t (t.id)}
            <section class="card">
              <div class="margin-bar flag-{t.nearest?.flag || 'wide'}"
                title={t.nearest ? `nearest: ${t.nearest.name} (${t.nearest.flag}, ${(1 - t.nearest.score).toFixed(2)} similar)` : ''}></div>
              <div class="card-body">
                <header class="card-head">
                  {#if editingId === t.id}
                    <input class="name-edit" bind:value={editingValue}
                      on:keydown={(e) => { if (e.key === 'Enter') saveRename(t); if (e.key === 'Escape') cancelRename(); }}
                      on:blur={() => saveRename(t)} autofocus />
                  {:else}
                    <button class="card-title" title="Click to rename" on:click={() => startRename(t)}>
                      {t.suggested_name}
                    </button>
                  {/if}
                  <div class="card-count">{t.size} repo{t.size === 1 ? '' : 's'}
                    {#if t.totalStars}<span class="card-stars">★ {t.totalStars.toLocaleString()}</span>{/if}</div>
                  {#if t.suggested_description}
                    <div class="card-desc">{t.suggested_description}</div>
                  {/if}
                </header>

                <div class="card-actions">
                  {#if t.nearest}
                    <button class="chip" disabled={mutating} on:click={() => mergeWithNearest(t)}
                      title={`Merge with nearest neighbour: ${t.nearest.name}`}>
                      🔗 merge w/ {t.nearest.name}
                    </button>
                  {/if}
                  {#if (splitSelect[t.id]?.size || 0) > 0}
                    <button class="chip" disabled={mutating} on:click={() => doSplit(t)}>
                      ✂ split {splitSelect[t.id].size} off
                    </button>
                  {/if}
                  <button class="chip danger" disabled={mutating} on:click={() => deleteCluster(t)}>
                    🗑 delete
                  </button>
                </div>

                <div class="card-members">
                  {#each t.members as m (memberKey(m))}
                    <div class="cell">
                      <input type="checkbox" class="split-check"
                        checked={splitSelect[t.id]?.has(memberKey(m)) || false}
                        on:change={() => toggleSplitMember(t.id, memberKey(m))}
                        title="Select for split" />
                      <div class="cell-main">
                        <a class="cell-title" href={ghUrl(m)} target="_blank" rel="noopener"
                           title={`Open ${m.full_name || m.repo} on GitHub`}>{m.repo}</a>
                        <div class="cell-sub">
                          {#if m.domain}<span class="domain-pill">{m.domain}</span>{/if}
                          {#if m.stars}<span>★ {m.stars}</span>{/if}
                        </div>
                        {#if m.aim}<div class="cell-desc" title={m.aim}>{m.aim}</div>{/if}
                      </div>
                      <select class="move-select" disabled={mutating}
                        on:change={(e) => { moveMemberTo(m, t.id, e.target.value); e.target.value=''; }}>
                        <option value="">move…</option>
                        {#each themes.filter(x => x.id !== t.id) as x (x.id)}
                          <option value={x.id}>{x.suggested_name}</option>
                        {/each}
                        <option value="orphans">unplaced</option>
                      </select>
                    </div>
                  {/each}
                </div>
              </div>
            </section>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .layout { display: grid; grid-template-columns: 260px 1fr; gap: 1rem;
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
  .margin-summary { margin-top: 0.3rem; font-size: 0.74rem; padding: 0.15rem 0.4rem;
    border-radius: 4px; display: inline-block; }
  .margin-summary.flag-thin { background: #fef2f2; color: #b91c1c; }
  .margin-summary.flag-ok { background: #fffbeb; color: #b45309; }
  .margin-summary.flag-wide { background: #ecfdf5; color: #047857; }

  .primary { background: #4f46e5; color: #fff; border: none; border-radius: 6px;
    padding: 0.6rem 0.75rem; font-size: 0.88rem; font-weight: 700;
    cursor: pointer; width: 100%; }
  .primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .secondary { width: 100%; text-align: center; padding: 0.5rem 0.6rem;
    font-size: 0.82rem; font-weight: 600; }

  .import-box { display: flex; flex-direction: column; gap: 0.4rem; }
  .import-box textarea { width: 100%; font-family: monospace; font-size: 0.72rem;
    padding: 0.4rem; border: 1px solid #e5e7eb; border-radius: 6px; resize: vertical; }
  .import-box .primary { padding: 0.4rem 0.6rem; font-size: 0.8rem; }

  .bundle-info { background: #f8fafc; border: 1px solid #e5e7eb;
    border-radius: 6px; padding: 0.5rem 0.6rem; font-size: 0.76rem;
    color: #374151; display: flex; flex-direction: column; gap: 0.18rem; }
  .bundle-info .muted { font-family: monospace; font-size: 0.66rem;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .saved-pill { font-size: 0.72rem; background: #ecfdf5; color: #047857;
    border: 1px solid #a7f3d0; border-radius: 4px; padding: 0.1rem 0.5rem;
    align-self: flex-start; }

  .orphans-box { border-top: 1px solid #e5e7eb; padding-top: 0.5rem;
    display: flex; flex-direction: column; gap: 0.3rem; max-height: 260px; overflow-y: auto; }
  .orphans-head { font-size: 0.76rem; font-weight: 700; color: #b45309; }
  .orphan-row { display: flex; align-items: center; justify-content: space-between;
    gap: 0.3rem; font-size: 0.74rem; }
  .orphan-name { font-family: monospace; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; max-width: 130px; }
  .orphan-row select { font-size: 0.68rem; max-width: 90px; }

  .stage { border: 1px solid #e5e7eb; border-radius: 10px;
    background: radial-gradient(circle at 1px 1px, #f1f5f9 1px, transparent 0) 0 0 / 22px 22px;
    padding: 1rem; display: flex; flex-wrap: wrap; gap: 1.1rem;
    align-items: flex-start; min-height: 12rem; }
  .card { flex: 1 1 340px; min-width: 340px; max-width: 460px;
    display: flex; background: rgba(255,255,255,0.5); border-radius: 10px;
    border: 1px solid #e5e7eb; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
  .margin-bar { width: 7px; flex-shrink: 0; }
  .margin-bar.flag-thin { background: #ef4444; }
  .margin-bar.flag-ok { background: #f59e0b; }
  .margin-bar.flag-wide { background: #10b981; }

  .card-body { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  .card-head { padding: 0.75rem 0.9rem 0.65rem; border-bottom: 1px solid #e5e7eb;
    background: rgba(255,255,255,0.6); }
  .card-title { font-size: 1rem; font-weight: 800; color: #4338ca;
    text-transform: lowercase; letter-spacing: 0.01em; background: none; border: none;
    padding: 0; cursor: pointer; text-align: left; width: 100%;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .card-title:hover { text-decoration: underline; }
  .name-edit { font-size: 1rem; font-weight: 700; width: 100%; padding: 0.15rem 0.3rem;
    border: 1px solid #4f46e5; border-radius: 4px; }
  .card-count { font-size: 0.74rem; color: #6b7280; margin-top: 0.25rem;
    display: flex; align-items: center; gap: 0.5rem; }
  .card-stars { color: #b45309; font-weight: 600; }
  .card-desc { font-size: 0.8rem; color: #4b5563; margin-top: 0.35rem; line-height: 1.4; }

  .card-actions { display: flex; flex-wrap: wrap; gap: 0.4rem; padding: 0.5rem 0.9rem;
    border-bottom: 1px solid #f1f5f9; }
  .chip { font-size: 0.72rem; padding: 0.22rem 0.65rem; border-radius: 999px;
    border: 1px solid #e5e7eb; background: #f8fafc; cursor: pointer; }
  .chip:disabled { opacity: 0.5; cursor: not-allowed; }
  .chip.danger { color: #b91c1c; border-color: #fecaca; background: #fef2f2; }

  .card-members { overflow-y: auto; padding: 0.6rem;
    display: grid; grid-template-columns: 1fr; row-gap: 0.55rem; max-height: 42rem; }

  .cell { display: flex; align-items: flex-start; gap: 0.5rem; border-radius: 7px;
    padding: 0.65rem 0.75rem; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    border: 2px solid #111827; overflow: hidden; }
  .split-check { margin-top: 0.25rem; flex-shrink: 0; }
  .cell-main { min-width: 0; flex: 1; }
  .cell-title { font-family: monospace; font-size: 0.84rem; font-weight: 600;
    color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    text-decoration: none; display: block; margin-bottom: 0.3rem; }
  .cell-title:hover { color: #4f46e5; text-decoration: underline; }
  .cell-sub { display: flex; gap: 0.55rem; align-items: center; font-size: 0.74rem;
    color: #4b5563; line-height: 1.4; }
  .domain-pill { background: #eef2ff; color: #4338ca; padding: 0.05rem 0.45em;
    border-radius: 3px; font-size: 0.7rem; }
  .cell-desc { font-size: 0.8rem; color: #4b5563; line-height: 1.4;
    margin-top: 0.3rem;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
    overflow: hidden; text-overflow: ellipsis; }
  .move-select { font-size: 0.68rem; max-width: 76px; flex-shrink: 0; align-self: flex-start; }
</style>
