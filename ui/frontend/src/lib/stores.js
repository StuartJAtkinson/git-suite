import { writable } from 'svelte/store';
import { browser } from '$app/environment';

function persisted(key, initial) {
  const stored = browser ? localStorage.getItem(key) : null;
  const store = writable(stored ? JSON.parse(stored) : initial);
  if (browser) {
    store.subscribe((v) => {
      if (v === null) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify(v));
    });
  }
  return store;
}

// { session_id, github_user, avatar_url }
export const session = persisted('gs_session', null);

// current scan_id from last scan run
export const currentScanId = persisted('gs_scan_id', null);
