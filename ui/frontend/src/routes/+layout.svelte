<script>
  import { session } from '$lib/stores';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import '../app.css';

  function logout() {
    session.set(null);
    goto('/');
  }

  $: active = (href) => $page.url.pathname.startsWith(href) ? 'active' : '';
</script>

<nav>
  <a href="/" class="brand">git-suite</a>
  <div class="links">
    <a href="/setup" class={active('/setup')}>Setup</a>
    <a href="/scan" class={active('/scan')}>Scan</a>
    <a href="/stars" class={active('/stars')}>Stars</a>
    <a href="/cluster" class={active('/cluster')}>Cluster</a>
    <a href="/hubs" class={active('/hubs')}>Hubs</a>
    <a href="/overlap" class={active('/overlap')}>Overlap</a>
    <a href="/replan" class={active('/replan')}>Replan</a>
    <a href="/triage" class={active('/triage')}>Triage</a>
    <a href="/execute" class={active('/execute')}>Execute</a>
    <a href="/layer-audit" class={active('/layer-audit')}>Layers</a>
    <a href="/summary" class={active('/summary')}>Summary</a>
  </div>
  <span class="spacer"></span>
  {#if $session}
    <div class="user">
      {#if $session.avatar_url}
        <img src={$session.avatar_url} alt={$session.github_user} />
      {/if}
      <span>{$session.github_user}</span>
      <button class="ghost sm" on:click={logout}>Logout</button>
    </div>
  {/if}
</nav>

<main>
  <slot />
</main>
