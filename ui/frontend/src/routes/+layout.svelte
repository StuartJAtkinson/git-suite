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
    <a href="/hubs" class={active('/hubs')}>Hubs</a>
    <a href="/scan" class={active('/scan')}>Scan</a>
  </div>
  <span class="spacer" />
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
