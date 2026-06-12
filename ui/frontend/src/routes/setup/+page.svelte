<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { session } from '$lib/stores';

  const LLM_PROVIDERS = {
    anthropic: "Anthropic", openai: "OpenAI", openrouter: "OpenRouter",
    deepseek: "DeepSeek", xai: "xAI", minimax: "MiniMax", ollama: "Ollama",
  };

  const LLM_DEFAULT_MODELS = {
    anthropic: "claude-sonnet-4-6", openai: "gpt-4o",
    openrouter: "anthropic/claude-sonnet-4-6", deepseek: "deepseek-chat",
    xai: "grok-beta", minimax: "abab6.5-chat", ollama: "llama3.2",
  };

  function obfuscate(key) {
    if (!key) return '';
    if (key.length < 12) return '••••••••';
    return key.slice(0, 10) + '...' + key.slice(-4);
  }

  let config = {};
  let providers = [];      // registry metadata from /api/config/providers
  let loading = true;
  let saving = false;
  let saved = false;
  let error = '';
  let llmStatus = null;

  async function refreshStatus() {
    try { llmStatus = await api.getLlmStatus(); } catch { llmStatus = null; }
  }

  // --- GitHub connection (merged from the old standalone login page) ---
  let ghToken = '';
  let tokenSource = '';
  let ghError = '';
  let loadingToken = false;
  let connecting = false;

  async function fetchGhToken() {
    loadingToken = true;
    ghError = '';
    try {
      const res = await api.getGhToken();
      ghToken = res.token;
      tokenSource = res.source;
    } catch (e) {
      ghError = e.message;
      tokenSource = '';
    } finally {
      loadingToken = false;
    }
  }

  async function connect() {
    connecting = true;
    ghError = '';
    try {
      const res = await api.login(ghToken);
      session.set(res);
      ghToken = '';
    } catch (e) {
      ghError = e.message;
    } finally {
      connecting = false;
    }
  }

  function disconnect() {
    session.set(null);
  }

  const SOURCE_LABEL = { env: 'from GH_TOKEN / Infisical', 'gh-cli': 'from gh CLI' };
  // ---------------------------------------------------------------------

  onMount(async () => {
    try {
      config = await api.getConfig();
      providers = await api.getProviders();
    } catch (e) { error = e.message; }
    if (!$session) {
      // Best-effort prefill from GH_TOKEN env or gh CLI; silent if neither.
      try { await fetchGhToken(); } catch {} finally { ghError = ''; }
    }
    await refreshStatus();
    loading = false;
  });

  // Adding a provider registers an (empty) key so its form renders — you then
  // fill in the key / call URL / model and Save.
  function addProvider(p) { patchKey(p, ''); }
  function patchKey(p, v) { config = { ...config, llm_keys: { ...(config.llm_keys||{}), [p]: v } }; saved = false; }
  function patchModel(p, v) { config = { ...config, llm_models: { ...(config.llm_models||{}), [p]: v } }; saved = false; }
  function patchBaseUrl(p, v) { config = { ...config, llm_base_urls: { ...(config.llm_base_urls||{}), [p]: v } }; saved = false; }
  function removeProvider(p) {
    const keys = { ...(config.llm_keys||{}) }; delete keys[p];
    const models = { ...(config.llm_models||{}) }; delete models[p];
    const urls = { ...(config.llm_base_urls||{}) }; delete urls[p];
    const order = (config.llm_priority_order||[]).filter(x => x !== p);
    config = { ...config, llm_keys: keys, llm_models: models, llm_base_urls: urls, llm_priority_order: order };
    saved = false;
  }
  function movePriority(p, dir) {
    // Start from the order the user actually sees, so the first reorder
    // works even before llm_priority_order has ever been saved.
    const order = [...orderedConfigured];
    const i = order.indexOf(p); if (i < 0) return;
    const j = i + dir; if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    config = { ...config, llm_priority_order: order };
    saved = false;
  }

  async function save() {
    saving = true; error = '';
    try { await api.saveConfig(config); saved = true; await refreshStatus(); }
    catch (e) { error = e.message; }
    finally { saving = false; }
  }

  const EMBED_DEFAULTS = { ollama: 'nomic-embed-text', openai: 'text-embedding-3-small' };
  $: embedProvider = Object.keys(config.embedding_models || {})[0] || '';
  $: embedModel = (config.embedding_models || {})[embedProvider] || '';
  function setEmbedProvider(p) {
    config = { ...config, embedding_models: p ? { [p]: EMBED_DEFAULTS[p] || '' } : {} };
    saved = false;
  }
  function setEmbedModel(m) {
    if (!embedProvider) return;
    config = { ...config, embedding_models: { [embedProvider]: m } };
    saved = false;
  }

  $: meta = Object.fromEntries(providers.map(p => [p.id, p]));
  $: allIds = providers.length ? providers.map(p => p.id) : Object.keys(LLM_PROVIDERS);
  $: llmKeys = config.llm_keys || {};
  $: llmModels = config.llm_models || {};
  $: llmBaseUrls = config.llm_base_urls || {};
  // "added" = registered in the form (key may still be empty) — NOT "has a key".
  $: added = Array.from(new Set([
       ...Object.keys(llmKeys),
       ...(config.llm_priority_order || []),
     ])).filter(p => allIds.includes(p));
  $: priorityOrder = (config.llm_priority_order?.length ? config.llm_priority_order : added);
  $: orderedConfigured = priorityOrder.filter(p => added.includes(p));
  $: unconfigured = allIds.filter(p => !added.includes(p));
  const dispName = (p) => (meta[p]?.display_name) || LLM_PROVIDERS[p] || p;
  const defModel = (p) => (meta[p]?.default_model) || LLM_DEFAULT_MODELS[p] || '';
</script>

<div class="page-header">
  <div class="header-row">
    <div>
      <h1>Setup</h1>
      <p class="sub">GitHub session + provider config (~/.git-suite/config.json)</p>
    </div>
    <div class="header-actions">
      {#if saved}<span class="ok-badge">Saved</span>{/if}
      {#if error}<span class="err-badge">{error}</span>{/if}
      <button on:click={save} disabled={saving} class="btn-primary">
        {saving ? 'Saving...' : 'Save'}
      </button>
    </div>
  </div>
</div>

{#if loading}<p class="loading">Loading...</p>
{:else}
<div class="two-col">
  <div class="col">
    <div class="card">
      <h3 class="card-title">GitHub connection</h3>
      {#if $session}
        <div class="gh-connected">
          {#if $session.avatar_url}
            <img class="gh-avatar" src={$session.avatar_url} alt={$session.github_user} />
          {/if}
          <div class="gh-id">
            <span class="gh-user">{$session.github_user}</span>
            <span class="gh-sub">connected</span>
          </div>
          <button class="btn-remove" on:click={disconnect}>Disconnect</button>
        </div>
        <p class="hint" style="margin:0.75rem 0 0">Next step: run a <a href="/scan">Scan</a> to pull the live portfolio.</p>
      {:else}
        <p class="hint">
          Connect first — every other stage needs a GitHub session. Token needs the
          <code>repo</code> scope (<a href="https://github.com/settings/tokens" target="_blank" rel="noreferrer">create one</a>).
        </p>
        <div class="field-row">
          <span class="field-label">Token</span>
          <input type="password" class="field-input" bind:value={ghToken}
            placeholder="ghp_…" autocomplete="off" />
          <button class="btn-add" disabled={loadingToken} on:click={fetchGhToken}>
            {loadingToken ? '…' : 'gh auth'}
          </button>
        </div>
        {#if tokenSource && ghToken}
          <p class="hint" style="margin:0 0 0.5rem">{SOURCE_LABEL[tokenSource] ?? tokenSource}</p>
        {/if}
        {#if ghError}<div class="error-msg" style="margin-top:0.5rem">{ghError}</div>{/if}
        <button class="btn-primary" style="margin-top:0.75rem"
          disabled={connecting || !ghToken} on:click={connect}>
          {connecting ? 'Connecting…' : 'Connect'}
        </button>
      {/if}
    </div>

    <div class="card">
      <h3 class="card-title">LLM Providers</h3>
      <p class="hint">First in list is used. On credit exhaustion or error, the next is tried automatically.</p>

      {#if llmStatus}
        <div class="status-box" class:warn={!llmStatus.configured}>
          {#if llmStatus.configured}
            <span class="status-label">Active failover chain:</span>
            {#each llmStatus.chain as c, i}
              <span class="chain-item" class:head={i === 0}>{i + 1}. {c.display} <span class="chain-model">{c.model}</span></span>
            {/each}
          {:else}
            No usable provider — replan/scrape fall back to rules only. Add an API key below.
          {/if}
        </div>
      {/if}

      {#each orderedConfigured as provider, i}
      <div class="provider-box">
        <div class="provider-head">
          <span class="provider-num">{i+1}</span>
          <span class="provider-name">{dispName(provider)}</span>
          {#if meta[provider]?.setup_url}
            <a class="get-key" href={meta[provider].setup_url} target="_blank" rel="noreferrer">get key ↗</a>
          {/if}
          <div class="provider-controls">
            <button class="btn-icon" on:click={() => movePriority(provider, -1)} disabled={i===0}>↑</button>
            <button class="btn-icon" on:click={() => movePriority(provider, 1)} disabled={i===orderedConfigured.length-1}>↓</button>
            <button class="btn-remove" on:click={() => removeProvider(provider)}>Remove</button>
          </div>
        </div>
        {#if meta[provider]?.needs_key !== false}
        <div class="field-row">
          <span class="field-label">API Key</span>
          <input type="password" class="field-input" value={llmKeys[provider]||''}
            on:change={e => patchKey(provider, e.target.value)} placeholder="API key" />
        </div>
        {/if}
        {#if meta[provider]?.api_type !== 'anthropic'}
        <div class="field-row">
          <span class="field-label">Call URL</span>
          <input type="text" class="field-input" value={llmBaseUrls[provider]||''}
            on:change={e => patchBaseUrl(provider, e.target.value)} placeholder={meta[provider]?.base_url || 'https://…'} />
        </div>
        {/if}
        <div class="field-row">
          <span class="field-label">Model</span>
          <input type="text" class="field-input" value={llmModels[provider] || defModel(provider)}
            on:change={e => patchModel(provider, e.target.value)} placeholder={defModel(provider)} />
        </div>
      </div>
      {/each}

      {#if unconfigured.length > 0}
      <div class="add-section">
        <p class="add-label">Add provider:</p>
        <div class="add-buttons">
          {#each unconfigured as p}
          <button class="btn-add" on:click={() => addProvider(p)}>+ {dispName(p)}</button>
          {/each}
        </div>
      </div>
      {/if}
    </div>

    <div class="card">
      <h3 class="card-title">Embeddings (semantic overlap)</h3>
      <p class="hint">Powers the semantic venn + absorb suggestions. Off = keyword rules.</p>
      {#if llmStatus?.embeddings}
        <div class="status-box" class:warn={!llmStatus.embeddings.configured}>
          {#if llmStatus.embeddings.configured}
            Active: {#each llmStatus.embeddings.chain as c}<span class="chain-item">{c.provider} <span class="chain-model">{c.model}</span></span>{/each}
          {:else}
            Not configured — overlap uses keyword scoring.
          {/if}
        </div>
      {/if}
      <div class="field-row">
        <span class="field-label">Provider</span>
        <select class="field-input" value={embedProvider} on:change={e => setEmbedProvider(e.target.value)}>
          <option value="">Off (keyword)</option>
          <option value="ollama">Ollama (local)</option>
          <option value="openai">OpenAI</option>
        </select>
      </div>
      {#if embedProvider}
        <div class="field-row">
          <span class="field-label">Model</span>
          <input class="field-input" value={embedModel}
            on:change={e => setEmbedModel(e.target.value)}
            placeholder={EMBED_DEFAULTS[embedProvider]} />
        </div>
        {#if embedProvider === 'openai' && !llmKeys.openai}
          <p class="hint" style="color:#92400e">Add an OpenAI key above for embeddings to work.</p>
        {/if}
      {/if}
    </div>
  </div>

  <div class="col">
    <div class="card">
      <h3 class="card-title">Where these are used</h3>
      <p class="hint">The failover chains are only called at these stages. Without them, each stage degrades to deterministic rules.</p>
      <div class="use-group">
        <span class="use-tag llm">LLM (chat)</span>
        <ul>
          <li><b>Replan</b> — verdict proposals (categorisation)</li>
          <li><b>Migration</b> — per-repo checklists</li>
          <li><b>Commercial</b> — scrape → feature extraction</li>
        </ul>
      </div>
      <div class="use-group">
        <span class="use-tag emb">Embeddings</span>
        <ul>
          <li><b>Cluster</b> — group formation</li>
          <li><b>Overlap</b> — semantic venn</li>
          <li><b>Replan</b> — absorb suggestions (classification)</li>
        </ul>
      </div>
    </div>
  </div>
</div>
{/if}

<style>
.header-row { display: flex; justify-content: space-between; align-items: flex-start; }
.header-actions { display: flex; align-items: center; gap: 0.75rem; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-top: 1.5rem; }
.col { display: flex; flex-direction: column; gap: 1rem; }
.card { background: #fff; border: 1px solid #dde1e9; border-radius: 10px; padding: 1.25rem; }
.card-title { font-size: 0.875rem; font-weight: 600; color: #374151; margin: 0 0 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e5e7eb; }
.hint { font-size: 0.78rem; color: #6b7280; margin: 0 0 1rem; }
.status-box { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 7px; padding: 0.6rem 0.8rem; margin-bottom: 1rem; font-size: 0.78rem; color: #065f46; }
.status-box.warn { background: #fffbeb; border-color: #fde68a; color: #92400e; }
.use-group { margin-bottom: 0.9rem; }
.use-tag { display: inline-block; font-size: 0.7rem; font-weight: 700; border-radius: 4px; padding: 0.15em 0.5em; margin-bottom: 0.3rem; }
.use-tag.llm { background: #ddd6fe; color: #5b21b6; }
.use-tag.emb { background: #cffafe; color: #155e75; }
.use-group ul { margin: 0; padding-left: 1.2rem; font-size: 0.82rem; color: #374151; line-height: 1.55; }
.status-label { font-weight: 600; }
.chain-item { background: rgba(255,255,255,0.7); border-radius: 4px; padding: 0.1em 0.45em; font-family: monospace; }
.chain-item.head { font-weight: 700; }
.chain-model { color: #6b7280; font-size: 0.92em; }
.provider-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
.provider-head { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.provider-num { font-size: 0.7rem; font-weight: 700; color: #6b7280; width: 20px; text-align: right; }
.provider-name { font-size: 0.875rem; font-weight: 500; }
.get-key { font-size: 0.72rem; color: #0057b7; flex: 1; }
.provider-controls { display: flex; gap: 0.25rem; }
.btn-icon { background: none; border: 1px solid #d1d5db; border-radius: 4px; padding: 0.15rem 0.4rem; font-size: 0.75rem; cursor: pointer; color: #6b7280; }
.btn-icon:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-remove { background: none; border: none; color: #dc2626; font-size: 0.75rem; cursor: pointer; padding: 0.15rem 0.4rem; }
.field-row { display: flex; align-items: center; gap: 0.75rem; padding: 0.35rem 0; }
.field-label { font-size: 0.8rem; color: #6b7280; width: 80px; shrink: 0; }
.field-input { flex: 1; padding: 0.35rem 0.6rem; border: 1px solid #d1d5db; border-radius: 5px; font-size: 0.875rem; font-family: monospace; }
.field-input:focus { outline: none; border-color: #0057b7; box-shadow: 0 0 0 2px rgba(0,87,183,0.1); }
.add-section { margin-top: 0.5rem; }
.add-label { font-size: 0.78rem; color: #6b7280; margin-bottom: 0.5rem; }
.add-buttons { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.btn-add { background: none; border: 1px solid #d1d5db; border-radius: 6px; padding: 0.3rem 0.75rem; font-size: 0.8rem; color: #6b7280; cursor: pointer; }
.btn-add:hover { border-color: #0057b7; color: #0057b7; }
.btn-primary { background: #0057b7; color: #fff; border: none; border-radius: 6px; padding: 0.45rem 1rem; font-size: 0.875rem; cursor: pointer; }
.btn-primary:disabled { opacity: 0.5; }
.ok-badge { font-size: 0.8rem; color: #16a34a; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 4px; padding: 0.2rem 0.6rem; }
.err-badge { font-size: 0.8rem; color: #dc2626; background: #fef2f2; border: 1px solid #fecaca; border-radius: 4px; padding: 0.2rem 0.6rem; }
.gh-connected { display: flex; align-items: center; gap: 0.75rem; }
.gh-avatar { width: 36px; height: 36px; border-radius: 50%; }
.gh-id { display: flex; flex-direction: column; flex: 1; }
.gh-user { font-size: 0.875rem; font-weight: 600; }
.gh-sub { font-size: 0.72rem; color: #16a34a; }
</style>
