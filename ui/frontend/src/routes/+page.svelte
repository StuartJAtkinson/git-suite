<script>
  // Setup is the first workflow step and owns the GitHub connection —
  // the old standalone login page merged into it (2026-06-12).
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  onMount(() => goto('/setup', { replaceState: true }));
</script>

<p class="loading">Redirecting to Setup…</p>
