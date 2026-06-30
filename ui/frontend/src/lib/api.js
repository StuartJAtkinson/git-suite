// All calls go through Vite's dev proxy (/api -> :2800/api, /auth -> :2800/auth)
// so no hard-coded base URL is needed in dev or prod.

import { session } from './stores';

async function req(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    // Stale session_id (e.g. the SQLite row was wiped by a backend restart):
    // clear local state so the Setup page surfaces the Connect form again.
    if (r.status === 401 && /invalid session/i.test(err.detail || '')) {
      session.set(null);
    }
    throw new Error(err.detail || r.statusText);
  }
  return r.json();
}

export const api = {
  // Auth
  getGhToken: () => req('GET', '/auth/gh-token'),
  login: (token) =>
    req('POST', '/auth/login', { token }),

  // Hubs
  getHubs: () => req('GET', '/api/hubs'),
  markAbsorbed: (hub, repo) =>
    req('POST', '/api/hubs/absorb', { hub, repo }),

  // Scan
  startScan: (session_id) =>
    req('POST', '/api/scan/start', { session_id }),
  latestScan: (session_id) =>
    req('GET', `/api/scan/latest/${session_id}`),
  heads: (session_id) =>
    req('GET', `/api/scan/heads/${session_id}`),
  distill: (session_id) =>
    req('POST', `/api/scan/distill/${session_id}`, {}),
  distillRecords: (session_id) =>
    req('GET', `/api/scan/distill/${session_id}/records`),
  revalidate: (session_id) =>
    req('POST', `/api/scan/distill/revalidate/${session_id}`, {}),
  verdicts: (session_id) =>
    req('GET', `/api/scan/distill/verdicts/${session_id}`),

  // Config
  getConfig: () => req('GET', '/api/config'),
  saveConfig: (body) => req('POST', '/api/config', body),
  getProviders: () => req('GET', '/api/config/providers'),
  getLlmStatus: () => req('GET', '/api/config/llm-status'),
  // POST so an unsaved key never lands in URLs/access logs.
  listModels: (provider, key, kind = 'llm') =>
    req('POST', `/api/config/models/${provider}`, { key, kind }),

  // Reconcile (intent vs reality)
  reconcile: (session_id) => req('GET', `/api/reconcile/${session_id}`),

  // Plan (editable single source of truth)
  setVerdict: (repo, verdict, hub) =>
    req('POST', '/api/plan/verdict', { repo, verdict, hub }),
  resetPlan: () => req('POST', '/api/plan/reset'),
  blankPlan: () => req('POST', '/api/plan/blank'),
  clearPlan: () => req('POST', '/api/plan/clear'),
  upsertHub: (hub) => req('POST', '/api/plan/hub', hub),
  removeHub: (name) => req('DELETE', `/api/plan/hub/${name}`),
  pruneGhosts: (session_id) => req('POST', `/api/replan/prune-ghosts/${session_id}`),
  setHubBoundary: (hub, boundary) =>
    req('POST', '/api/plan/hub-boundary', { hub, boundary }),

  // Overlap (hub venn / boundaries)
  getOverlap: (session_id) => req('GET', `/api/overlap/${session_id}`),

  // Stars (dedup: owned + starred in one framework)
  refreshStars: (session_id) => req('POST', `/api/stars/refresh/${session_id}`),
  getStars: () => req('GET', '/api/stars'),

  // Cluster (assisted group formation — mixed: owned + forks + stars)
  // recompute=false returns the saved result (no re-embedding); true forces a
  // fresh clustering pass and overwrites it. k = target cluster count (omit for
  // the server default ~√(n/2)).
  getClusters: (session_id, { k = null, source = 'mixed', recompute = false } = {}) => {
    const q = new URLSearchParams({ source, recompute });
    if (k != null) q.set('k', k);
    return req('GET', `/api/cluster/${session_id}?${q}`);
  },
  formHub: (session_id, body) =>
    req('POST', `/api/cluster/form/${session_id}`, body),
  refreshForks: (session_id) =>
    req('POST', `/api/cluster/refresh-forks/${session_id}`, {}),

  // Order (per-hub ontological ordering, Tree of Knowledge layout)
  getOrder: (session_id, hub) =>
    req('GET', `/api/order/${session_id}/${hub}`),
  saveOrder: (session_id, hub, rows) =>
    req('POST', `/api/order/${session_id}/${hub}`, { rows }),
  suggestOrder: (session_id, hub) =>
    req('POST', `/api/order/${session_id}/${hub}/suggest-order`, {}),
  suggestColumn: (session_id, hub, repo) =>
    req('POST', `/api/order/${session_id}/${hub}/suggest-column`, { repo }),
  setCompatTags: (session_id, hub, tags) =>
    req('POST', `/api/order/${session_id}/${hub}/compat-tags`, { tags }),
  annotate: (session_id, hub, repo, annotations) =>
    req('POST', `/api/order/${session_id}/${hub}/annotate`, { repo, annotations }),

  // Execute (plan -> real GitHub actions)
  executePreview: (session_id) => req('GET', `/api/execute/preview/${session_id}`),
  executeArchive: (session_id, repos) =>
    req('POST', `/api/execute/archive/${session_id}`, { repos }),
  executeCreateHubs: (session_id, hubs) =>
    req('POST', `/api/execute/create-hubs/${session_id}`, { hubs }),
  executePushReadmes: (session_id, hubs) =>
    req('POST', `/api/execute/push-readmes/${session_id}`, { hubs }),
  archiveHubs: (session_id, hubs) =>
    req('POST', `/api/execute/archive-hubs/${session_id}`, { hubs }),
  unarchiveHubs: (session_id, hubs) =>
    req('POST', `/api/execute/unarchive-hubs/${session_id}`, { hubs }),
  deleteHubs: (session_id, hubs) =>
    req('POST', `/api/execute/delete-hubs/${session_id}`, { hubs }),

  // Migration assist
  migrationHub: (hub, session_id) =>
    req('GET', `/api/migration/hub/${hub}/${session_id}`),
  genChecklist: (session_id, hub, repo, regenerate = false) =>
    req('POST', `/api/migration/checklist/${session_id}`, { hub, repo, regenerate }),
  pushMigration: (session_id, hub) =>
    req('POST', `/api/migration/push/${session_id}`, { hub }),

  // Replan loop
  replanState: (session_id) => req('GET', `/api/replan/state/${session_id}`),
  runReplanPass: (session_id) => req('POST', `/api/replan/pass/${session_id}`),
  getProposals: () => req('GET', '/api/replan/proposals'),
  acceptProposal: (id) => req('POST', `/api/replan/proposal/${id}/accept`),
  rejectProposal: (id) => req('POST', `/api/replan/proposal/${id}/reject`),
  replanHistory: () => req('GET', '/api/replan/history'),
};

export function scanWs(scan_id, onRepo, onDone, onError) {
  // Same-origin WS — proxied to the backend by Vite (dev) or nginx (prod),
  // so it works regardless of host/port and over https (wss).
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/api/scan/${scan_id}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'repo') onRepo(msg.data);
    else if (msg.type === 'done') onDone(msg.total);
    else if (msg.type === 'error') onError(msg.message);
  };
  ws.onerror = () => onError('WebSocket connection failed');
  return ws;
}
