<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  // The re-planning loop (replaces one-shot scoping). Two phases:
  //   incremental — fill in orphans / prune ghosts (until nothing undecided)
  //   replan      — structural advisories unlock once fully planned

  let state = null;
  let proposals = [];
  let history = [];
  let loading = true;
  let running = false;
  let errorMsg = '';
  let busyId = null;

  const KIND_LABEL = {
    verdict: 'verdict', 'ghost-prune': 'ghost', reassign: 'reassign',
    split: 'split', 'new-hub': 'new hub',
  };

  onMount(async () => {
    if (!$session) { goto('/'); return; }
    await load();
  });

  async function load() {
    loading = true; errorMsg = '';
    try {
      [state, proposals, history] = await Promise.all([
        api.replanState($session.session_id),
        api.getProposals(),
        api.replanHistory(),
      ]);
    } catch (e) { errorMsg = e.message; }
    finally { loading = false; }
  }

  async function runPass() {
    running = true; errorMsg = '';
    try {
      const r = await api.runReplanPass($session.session_id);
      proposals = r.proposals;
      state = await api.replanState($session.session_id);
    } catch (e) { errorMsg = e.message; }
    finally { running = false; }
  }

  async function decide(p, accept) {
    busyId = p.id; errorMsg = '';
    try {
      if (accept) await api.acceptProposal(p.id);
      else await api.rejectProposal(p.id);
      proposals = proposals.filter((x) => x.id !== p.id);
      // refresh state + history in the background
      [state, history] = await Promise.all([
        api.replanState($session.session_id),
        api.replanHistory(),
      ]);
    } catch (e) { errorMsg = e.message; }
    finally { busyId = null; }
  }

  async function acceptAllHighConf() {
    const strong = proposals.filter((p) => p.kind === 'verdict' && p.confidence >= 0.7 && p.proposed.hub);
    for (const p of strong) {
      busyId = p.id;
      try { await api.acceptProposal(p.id); proposals = proposals.filter((x) => x.id !== p.id); }
      catch (e) { errorMsg = e.message; break; }
    }
    busyId = null;
    [state, history] = await Promise.all([
      api.replanState($session.session_id), api.replanHistory(),
    ]);
  }

  function fmtProposed(p) {
    if (p.kind === 'verdict' || p.kind === 'reassign')
      return p.proposed.verdict + (p.proposed.hub ? ` → ${p.proposed.hub}` : '');
    if (p.kind === 'ghost-prune') return 'remove from plan';
    return 'advisory';
  }
  function confClass(c) { return c >= 0.7 ? 'hi' : c >= 0.45 ? 'mid' : 'lo'; }
</script>

<div class="page-header">
  <h1>Replan</h1>
  <p class="sub">Iterate the plan: each pass proposes changes from current reality — you review and apply.</p>
</div>

{#if errorMsg}<div class="error-msg">{errorMsg}</div>{/if}
{#if loading}<p class="loading">Loading…</p>{/if}

{#if !loading && state}
  <!-- Phase banner -->
  <div class="phase-banner phase-{state.phase}">
    <div class="phase-tag">{state.phase === 'incremental' ? 'INCREMENTAL' : 'REPLAN'}</div>
    <div class="phase-text">
      {#if state.phase === 'incremental'}
        <b>{state.undecided}</b> repos still undecided. Passes fill in orphans &amp; prune ghosts —
        structural re-planning unlocks once everything has a verdict.
      {:else}
        Everything is planned. Passes can now propose <b>structural changes</b> — hub splits, new hubs, re-assignments.
      {/if}
    </div>
    <div class="phase-stats">
      <span>{state.undecided} undecided</span>
      <span>{state.ghosts} ghosts</span>
      <span>{state.pending_proposals} pending</span>
    </div>
  </div>

  <div class="actions-row" style="margin-top:1rem;">
    <button on:click={runPass} disabled={running}>
      {running ? 'Running pass…' : '▶ Run replan pass'}
    </button>
    {#if proposals.some((p) => p.kind === 'verdict' && p.confidence >= 0.7)}
      <button class="success" on:click={acceptAllHighConf} disabled={busyId !== null}>
        ✓ Accept all high-confidence
      </button>
    {/if}
    <button class="ghost" on:click={load} disabled={running}>↻ Reload</button>
  </div>

  <!-- Proposals -->
  <div class="section">
    <div class="section-head"><h2>Proposals ({proposals.length})</h2></div>
    {#if proposals.length === 0}
      <p class="empty">No pending proposals. Run a pass to generate some.</p>
    {:else}
      <div class="prop-list">
        {#each proposals as p (p.id)}
          <div class="prop-row" class:advisory={p.kind === 'split' || p.kind === 'new-hub'}>
            <span class="kind-badge k-{p.kind}">{KIND_LABEL[p.kind] ?? p.kind}</span>
            <span class="prop-target">{p.target}</span>
            <span class="prop-arrow">{fmtProposed(p)}</span>
            <span class="src-badge src-{p.source}">{p.source}</span>
            <span class="conf {confClass(p.confidence)}" title="confidence">{Math.round(p.confidence * 100)}%</span>
            <span class="prop-rationale">{p.rationale}</span>
            <span class="prop-actions">
              <button class="sm success" disabled={busyId === p.id} on:click={() => decide(p, true)}>Accept</button>
              <button class="sm ghost" disabled={busyId === p.id} on:click={() => decide(p, false)}>Reject</button>
            </span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- History -->
  <div class="section">
    <div class="section-head"><h2>Plan history ({history.length})</h2></div>
    {#if history.length === 0}
      <p class="empty">No changes applied yet.</p>
    {:else}
      <div class="hist-list">
        {#each history as h}
          <div class="hist-row">
            <span class="kind-badge k-{h.kind}">{KIND_LABEL[h.kind] ?? h.kind}</span>
            <span class="hist-target">{h.target}</span>
            {#if h.change.to}
              <span class="hist-change">{h.change.from ? `${h.change.from.verdict}${h.change.from.hub ? '→'+h.change.from.hub : ''}` : 'undecided'} ⇒ {h.change.to.verdict}{h.change.to.hub ? '→'+h.change.to.hub : ''}</span>
            {:else}
              <span class="hist-change">advisory acknowledged</span>
            {/if}
            <span class="src-badge src-{h.source}">{h.source}</span>
            <span class="hist-time">{h.created_at}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .phase-banner { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 1rem; padding: 0.9rem 1.1rem; border-radius: 10px; margin-top: 1rem; border: 1px solid; }
  .phase-incremental { background: #eff6ff; border-color: #bfdbfe; }
  .phase-replan { background: #f0fdf4; border-color: #bbf7d0; }
  .phase-tag { font-weight: 700; font-size: 0.72rem; letter-spacing: 0.08em; padding: 0.25em 0.6em; border-radius: 5px; background: #1a1a2e; color: #fff; }
  .phase-text { font-size: 0.875rem; color: #374151; }
  .phase-stats { display: flex; gap: 0.6rem; font-size: 0.75rem; color: #6b7280; white-space: nowrap; }
  .phase-stats span { background: rgba(255,255,255,0.7); border-radius: 4px; padding: 0.15em 0.5em; }

  .prop-list, .hist-list { display: flex; flex-direction: column; gap: 0.4rem; }
  .prop-row { display: grid; grid-template-columns: 72px 180px 150px 48px 42px 1fr auto; align-items: center; gap: 0.6rem; padding: 0.45rem 0.7rem; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 0.84rem; }
  .prop-row.advisory { background: #fffbeb; border-color: #fde68a; }
  .prop-target { font-family: monospace; font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
  .prop-arrow { font-family: monospace; color: #1e40af; font-size: 0.8rem; }
  .prop-rationale { color: #6b7280; font-size: 0.78rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .prop-actions { display: flex; gap: 0.3rem; }

  .kind-badge { font-size: 0.68rem; font-weight: 600; padding: 0.15em 0.45em; border-radius: 4px; text-align: center; }
  .k-verdict { background: #dbeafe; color: #1e40af; }
  .k-ghost-prune, .k-ghost { background: #f3f4f6; color: #6b7280; }
  .k-reassign { background: #ede9fe; color: #5b21b6; }
  .k-split, .k-new-hub { background: #fef3c7; color: #92400e; }
  .src-badge { font-size: 0.66rem; padding: 0.1em 0.4em; border-radius: 4px; text-align: center; }
  .src-rule { background: #e5e7eb; color: #374151; }
  .src-llm { background: #ddd6fe; color: #5b21b6; }
  .src-manual { background: #d1fae5; color: #065f46; }
  .conf { font-size: 0.72rem; font-weight: 700; text-align: right; }
  .conf.hi { color: #16a34a; } .conf.mid { color: #d97706; } .conf.lo { color: #9ca3af; }

  .hist-row { display: grid; grid-template-columns: 72px 160px 1fr 48px auto; align-items: center; gap: 0.6rem; padding: 0.4rem 0.7rem; border-bottom: 1px solid #f0f0f4; font-size: 0.82rem; }
  .hist-target { font-family: monospace; font-weight: 600; }
  .hist-change { font-family: monospace; font-size: 0.78rem; color: #374151; }
  .hist-time { font-size: 0.72rem; color: #9ca3af; white-space: nowrap; }
</style>
