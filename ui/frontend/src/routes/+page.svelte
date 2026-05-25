<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores';
  import { api } from '$lib/api';

  let token = '';
  let repos_root = 'H:\\GitHub';
  let errorMsg = '';
  let loading = false;

  onMount(() => {
    if ($session) goto('/hubs');
  });

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
</script>

<div class="card login-card">
  <h1>git-suite</h1>
  <p class="sub">GitHub portfolio manager</p>

  <form on:submit|preventDefault={login} class="form-group">
    <label>
      GitHub Personal Access Token
      <input
        type="password"
        bind:value={token}
        placeholder="ghp_..."
        required
        autocomplete="off"
      />
    </label>
    <label>
      Repos root path
      <input type="text" bind:value={repos_root} required />
    </label>
    {#if errorMsg}
      <p class="error-msg">{errorMsg}</p>
    {/if}
    <button type="submit" disabled={loading || !token}>
      {loading ? 'Connecting...' : 'Connect'}
    </button>
  </form>
</div>
