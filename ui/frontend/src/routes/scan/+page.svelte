<script>
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { session, currentScanId } from '$lib/stores';
  import { api, scanWs } from '$lib/api';
  import { SOURCE_GLYPH } from '$lib/columns';

  // One GitHub pull, three phases shown as they happen: your repos, your forks,
  // your stars. Then ✨ Enrich runs the LLM pass (Fit / Purpose / Domain /
  // Entities). Nothing here clusters — Cluster and Hub columns are read-only,
  // backfilled from later steps.

  let owned = [];          // owned repos (own forks via is_fork)
  let stars = [];          // starred repos
  let headsMap = {};       // full_name -> head row
  let records = {};        // full_name/name -> {purpose, entities, domain}
  let warnings = [];       // repos needing attention (404/403/etc)
  let clusterMap = {};     // name -> cluster label (backfilled from Cluster step)
  let hubMap = {};         // name -> hub (backfilled from the live plan)
  let verdicts = {};       // name -> fit | drift | mis-clustered | ''
  let verdictClusterHash = '';
  let verdictCounts = { fit: 0, drift: 0, 'mis-clustered': 0, skipped: 0 };

  let status = 'idle';     // idle | pulling | done | error
  let phase = '';          // 'repos' | 'forks' | 'stars'
  let forkCount = 0;
  let starCount = 0;
  let pullErrors = [];     // per-phase failures, surfaced (no silent swallow)
  let enrichStatus = '';   // '' | 'running' | 'done'
  let enrichMsg = '';
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
      await loadBackfill();
      refreshMeta();
      status = 'done';
    } catch (e) { /* stay idle */ }
  }

  async function loadBackfill() {
    // Read-only: saved clustering (Cluster column) + live plan hub (Hub column).
    // saved_only never triggers a clustering compute.
    const [c, recon] = await Promise.all([
      api.getClusters($session.session_id, { savedOnly: true }).catch(() => ({ available: false })),
      api.reconcile($session.session_id).catch(() => ({ repos: [] })),
    ]);
    clusterMap = {}; hubMap = {};
    if (c.available) {
      for (const cl of c.clusters)
        for (const m of cl.members) clusterMap[m.repo] = cl.suggested_name;
    }
    for (const r of recon.repos || []) if (r.hub) hubMap[r.name] = r.hub;
    clusterMap = clusterMap; hubMap = hubMap;
  }

  async function refreshMeta() {
    try {
      const [h, rec, v] = await Promise.all([
        api.heads($session.session_id).catch(() => ({ heads: [] })),
        api.distillRecords($session.session_id).catch(() => ({})),
        api.verdicts($session.session_id).catch(() => ({ verdicts: {} })),
      ]);
      headsMap = {}; warnings = [];
      for (const row of h.heads || []) {
        headsMap[row.full_name] = row;
        if (row.issue || row.status && row.status >= 400) warnings = [...warnings, row];
      }
      records = rec || {};
      verdicts = v.verdicts || {};
      verdictClusterHash = v.cluster_hash || '';
    } catch (e) { /* non-fatal */ }
  }

  // The GitHub pull: repos (streamed) -> forks -> stars.
  function startPull() {
    status = 'pulling'; phase = 'repos';
    owned = []; stars = []; clusterMap = {}; hubMap = {};
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
    // Each phase is independent and surfaces its own error — a stars failure no
    // longer hides behind a forks failure (or vice versa).
    phase = 'forks';
    try { forkCount = (await api.refreshForks($session.session_id)).count ?? 0; }
    catch (e) { pullErrors = [...pullErrors, `Forks pull failed: ${e.message}`]; }

    phase = 'stars';
    try {
      starCount = (await api.refreshStars($session.session_id)).count ?? 0;
      stars = (await api.getStars()).stars || [];
    } catch (e) { pullErrors = [...pullErrors, `Stars pull failed: ${e.message}`]; }

    await loadBackfill();
    await refreshMeta();
    status = 'done';
  }

  // ✨ Enrich — LLM pass: Purpose/Domain/Entities (distill) + Fit (revalidate).
  async function enrich() {
    enrichStatus = 'running';
    enrichMsg = 'Enriching — distilling Purpose / Domain / Entities…';
    try {
      const d = await api.distill($session.session_id);
      let m = d.stop_reason
        ? `Distill stopped: ${d.stop_reason} (${d.done}/${d.total}).`
        : `Distilled ${d.done}/${d.total} repos.`;
      enrichMsg = m + ' Checking cluster Fit…';
      const v = await api.revalidate($session.session_id);
      if (v.counts) verdictCounts = v.counts;
      verdictClusterHash = v.cluster_hash || '';
      m += verdictClusterHash
        ? ` Fit: ${verdictCounts.fit} ✓ · ${verdictCounts.drift} ↘ · ${verdictCounts['mis-clustered']} ✗.`
        : ' Fit pending — run the Cluster step, then Enrich again.';
      enrichMsg = m;
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
        verdict: verdicts[r.name] || '',
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
        verdict: verdicts[r.name] || '',
      };
    }),
  ];

  $: counts = records_view.reduce((a, r) => (a[r.source] = (a[r.source] || 0) + 1, a), {});
</script>

<div class="page-header">
  <h1>GitHub Pull</h1>
  <p class="sub">
    One pull, three phases: <strong>your repos</strong>, <strong>your forks</strong>,
    <strong>your stars</strong>. Then <strong>✨ Enrich</strong> runs the LLM pass
    that fills <em>Fit · Purpose · Domain · Entities</em>.
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
    <a href="/cluster"><button class="success">Next: Cluster →</button></a>
  </div>
  {#if enrichMsg}<div class="info-msg" style="margin-top:0.5rem">{enrichMsg}</div>{/if}
  {#if verdictClusterHash && (verdictCounts.fit + verdictCounts.drift + verdictCounts['mis-clustered']) > 0}
    <div class="drift-banner" style="margin-top:0.6rem">
      <span class="vpill v-fit">✓ fit · {verdictCounts.fit}</span>
      <span class="vpill v-drift">↘ drift · {verdictCounts.drift}</span>
      <span class="vpill v-mis">✗ mis-clustered · {verdictCounts['mis-clustered']}</span>
      {#if verdictCounts.skipped}<span class="vpill v-skip">? unjudged · {verdictCounts.skipped}</span>{/if}
      <span class="verdict-hash">snapshot {verdictClusterHash}</span>
    </div>
  {/if}
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
    <p class="sub">Cluster &amp; Hub are read-only here — they fill in once you reach those steps.</p>
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
          <th>Cluster</th>
          <th>Fit</th>
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
          <tr class:warn={r.issue}
              class:drift={r.verdict === 'drift'}
              class:mis={r.verdict === 'mis-clustered'}
              class:fit={r.verdict === 'fit'}>
            <td class="src" title={r.source}>{SOURCE_GLYPH[r.source]}</td>
            <td class="name">
              {#if r.repo_url}
                <a href={r.repo_url} target="_blank" rel="noopener">{r.name}</a>
              {:else}{r.name}{/if}
              {#if r.readme_url}
                <a class="readme" href={r.readme_url} target="_blank" rel="noopener" title="README on GitHub">README</a>
              {/if}
            </td>
            <td class="cluster">{clusterMap[r.name] || '—'}</td>
            <td class="fit">{#if r.verdict}<span class="vpill v-{r.verdict === 'mis-clustered' ? 'mis' : r.verdict}">{r.verdict}</span>{:else}—{/if}</td>
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
  td.cluster { color: #6366f1; font-weight: 600; }
  td.purpose { color: #1e293b; max-width: 280px; }
  td.domain .domain-pill { background: #eef2ff; color: #4338ca; border-radius: 4px; padding: 0.1em 0.45em; font-size: 0.72rem; }
  td.entities { color: #6b7280; max-width: 220px; }
  td.hub { color: #6b7280; }
  td.lang { color: #9ca3af; }
  td.stars { color: #9ca3af; text-align: right; }
  ul.warnlist { list-style: none; padding: 0; margin: 0; }
  ul.warnlist li { padding: 0.35rem 0.5rem; border-bottom: 1px solid #f1f5f9; display: flex; gap: 0.6rem; align-items: baseline; }
  .warn-reason { color: #b45309; font-size: 0.8rem; }

  .vpill { display: inline-block; font-size: 0.7rem; font-weight: 600; padding: 0.1em 0.55em; border-radius: 999px; }
  .vpill.v-fit { background: #dcfce7; color: #166534; }
  .vpill.v-drift { background: #fef3c7; color: #92400e; }
  .vpill.v-mis  { background: #fee2e2; color: #991b1b; }
  .vpill.v-skip { background: #f1f5f9; color: #475569; }
  .drift-banner { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
    padding: 0.5rem 0.7rem; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 0.82rem; }
  .verdict-hash { margin-left: auto; color: #9ca3af; font-family: monospace; font-size: 0.72rem; }
  tr.fit td.fit .vpill { box-shadow: 0 0 0 1px #bbf7d0; }
  tr.drift td { background: #fffbeb; }
  tr.drift:hover td { background: #fef3c7; }
  tr.mis td { background: #fef2f2; }
  tr.mis:hover td { background: #fee2e2; }
</style>
