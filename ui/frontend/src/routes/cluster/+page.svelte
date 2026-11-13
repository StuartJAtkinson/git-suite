<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // Clump the portfolio, show the AI's confidence, and answer the clarifying
  // questions it raises until the boundaries settle. One page, read top to
  // bottom: questions, then clumps, then anything still unplaced.

  let data = null;
  let themes = [];             // [{id, name, description, confidence, members, size}]
  let questions = [];          // [{id, question, repos, options}]
  let orphans = [];            // repos the AI left unplaced
  let resolved = [];           // cumulative (question, answer) pairs from prior rounds
  let round = 0;

  let loading = true;
  let busy = false;            // initial grouping in flight
  let refining = false;        // answer → re-group in flight
  let errorMsg = '';
  let msg = '';

  let pending = [];            // answers chosen this round [{question, answer}]
  let chosen = {};             // questionId -> answer (for selected styling)
  let customText = {};         // questionId -> free-text
  let editingId = null;
  let editingValue = '';

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    try {
      data = await api.getClusters($session.session_id, { savedOnly: true });
      if (data) build(data);
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  });

  async function groupNow() {
    busy = true; errorMsg = ''; msg = '';
    try {
      data = await api.getClusters($session.session_id, { recompute: true });
      build(data);
    } catch (e) { errorMsg = e.message; }
    finally { busy = false; }
  }

  async function apply() {
    refining = true; errorMsg = ''; msg = '';
    try {
      data = await api.answerThemes($session.session_id, pending);
      build(data);
      msg = 'Re-grouped with your answers.';
    } catch (e) { errorMsg = e.message; }
    finally { refining = false; }
  }

  function build(d) {
    themes = (d.clusters || []).map((c) => ({
      id: c.id,
      name: c.suggested_name,
      description: c.suggested_description || '',
      confidence: c.confidence ?? null,
      members: (c.members || []).map((m) => ({
        repo: m.repo || m.name || m.full_name,
        full_name: m.full_name || m.repo || m.name || '',
        source: m.source || 'owned',
        stars: m.stars || 0,
        domain: m.domain || '',
        aim: m.aim || m.description || '',
      })).sort((a, b) => b.stars - a.stars),
    })).sort((a, b) => sizeOf(b) - sizeOf(a));

    questions = d.questions || [];
    orphans = (d.orphans_returned || []).map((m) => ({
      repo: m.repo || m.name || m.full_name,
      full_name: m.full_name || m.repo || m.name || '',
      source: m.source || 'owned',
    }));
    resolved = d.answers || [];
    round = d.round || 0;

    pending = [];
    chosen = {};
    customText = {};
    editingId = null;
  }

  function sizeOf(t) { return (t.members || []).length; }

  function setAnswer(q, answer) {
    const a = answer.trim();
    if (!a) return;
    chosen = { ...chosen, [q.id]: a };
    pending = [...pending.filter((p) => p.question !== q.question),
               { question: q.question, answer: a }];
  }

  function submitCustom(q) {
    const v = (customText[q.id] || '').trim();
    if (!v) return;
    setAnswer(q, v);
    customText = { ...customText, [q.id]: '' };
  }

  function conf(c) {
    if (c == null) return { label: 'no score', cls: 'none' };
    if (c >= 0.85) return { label: 'high', cls: 'high' };
    if (c >= 0.65) return { label: 'medium', cls: 'med' };
    return { label: 'low', cls: 'low' };
  }

  function memberKey(m) { return m.full_name || m.repo; }

  function ghUrl(m) {
    const fn = m.full_name || '';
    if (m.source === 'star') {
      const owner = fn.split('/')[0] || '';
      return owner ? `https://github.com/${owner}` : 'https://github.com';
    }
    if (fn.includes('/')) return `https://github.com/${fn}`;
    return `https://github.com/${m.repo}`;
  }

  function startRename(t) { editingId = t.id; editingValue = t.name; }
  function cancelRename() { editingId = null; editingValue = ''; }
  async function saveRename(t) {
    const name = editingValue.trim();
    editingId = null;
    if (!name || name === t.name) return;
    try {
      const d = await api.renameCluster($session.session_id, t.id, name);
      build(d);
    } catch (e) { errorMsg = e.message; }
  }
</script>

<div class="page-header">
  <h1>Cluster</h1>
  <p class="sub">
    Your repos get clumped by the AI, each with a confidence score. Answer its
    clarifying questions to settle the fuzzy boundaries. Promote a clump into a
    real project from the <a href="/promote">Own</a> page once it looks right.
  </p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if msg}<div class="ok-msg" style="margin-top:0.6rem">{msg}</div>{/if}

{#if loading}<p class="loading">Loading…</p>{/if}

{#if !loading}
  <div class="bar">
    {#if !data || !data.available}
      <button disabled={busy} on:click={groupNow}
        title="Ask your LLM to clump every repo by the human activity it serves.">
        ✨ {busy ? 'Clumping…' : 'Clump my repos'}
      </button>
      {#if data?.reason}<span class="hint">{data.reason}</span>{/if}
    {:else}
      <span class="summary">
        <b>{themes.length}</b> clumps · <b>{themes.reduce((n, t) => n + sizeOf(t), 0)}</b> grouped
        {#if orphans.length}<span class="unplaced">· {orphans.length} unplaced</span>{/if}
        {#if resolved.length}<span class="resolved">· {resolved.length} answers</span>{/if}
        {#if round}<span class="muted">· round {round}</span>{/if}
      </span>
      <button class="ghost sm" disabled={busy} on:click={groupNow}
        title="Re-clump from scratch (forget all answers and re-ask).">
        ↻ {busy ? 'Clumping…' : 'Restart'}
      </button>
    {/if}
  </div>

  {#if data?.available}
    {#if questions.length}
      <section class="section">
        <div class="section-head">
          <h2>Things I'm unsure about ({questions.length})</h2>
          <button class="sm" disabled={refining || pending.length === 0} on:click={apply}>
            {refining ? 'Re-clumping…' : `Apply & re-clump${pending.length ? ` (${pending.length})` : ''}`}
          </button>
        </div>

        <div class="questions">
          {#each questions as q (q.id)}
            <div class="q-card">
              <div class="q-text">{q.question}</div>
              {#if q.repos?.length}
                <div class="q-repos">
                  {#each q.repos as r}<span class="q-repo">{r}</span>{/each}
                </div>
              {/if}
              <div class="q-options">
                {#each q.options as opt}
                  <button class="opt {chosen[q.id] === opt ? 'sel' : ''}"
                    disabled={refining}
                    on:click={() => setAnswer(q, opt)}>{opt}</button>
                {/each}
              </div>
              <div class="q-other">
                <input type="text" bind:value={customText[q.id]}
                  placeholder="or say it your own way…"
                  on:keydown={(e) => { if (e.key === 'Enter') submitCustom(q); }} />
                <button class="ghost sm" disabled={refining || !(customText[q.id] || '').trim()}
                  on:click={() => submitCustom(q)}>use</button>
              </div>
            </div>
          {/each}
        </div>
      </section>
    {:else}
      {#if resolved.length}
        <div class="ok-msg">No open questions — boundaries look settled.</div>
      {/if}
    {/if}

    {#if themes.length}
      <div class="clumps">
        {#each themes as t (t.id)}
          <section class="clump">
            <header>
              {#if editingId === t.id}
                <input class="name-edit" bind:value={editingValue}
                  on:keydown={(e) => { if (e.key === 'Enter') saveRename(t); if (e.key === 'Escape') cancelRename(); }}
                  on:blur={() => saveRename(t)} autofocus />
              {:else}
                <button class="clump-title" title="Click to name your ideal project"
                  on:click={() => startRename(t)}>{t.name}</button>
              {/if}
              <span class="conf conf-{conf(t.confidence).cls}"
                title="AI confidence in this clump's membership">
                {conf(t.confidence).label}{t.confidence != null ? ` · ${Math.round(t.confidence * 100)}%` : ''}
              </span>
            </header>
            {#if t.description}<p class="clump-desc">{t.description}</p>{/if}
            <div class="members">
              {#each t.members as m (memberKey(m))}
                <div class="member">
                  <a class="m-name" href={ghUrl(m)} target="_blank" rel="noopener"
                    title={`Open ${m.full_name || m.repo} on GitHub`}>{m.repo}</a>
                  <span class="m-meta">
                    {#if m.domain}<span class="domain-pill">{m.domain}</span>{/if}
                    {#if m.stars}<span>★ {m.stars}</span>{/if}
                  </span>
                  {#if m.aim}<span class="m-aim">{m.aim}</span>{/if}
                </div>
              {/each}
            </div>
          </section>
        {/each}
      </div>
    {/if}

    {#if orphans.length}
      <section class="section">
        <div class="section-head"><h2>Unplaced ({orphans.length})</h2></div>
        <div class="orphans">
          {#each orphans as o (memberKey(o))}
            <a class="orphan" href={ghUrl(o)} target="_blank" rel="noopener">{o.repo}</a>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
{/if}

<style>
  .bar { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
  .summary { font-size: 0.88rem; color: #374151; }
  .unplaced { color: #b45309; font-weight: 600; }
  .resolved { color: var(--muted-text); }

  .section { margin-top: 1.1rem; background: #fff; border: 1px solid var(--border);
    border-radius: 8px; padding: 0.9rem 1rem; }
  .section-head { display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 0.6rem; }
  .section-head h2 { font-size: 1rem; margin: 0; }

  .questions { display: flex; flex-direction: column; gap: 0.6rem; }
  .q-card { border: 1px solid var(--border); border-radius: 8px; padding: 0.7rem 0.8rem; }
  .q-text { font-size: 0.9rem; color: #111827; font-weight: 600; }
  .q-repos { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.4rem; }
  .q-repo { font-family: var(--mono); font-size: 0.72rem; background: #f9fafb;
    border: 1px solid var(--border); border-radius: 4px; padding: 0.05rem 0.4rem; }
  .q-options { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.55rem; }
  .opt { font-size: 0.8rem; padding: 0.32rem 0.7rem; border-radius: 6px;
    border: 1px solid var(--border); background: #fff; cursor: pointer; }
  .opt:hover { border-color: var(--brand); color: var(--brand); }
  .opt.sel { background: var(--brand); color: #fff; border-color: var(--brand); }
  .q-other { display: flex; gap: 0.4rem; margin-top: 0.5rem; }
  .q-other input { flex: 1; font-size: 0.8rem; }

  .clumps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; margin-top: 1.1rem; }
  .clump { background: #fff; border: 1px solid var(--border); border-radius: 10px;
    padding: 0.85rem 0.95rem; display: flex; flex-direction: column; }
  .clump header { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
  .clump-title { font-size: 1rem; font-weight: 700; color: #1e40af; background: none;
    border: none; padding: 0; cursor: pointer; text-align: left; }
  .clump-title:hover { text-decoration: underline; }
  .name-edit { font-size: 1rem; font-weight: 700; flex: 1; padding: 0.15rem 0.3rem;
    border: 1px solid var(--brand); border-radius: 4px; }
  .conf { font-size: 0.7rem; font-weight: 600; border-radius: 4px; padding: 0.1rem 0.45rem;
    white-space: nowrap; }
  .conf-high { background: #f0fdf4; color: #15803d; }
  .conf-med { background: #fef3c7; color: #b45309; }
  .conf-low { background: #fef2f2; color: #dc2626; }
  .conf-none { background: #f3f4f6; color: #4b5563; }
  .clump-desc { font-size: 0.8rem; color: #4b5563; margin: 0.4rem 0 0.5rem; line-height: 1.4; }

  .members { display: flex; flex-direction: column; gap: 0.35rem; }
  .member { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.4rem;
    border: 1px solid #f3f4f6; border-radius: 6px; padding: 0.35rem 0.5rem; }
  .m-name { font-family: var(--mono); font-size: 0.82rem; font-weight: 600;
    color: #111827; text-decoration: none; }
  .m-name:hover { color: var(--brand); text-decoration: underline; }
  .m-meta { display: flex; gap: 0.4rem; align-items: center; font-size: 0.7rem;
    color: #4b5563; }
  .domain-pill { background: var(--info-bg); color: #1e40af; padding: 0.03rem 0.4rem;
    border-radius: 3px; font-size: 0.68rem; }
  .m-aim { font-size: 0.76rem; color: #4b5563; width: 100%;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .orphans { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .orphan { font-family: var(--mono); font-size: 0.78rem; background: #f9fafb;
    border: 1px solid var(--border); border-radius: 4px; padding: 0.15rem 0.5rem;
    color: #374151; text-decoration: none; }
  .orphan:hover { border-color: var(--brand); color: var(--brand); }

  @media (max-width: 900px) { .clumps { grid-template-columns: 1fr; } }
</style>
