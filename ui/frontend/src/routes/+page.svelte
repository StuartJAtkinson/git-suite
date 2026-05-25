<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let token = '';
  let repos_root = '';
  let errorMsg = '';
  let loading = false;
  let loadingToken = false;
  let tokenSource = '';
  let suggestions = [];
  let completeTimer;
  let fileInput;

  onMount(async () => {
    if ($session) { goto('/hubs'); return; }
    try {
      const defaults = await api.getDefaults();
      repos_root = defaults.repos_root;
      if (defaults.has_env_token) await fetchGhToken();
    } catch { /* leave blank */ }
  });

  async function fetchGhToken() {
    loadingToken = true;
    errorMsg = '';
    try {
      const res = await api.getGhToken();
      token = res.token;
      tokenSource = res.source;
    } catch (e) {
      errorMsg = e.message;
      tokenSource = '';
    } finally {
      loadingToken = false;
    }
  }

  function onPathInput(e) {
    clearTimeout(completeTimer);
    const val = e.target.value;
    completeTimer = setTimeout(async () => {
      try {
        suggestions = await api.pathComplete(val);
      } catch { suggestions = []; }
    }, 250);
  }

  async function onFolderPick(e) {
    const files = e.target.files;
    if (!files || !files.length) return;
    const folderName = files[0].webkitRelativePath.split('/')[0];
    errorMsg = '';
    try {
      const res = await api.searchFolder(folderName);
      if (res.path) {
        repos_root = res.path;
      } else {
        errorMsg = `Selected "${folderName}" but couldn't find it on the server — type the full path.`;
      }
    } catch (ex) {
      errorMsg = ex.message;
    }
    // Reset so the same folder can be re-picked if needed
    e.target.value = '';
  }

  async function login() {
    loading = true;
    errorMsg = '';
    try {
      const res = await api.login(token, repos_root);
      session.set(res);
      goto('/hubs');
    } catch (e) {
      errorMsg = e.message;
    } finally {
      loading = false;
    }
  }

  const SOURCE_LABEL = {
    env: 'from GH_TOKEN / Infisical',
    'gh-cli': 'from gh CLI',
  };
</script>

<div class="card login-card">
  <h1>git-suite</h1>
  <p class="sub">GitHub portfolio manager</p>

  <form on:submit|preventDefault={login} class="form-group">

    <!-- Token -->
    <div>
      <label style="margin-bottom:0.4rem;">
        GitHub token
        <div style="display:flex; gap:0.4rem; align-items:center; margin-top:0.3rem;">
          <input
            type="password"
            bind:value={token}
            placeholder="ghp_..."
            required
            autocomplete="off"
            style="flex:1;"
          />
          <button type="button" class="ghost sm" disabled={loadingToken} on:click={fetchGhToken}>
            {loadingToken ? '...' : 'gh auth'}
          </button>
        </div>
      </label>
      {#if tokenSource && token}
        <p style="font-size:0.78rem; color:#6b7280; margin:0.2rem 0 0">{SOURCE_LABEL[tokenSource] ?? tokenSource}</p>
      {:else if !token}
        <p style="font-size:0.78rem; color:#6b7280; margin:0.2rem 0 0">
          Create one at
          <a href="https://github.com/settings/tokens" target="_blank" rel="noreferrer">github.com/settings/tokens</a>
          — needs <code>repo</code> scope.
        </p>
      {/if}
    </div>

    <!-- Repos root -->
    <div>
      <label style="margin-bottom:0.4rem;">
        Repos root
        <div style="display:flex; gap:0.4rem; align-items:center; margin-top:0.3rem;">
          <input
            list="path-suggestions"
            bind:value={repos_root}
            on:input={onPathInput}
            required
            placeholder="H:\GitHub"
            style="flex:1;"
          />
          <button type="button" class="ghost sm" on:click={() => fileInput.click()}>Browse</button>
        </div>
        <datalist id="path-suggestions">
          {#each suggestions as s}
            <option value={s}></option>
          {/each}
        </datalist>
      </label>
      <p style="font-size:0.78rem; color:#6b7280; margin:0.2rem 0 0">
        Type to autocomplete or click Browse to pick the folder.
      </p>
    </div>

    <!-- Hidden folder picker -->
    <input
      type="file"
      webkitdirectory
      bind:this={fileInput}
      on:change={onFolderPick}
      style="display:none"
    />

    {#if errorMsg}
      <div class="error-msg">{errorMsg}</div>
    {/if}

    <button type="submit" disabled={loading || !token || !repos_root}>
      {loading ? 'Connecting...' : 'Connect'}
    </button>
  </form>
</div>
