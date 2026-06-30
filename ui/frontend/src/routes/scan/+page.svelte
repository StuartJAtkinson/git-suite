<script>
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { session, currentScanId } from '$lib/stores';
  import { api, scanWs } from '$lib/api';
  import { SOURCE_GLYPH } from '$lib/columns';

  // ONE GitHub pull, three phases shown as they happen: your repos, your forks,
  // your stars. Then ✨ Enrich runs the LLM distill (Purpose / Domain /
  // Entities). NOTHING here clusters — clustering is its own explicit step on
  // the Cluster page. Hub is read-only, backfilled from the live plan.

  let owned = [];          // owned repos (own forks via is_fork)
  let stars = [];          // starred repos
  let headsMap = {};       // full_name -> head row
  let records = {};        // full_name/name -> {purpose, entities, domain}
  let warnings = [];       // repos needing attention (404/403/etc)
  let hubMap = {};         // name -> hub (backfilled from the live plan)

  let status = 'idle';     // idle | pulling | done | error
  let phase = '';          // 'repos' | 'forks' | 'stars'
  let forkCount = 0;
  let starCount = 0;
  let pullErrors = [];     // per-phase failures, surfaced (no silent swallow)
  let enrichStatus = '';   // '' | 'running' | 'done'
  let enrichMsg = '';
  let accessStatus = '';   // '' | 'checking' | 'done'  (opt-in heads check)
  let errorMsg = '';
  let ws;

  onMount(() => { if (!$session) goto('/'); rehydrate(); });
  onDestroy(() => { if (ws) ws.close(); });

  async function rehydrate() {
    try {
      const [scan, s] = await Promise.all([
        api.latestScan($session.session_id).catch(() => null),
        api.getStars().catch(() => ({ stars: [] })),
      ]);
      if (!scan?.repos?.length) return;
      owned = scan.repos;
      stars = s.stars || [];
      starCount = stars.length;
      await loadHubs();
      refreshMeta();
      status = 'done';
    } catch (e) { /* stay idle */ }
  }

  async function loadHubs() {
    // Read-only Hub column from the live plan. No clustering, no token spend.
    const recon = await api.reconcile($session.session_id).catch(() => ({ repos: [] }));
    hubMap = {};
    for (const r of recon.repos || []) if (r.hub) hubMap[r.name] = r.hub;
    hubMap = hubMap;
  }

  async function refreshMeta() {
    // Cheap, DB-only. NO per-repo GitHub calls here — `heads` is opt-in below.
    try {
      records = (await api.distillRecords($session.session_id).catch(() => ({}))) || {};
    } catch (e) { /* non-fatal */ }
  }

  // Opt-in: one live GitHub GET per repo AND per star (parent/upstream status,
  // README URL, 403/404 flags). Heavy — kept off the automatic pull so a pull
  // costs ~10 API calls, not ~700. Run it explicitly when you want the
  // "Need attention" panel + README links.
  async function checkAccess() {
    accessStatus = 'checking';
    try {
      const h = await api.heads($session.session_id);
      headsMap = {}; warnings = [];
      for (const row of h.heads || []) {
        headsMap[row.full_name] = row;
        if (row.issue || (row.status && row.status >= 400)) warnings = [...warnings, row];
      }
    } catch (e) { errorMsg = e.message; }
    finally { accessStatus = 'done'; }
  }

  // The GitHub pull: repos (streamed) -> forks -> stars.
  function startPull() {
    status = 'pulling'; phase = 'repos';
    owned = []; stars = []; hubMap = {};
    headsMap = {}; warnings = []; records = {};
    forkCount = 0; starCount = 0; pullErrors = []; enrichMsg = ''; errorMsg = '';
    api.startScan($session.session_id).then(({ scan_id }) => {
      currentScanId.set(scan_id);
      ws = scanWs(
        scan_id,
        (repo) => (owned = [...owned, repo]),
        () => pullForksAndStars(),
        (msg) => { status = 'error'; errorMsg = msg; }
      );
    }).catch((e) => { status = 'error'; errorMsg = e.message; });
  }

  async function pullForksAndStars() {
    // Forks came free with the repos pull (the scan writes the fork table) —
    // no second /user/repos call. Stars need their own /user/starred pull.
    forkCount = owned.filter((r) => r.is_fork).length;

    phase = 'stars';
    try {
      starCount = (await api.refreshStars($session.session_id)).count ?? 0;
      stars = (await api.getStars()).stars || [];
    } catch (e) { pullErrors = [...pullErrors, `Stars pull failed: ${e.message}`]; }

    // The pull is done the moment stars land. Hub backfill + heads/records are
    // background enrichment (heads = one live GitHub GET per repo, can be slow)
    // — don't block the status on them, or it looks frozen on "pulling stars".
    status = 'done';
    loadHubs();
    refreshMeta();
  }

  // ✨ Enrich — LLM distill only: Purpose / Domain / Entities. No clustering.
  async function enrich() {
    enrichStatus = 'running';
    enrichMsg = 'Enriching — distilling Purpose / Domain / Entities…';
    try {
      const d = await api.distill($session.session_id);
      enrichMsg = d.stop_reason
        ? `Distill stopped: ${d.stop_reason} (${d.done}/${d.total}).`
        : `Distilled ${d.done}/${d.total} repos.`;
      await refreshMeta();
    } catch (e) { enrichMsg = e.message; }
    finally { enrichStatus = 'done'; }
  }

  $: repoCount = owned.filter((r) => !r.is_fork).length;
  $: forkFromOwned = owned.filter((r) => r.is_fork).length;

  $: records_view = [
    ...owned.map((r) => {
      const fn = r._full_name || r.name;
      const head = headsMap[fn] || {};
      return {
        key: fn, name: r.name, source: r.is_fork ? 'fork' : 'owned',
        hub: hubMap[r.name] || r.mid_cat || '', language: r.language, stars: r.stars,
        readme_url: head.readme_url || r.url,
        repo_url: head.url || r.url,
        rec: records[fn] || records[r.name] || null,
        issue: head.issue || null,
      };
    }),
    ...stars.map((r) => {
      const fn = r.full_name;
      const head = headsMap[fn] || {};
      return {
        key: fn, name: r.name, source: 'star',
        hub: '', language: r.language, stars: r.stars,
        readme_url: head.readme_url || (fn ? `https://github.com/${fn}/blob/main/README.md` : ''),
        repo_url: head.url || (fn ? `https://github.com/${fn}` : ''),
        rec: records[fn] || null,
        issue: head.issue || (head.status && head.status >= 400 ? 'http_error' : null),
      };
    }),
  ];

  $: counts = records_view.reduce((a, r) => (a[r.source] = (a[r.source] || 0) + 1, a), {});
</script>

<div class="page-header">
  <h1>GitHub Pull</h1>
  <p class="sub">
    One pull, three phases: <strong>your repos</strong>, <strong>your forks</strong>,
    <strong>your stars</strong>. Then <strong>✨ Enrich</strong> distills
    <em>Purpose · Domain · Entities</em>. Clustering is a separate step.
  </p>
</div>

{#if status === 'idle'}
  <button on:click={startPull}>⤓ Pull from GitHub</button>
{:else if status === 'pulling'}
  <div class="info-msg"><span class="spinner">⟳</span>
    {#if phase === 'repos'}Pulling your repos… ({owned.length})
    {:else if phase === 'forks'}Repos {repoCount} ✓ · pulling your forks…
    {:else}Repos {repoCount} ✓ · forks {forkCount} ✓ · pulling your stars…{/if}
  </div>
{:else if status === 'done'}
  <div class="ok-msg">Pulled — {repoCount} repos · {forkFromOwned || forkCount} forks · {stars.length} stars.</div>
  {#each pullErrors as e}<div class="error-msg" style="margin-top:0.4rem">{e}</div>{/each}
  <div class="actions-row">
    <button on:click={startPull} class="secondary">⤓ Re-pull</button>
    <button on:click={enrich} class="primary" disabled={enrichStatus === 'running'}>
      {enrichStatus === 'running' ? 'Enriching…' : '✨ Enrich'}
    </button>
    <button on:click={checkAccess} class="secondary" disabled={accessStatus === 'checking'}
            title="One GitHub request per repo + star — heavier, use sparingly">
      {accessStatus === 'checking' ? 'Checking…' : '🔎 Check access'}
    </button>
    <a href="/cluster"><button class="success">Next: Cluster →</button></a>
  </div>
  {#if enrichMsg}<div class="info-msg" style="margin-top:0.5rem">{enrichMsg}</div>{/if}
{:else}
  <div class="error-msg">{errorMsg}</div>
  <button on:click={startPull} class="secondary" style="margin-top: 0.5rem">Retry</button>
{/if}

{#if warnings.length > 0}
  <div class="section">
    <div class="section-head"><h2>⚠ Need attention ({warnings.length})</h2></div>
    <p class="sub">Repos GitHub couldn't serve a README for — private-upstream forks, archived stars, 403s. Click through to investigate or unstar.</p>
    <ul class="warnlist">
      {#each warnings as w}
        <li>
          <a href={w.url || (w.full_name ? `https://github.com/${w.full_name}` : '#')} target="_blank" rel="noopener">
            {w.full_name}
          </a>
          <span class="warn-reason">{w.message || w.issue || `HTTP ${w.status}`}</span>
        </li>
      {/each}
    </ul>
  </div>
{/if}

{#if records_view.length > 0}
  <div class="section">
    <div class="section-head"><h2>Records ({records_view.length})</h2></div>
    <p class="sub">Hub is read-only here — it fills in once you form hubs on the Cluster step.</p>
    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.6rem;">
      <span class="badge">{SOURCE_GLYPH.owned} owned: {counts.owned || 0}</span>
      <span class="badge">{SOURCE_GLYPH.fork} forks: {counts.fork || 0}</span>
      <span class="badge">{SOURCE_GLYPH.star} stars: {counts.star || 0}</span>
      <span class="badge" style="background:#eef2ff;color:#4338ca">distilled: {Object.keys(records).length}</span>
    </div>
    <table class="records">
      <thead>
        <tr>
          <th></th>
          <th>Repo</th>
          <th>Purpose</th>
          <th>Domain</th>
          <th>Entities</th>
          <th>Hub</th>
          <th>Lang</th>
          <th>★</th>
        </tr>
      </thead>
      <tbody>
        {#each records_view as r}
          <tr class:warn={r.issue}>
            <td class="src" title={r.source}>{SOURCE_GLYPH[r.source]}</td>
            <td class="name">
              {#if r.repo_url}
                <a href={r.repo_url} target="_blank" rel="noopener">{r.name}</a>
              {:else}{r.name}{/if}
              {#if r.readme_url}
                <a class="readme" href={r.readme_url} target="_blank" rel="noopener" title="README on GitHub">README</a>
              {/if}
            </td>
            <td class="purpose">{r.rec?.purpose || '—'}</td>
            <td class="domain">{#if r.rec?.domain}<span class="domain-pill">{r.rec.domain}</span>{:else}—{/if}</td>
            <td class="entities">{r.rec?.entities?.join(' · ') || '—'}</td>
            <td class="hub">{r.hub || ''}</td>
            <td class="lang">{r.language || ''}</td>
            <td class="stars">{r.stars || ''}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  table.records { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
  table.records th { text-align: left; color: #6b7280; font-weight: 600; border-bottom: 2px solid #e5e7eb; padding: 0.3rem 0.5rem; }
  table.records td { border-bottom: 1px solid #f1f5f9; padding: 0.28rem 0.5rem; vertical-align: top; }
  table.records tr:hover td { background: #f8fafc; }
  tr.warn td { background: #fff7ed; }
  tr.warn:hover td { background: #ffedd5; }
  td.src { text-align: center; }
  td.name a { color: #1e293b; font-family: monospace; }
  td.name a.readme { font-size: 0.66rem; color: #6b7280; margin-left: 0.3rem; }
  td.purpose { color: #1e293b; max-width: 280px; }
  td.domain .domain-pill { background: #eef2ff; color: #4338ca; border-radius: 4px; padding: 0.1em 0.45em; font-size: 0.72rem; }
  td.entities { color: #6b7280; max-width: 220px; }
  td.hub { color: #6b7280; }
  td.lang { color: #9ca3af; }
  td.stars { color: #9ca3af; text-align: right; }
  ul.warnlist { list-style: none; padding: 0; margin: 0; }
  ul.warnlist li { padding: 0.35rem 0.5rem; border-bottom: 1px solid #f1f5f9; display: flex; gap: 0.6rem; align-items: baseline; }
  .warn-reason { color: #b45309; font-size: 0.8rem; }
</style>
