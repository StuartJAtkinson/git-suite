<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api';

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
  let loading = true;
  let saving = false;
  let saved = false;
  let error = '';
  let llmStatus = null;

  async function refreshStatus() {
    try { llmStatus = await api.getLlmStatus(); } catch { llmStatus = null; }
  }

  onMount(async () => {
    try { config = await api.getConfig(); } catch (e) { error = e.message; }
    await refreshStatus();
    loading = false;
  });

  function patch(key, val) { config = { ...config, [key]: val }; saved = false; }
  function patchKey(p, v) { config = { ...config, llm_keys: { ...(config.llm_keys||{}), [p]: v } }; saved = false; }
  function patchModel(p, v) { config = { ...config, llm_models: { ...(config.llm_models||{}), [p]: v } }; saved = false; }
  function removeProvider(p) {
    const keys = { ...(config.llm_keys||{}) }; delete keys[p];
    const models = { ...(config.llm_models||{}) }; delete models[p];
    const order = (config.llm_priority_order||[]).filter(x => x !== p);
    config = { ...config, llm_keys: keys, llm_models: models, llm_priority_order: order };
    saved = false;
  }
  function movePriority(p, dir) {
    const order = [...(config.llm_priority_order||configured)];
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

  $: llmKeys = config.llm_keys || {};
  $: llmModels = config.llm_models || {};
  $: configured = Object.keys(llmKeys).filter(p => llmKeys[p]);
  $: priorityOrder = (config.llm_priority_order?.length ? config.llm_priority_order : configured);
  $: orderedConfigured = priorityOrder.filter(p => llmKeys[p]);
  $: unconfigured = Object.keys(LLM_PROVIDERS).filter(p => !llmKeys[p]);
</script>

<div class="page-header">
  <div class="header-row">
    <div>
      <h1>Setup</h1>
      <p class="sub">Reads and writes ~/.git-suite/config.json</p>
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
          <span class="provider-name">{LLM_PROVIDERS[provider] ?? provider}</span>
          <div class="provider-controls">
            <button class="btn-icon" on:click={() => movePriority(provider, -1)} disabled={i===0}>↑</button>
            <button class="btn-icon" on:click={() => movePriority(provider, 1)} disabled={i===orderedConfigured.length-1}>↓</button>
            <button class="btn-remove" on:click={() => removeProvider(provider)}>Remove</button>
          </div>
        </div>
        <div class="field-row">
          <span class="field-label">API Key</span>
          <input type="password" class="field-input" value={llmKeys[provider]||''}
            on:change={e => patchKey(provider, e.target.value)} placeholder="API key" />
        </div>
        <div class="field-row">
          <span class="field-label">Model</span>
          <input type="text" class="field-input" value={llmModels[provider] || LLM_DEFAULT_MODELS[provider] || ''}
            on:change={e => patchModel(provider, e.target.value)} placeholder={LLM_DEFAULT_MODELS[provider]} />
        </div>
      </div>
      {/each}

      {#if unconfigured.length > 0}
      <div class="add-section">
        <p class="add-label">Add provider:</p>
        <div class="add-buttons">
          {#each unconfigured as p}
          <button class="btn-add" on:click={() => patchKey(p, '')}>+ {LLM_PROVIDERS[p]}</button>
          {/each}
        </div>
      </div>
      {/if}
    </div>
  </div>

  <div class="col">
    <div class="card">
      <h3 class="card-title">Jira</h3>
      <div class="field-row"><span class="field-label">Instance URL</span><input class="field-input" value={config.jira_url||''} on:change={e=>patch('jira_url',e.target.value)} placeholder="https://yourorg.atlassian.net" /></div>
      <div class="field-row"><span class="field-label">Email</span><input class="field-input" value={config.email||''} on:change={e=>patch('email',e.target.value)} placeholder="you@company.com" /></div>
      <div class="field-row"><span class="field-label">API Token</span><input type="password" class="field-input" value={config.api_token||''} on:change={e=>patch('api_token',e.target.value)} placeholder="API token" /></div>
    </div>

    <div class="card">
      <h3 class="card-title">Zoho Desk</h3>
      <p class="hint">Run python zoho_auth.py in the repo root to generate the refresh token.</p>
      <div class="field-row"><span class="field-label">Org ID</span><input class="field-input" value={config.zoho_org_id||''} on:change={e=>patch('zoho_org_id',e.target.value)} placeholder="20079607586" /></div>
      <div class="field-row"><span class="field-label">Client ID</span><input class="field-input" value={config.zoho_client_id||''} on:change={e=>patch('zoho_client_id',e.target.value)} /></div>
      <div class="field-row"><span class="field-label">Client Secret</span><input type="password" class="field-input" value={config.zoho_client_secret||''} on:change={e=>patch('zoho_client_secret',e.target.value)} /></div>
      <div class="field-row"><span class="field-label">Refresh Token</span><input type="password" class="field-input" value={config.zoho_refresh_token||''} on:change={e=>patch('zoho_refresh_token',e.target.value)} /></div>
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
.status-label { font-weight: 600; }
.chain-item { background: rgba(255,255,255,0.7); border-radius: 4px; padding: 0.1em 0.45em; font-family: monospace; }
.chain-item.head { font-weight: 700; }
.chain-model { color: #6b7280; font-size: 0.92em; }
.provider-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
.provider-head { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.provider-num { font-size: 0.7rem; font-weight: 700; color: #6b7280; width: 20px; text-align: right; }
.provider-name { font-size: 0.875rem; font-weight: 500; flex: 1; }
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
</style>
