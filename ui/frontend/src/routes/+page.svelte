<script>
  // Landing: resume the last workflow step when logged in, else Setup (the
  // first step, which owns the GitHub connection). The old standalone login
  // page merged into Setup (2026-06-12).
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { goto } from '$app/navigation';
  import { session, lastStep } from '$lib/stores';
  onMount(() => {
    const last = get(lastStep);
    const dest = (get(session) && last && last !== '/') ? last : '/setup';
    goto(dest, { replaceState: true });
  });
</script>

<p class="loading">Loading…</p>
