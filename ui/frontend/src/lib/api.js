// All calls go through Vite's dev proxy (/api → :8000/api, /auth → :8000/auth)
// so no hard-coded base URL is needed in dev or prod.

async function req(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

export const api = {
  // Auth
  pickFolder: () => req('POST', '/auth/pick-folder'),
  browse: (path) =>
    req('GET', `/auth/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`),
  searchFolder: (name) =>
    req('GET', `/auth/search-folder?name=${encodeURIComponent(name)}`),

  pathComplete: (prefix) =>
    req('GET', `/auth/path-complete?prefix=${encodeURIComponent(prefix)}`),
  getDefaults: () => req('GET', '/auth/defaults'),
  getGhToken: () => req('GET', '/auth/gh-token'),
  login: (token, repos_root) =>
    req('POST', '/auth/login', { token, repos_root }),
  getSession: (session_id) =>
    req('GET', `/auth/session/${session_id}`),

  // Hubs
  getHubs: () => req('GET', '/api/hubs'),
  getHubStatus: (hub) =>
    req('GET', `/api/hubs/${hub}/status`),
  archiveRepo: (session_id, hub, repo) =>
    req('POST', '/api/hubs/archive', { session_id, hub, repo }),
  markAbsorbed: (hub, repo) =>
    req('POST', '/api/hubs/absorb', { hub, repo }),

  // Scan
  startScan: (session_id) =>
    req('POST', '/api/scan/start', { session_id }),
  getScanResults: (scan_id, super_cat) =>
    req('GET', `/api/scan/${scan_id}/results${super_cat ? `?super_cat=${super_cat}` : ''}`),

  // Commercial refs
  scrapeUrl: (hub, url) =>
    req('POST', '/api/commercial/scrape', { hub, url }),
  getCommercialRefs: (hub) =>
    req('GET', `/api/commercial/${hub}`),
  deleteRef: (ref_id) =>
    req('DELETE', `/api/commercial/${ref_id}`),

  // README
  pushReadme: (session_id, hub) =>
    req('POST', '/api/readme/push', { session_id, hub }),
  previewReadme: (hub, session_id) =>
    req('GET', `/api/readme/preview/${hub}?session_id=${session_id}`),
};

export function scanWs(scan_id, onRepo, onDone, onError) {
  const ws = new WebSocket(`ws://localhost:8000/api/scan/${scan_id}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'repo') onRepo(msg.data);
    else if (msg.type === 'done') onDone(msg.total);
    else if (msg.type === 'error') onError(msg.message);
  };
  ws.onerror = () => onError('WebSocket connection failed');
  return ws;
}
