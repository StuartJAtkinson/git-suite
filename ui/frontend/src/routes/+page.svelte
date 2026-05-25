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
  let tokenSource = ''; // 'env' | 'gh-cli' | ''

  onMount(async () => {
    if ($session) { goto('/hubs'); return; }

    // Pre-fill from server-detected defaults
    try {
      const defaults = await api.getDefaults();
      repos_root = defaults.repos_root;
      if (defaults.has_env_token) {
        tokenSource = 'env';
        await fetchGhToken(); // auto-fill if env token is ready
      }
    } catch {
      repos_root = '';
    }
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
    env: 'from GH_TOKEN env / Infisical',
    'gh-cli': 'from gh CLI',
  };
</script>

<div class="card login-card">
  <h1>git-suite</h1>
  <p class="sub">GitHub portfolio manager</p>

  <form on:submit|preventDefault={login} class="form-group">

    <!-- Token row -->
    <div>
      <label style="margin-bottom: 0.4rem;">
        GitHub token
        <div style="display: flex; gap: 0.4rem; align-items: center; margin-top: 0.3rem;">
          <input
            type="password"
            bind:value={token}
            placeholder="ghp_..."
            required
            autocomplete="off"
            style="flex: 1;"
          />
          <button
            type="button"
            class="ghost sm"
            disabled={loadingToken}
            on:click={fetchGhToken}
            title="Read token from gh CLI or GH_TOKEN env var"
          >
            {loadingToken ? '...' : 'gh auth'}
          </button>
        </div>
      </label>
      {#if tokenSource && token}
        <p style="font-size: 0.78rem; color: #6b7280; margin: 0.2rem 0 0;">
          {SOURCE_LABEL[tokenSource] ?? tokenSource}
        </p>
      {:else if !token}
        <p style="font-size: 0.78rem; color: #6b7280; margin: 0.2rem 0 0;">
          Or create one at
          <a href="https://github.com/settings/tokens" target="_blank" rel="noreferrer">
            github.com/settings/tokens
          </a>
          — needs <code>repo</code> scope.
        </p>
      {/if}
    </div>

    <!-- Repos root -->
    <label>
      Repos root (server path)
      <input type="text" bind:value={repos_root} required placeholder="/home/user/GitHub" />
    </label>

    {#if errorMsg}
      <div class="error-msg">{errorMsg}</div>
    {/if}

    <button type="submit" disabled={loading || !token || !repos_root}>
      {loading ? 'Connecting...' : 'Connect'}
    </button>
  </form>
</div>
