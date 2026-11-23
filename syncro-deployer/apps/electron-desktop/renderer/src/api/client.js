/**
 * Syncro Deployer API, MCP JSON-RPC 2.0, and WebSocket client.
 * Auto-resolves origin when served via Vite/HTTP preview or points to Electron sidecar :8080.
 */

let apiBase = '';

export function setApiBaseUrl(url) {
  apiBase = (url || '').replace(/\/$/, '');
}

export function getApiBaseUrl() {
  if (apiBase) return apiBase;
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') {
    return 'http://127.0.0.1:8080';
  }
  return '';
}

function buildUrl(path) {
  return `${getApiBaseUrl()}${path}`;
}

export async function apiRequest(path, options = {}) {
  const res = await fetch(buildUrl(path), {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  const text = await res.text();
  let parsed = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!res.ok) {
    const detail =
      parsed && typeof parsed === 'object'
        ? parsed.detail?.message || parsed.detail || JSON.stringify(parsed)
        : text || `HTTP ${res.status}`;
    throw new Error(String(detail));
  }
  return parsed;
}

let rpcSeq = 1;

export async function mcpCall(method, params = {}) {
  const payload = {
    jsonrpc: '2.0',
    id: rpcSeq++,
    method,
    params,
  };
  const resp = await apiRequest('/mcp', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (resp.error) {
    throw new Error(resp.error.message || 'MCP JSON-RPC error');
  }
  return resp.result;
}

export function connectLiveWebSocket({ onMessage, onStatus }) {
  let ws = null;
  let closed = false;
  let retryTimer = null;

  function resolveWsUrl() {
    const base = getApiBaseUrl();
    if (base) {
      return `${base.replace(/^http/, 'ws')}/ws/events`;
    }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/ws/events`;
  }

  function open() {
    if (closed) return;
    try {
      ws = new WebSocket(resolveWsUrl());
      ws.onopen = () => onStatus?.('connected');
      ws.onmessage = (ev) => {
        try {
          onMessage?.(JSON.parse(ev.data));
        } catch {
          onMessage?.({ type: 'raw', data: ev.data });
        }
      };
      ws.onclose = () => {
        onStatus?.('reconnecting');
        if (!closed) {
          retryTimer = setTimeout(open, 3000);
        }
      };
      ws.onerror = () => {
        ws?.close();
      };
    } catch {
      onStatus?.('offline');
    }
  }

  open();

  return () => {
    closed = true;
    if (retryTimer) clearTimeout(retryTimer);
    ws?.close();
  };
}

export const api = {
  health: () => apiRequest('/api/v1/health'),
  overview: () => apiRequest('/api/v1/overview'),
  cloudsStatus: () => apiRequest('/api/v1/clouds/status'),
  finops: () => apiRequest('/api/v1/finops/summary'),
  cliStatus: () => apiRequest('/api/v1/cli/status'),
  cliPresets: () => apiRequest('/api/v1/cli/presets'),
  cliHistory: () => apiRequest('/api/v1/cli/history'),
  cliExec: (body) => apiRequest('/api/v1/cli/exec', { method: 'POST', body: JSON.stringify(body) }),
  syncroSuite: () => apiRequest('/api/v1/syncro/suite'),
  syncroResilience: () => apiRequest('/api/v1/syncro/resilience/health'),
  syncroSetMode: (mode) =>
    apiRequest('/api/v1/syncro/mode', { method: 'POST', body: JSON.stringify({ mode }) }),
  syncroDeployments: () => apiRequest('/api/v1/syncro/deployments'),
  syncroDeploy: (body) =>
    apiRequest('/api/v1/syncro/deploy', { method: 'POST', body: JSON.stringify(body) }),
  syncroPromote: (id) =>
    apiRequest(`/api/v1/syncro/deployments/${encodeURIComponent(id)}/promote`, {
      method: 'POST',
      body: JSON.stringify({ actor: 'electron-desktop' }),
    }),
  syncroRollback: (id, reason) =>
    apiRequest(`/api/v1/syncro/deployments/${encodeURIComponent(id)}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ actor: 'electron-desktop', reason }),
    }),
  vmCompare: (criteria) =>
    apiRequest('/api/v1/vms/compare', { method: 'POST', body: JSON.stringify(criteria) }),
  vmProvision: (body) =>
    apiRequest('/api/v1/vms/provision', { method: 'POST', body: JSON.stringify(body) }),
  triggerScan: (body) =>
    apiRequest('/api/v1/scans', { method: 'POST', body: JSON.stringify(body) }),
  listScans: () => apiRequest('/api/v1/scans'),
  scanSarif: (id) => apiRequest(`/api/v1/scans/${encodeURIComponent(id)}/sarif`),
  rbacPlan: (body) =>
    apiRequest('/api/v1/rbac/powershell-plan', { method: 'POST', body: JSON.stringify(body) }),
  destroyPreview: (envId) =>
    apiRequest(`/api/v1/destroy/${encodeURIComponent(envId)}/preview`, { method: 'POST' }),
  destroyExecute: (envId, body) =>
    apiRequest(`/api/v1/destroy/${encodeURIComponent(envId)}/execute`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  environments: () => apiRequest('/api/v1/environments'),
  botStatus: () => apiRequest('/api/v1/bot/status'),
  botBill: () => apiRequest('/api/v1/bot/bill'),
  botSelfPrompt: (customPrompt) =>
    apiRequest('/api/v1/bot/self-prompt/run', {
      method: 'POST',
      body: JSON.stringify({ custom_user_prompt: customPrompt || null }),
    }),
  botPrompt: (prompt) =>
    apiRequest('/api/v1/bot/prompt', { method: 'POST', body: JSON.stringify({ prompt }) }),
  kafkaEvents: () => apiRequest('/api/v1/brokers/kafka/events?limit=25'),
};
