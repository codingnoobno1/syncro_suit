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
      ws.onerror = () => ws?.close();
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
  healthReady: () => apiRequest('/api/v1/health/ready'),
  overview: () => apiRequest('/api/v1/overview'),
  projects: () => apiRequest('/api/v1/projects'),
  environments: () => apiRequest('/api/v1/environments'),
  cloudsStatus: () => apiRequest('/api/v1/clouds/status'),
  finops: () => apiRequest('/api/v1/finops/summary'),
  driftCheck: (envId) =>
    apiRequest(`/api/v1/drift/${encodeURIComponent(envId)}/check`, { method: 'POST' }),
  extensions: () => apiRequest('/api/v1/extensions'),
  invokeExtension: (extId, hookName, payload = {}) =>
    apiRequest(`/api/v1/extensions/${encodeURIComponent(extId)}/hooks`, {
      method: 'POST',
      body: JSON.stringify({ hook_name: hookName, payload }),
    }),
  brokersHealth: () => apiRequest('/api/v1/brokers/health'),
  kafkaEvents: () => apiRequest('/api/v1/brokers/kafka/events?limit=30'),
  rabbitmqJobs: () => apiRequest('/api/v1/brokers/rabbitmq/jobs?limit=30'),
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
  vmCatalog: () => apiRequest('/api/v1/vms/catalog'),
  vmCompare: (criteria) =>
    apiRequest('/api/v1/vms/compare', { method: 'POST', body: JSON.stringify(criteria) }),
  vmProvision: (body) =>
    apiRequest('/api/v1/vms/provision', { method: 'POST', body: JSON.stringify(body) }),
  triggerScan: (body) =>
    apiRequest('/api/v1/scans', { method: 'POST', body: JSON.stringify(body) }),
  listScans: () => apiRequest('/api/v1/scans'),
  scanSarif: (id) => apiRequest(`/api/v1/scans/${encodeURIComponent(id)}/sarif`),
  opaPolicies: () => apiRequest('/api/v1/policies/opa'),
  rbacPlan: (body) =>
    apiRequest('/api/v1/rbac/powershell-plan', { method: 'POST', body: JSON.stringify(body) }),
  destroyPreview: (envId) =>
    apiRequest(`/api/v1/destroy/${encodeURIComponent(envId)}/preview`, { method: 'POST' }),
  destroyExecute: (envId, body) =>
    apiRequest(`/api/v1/destroy/${encodeURIComponent(envId)}/execute`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  botStatus: () => apiRequest('/api/v1/bot/status'),
  botBill: () => apiRequest('/api/v1/bot/bill'),
  botGuardrails: () => apiRequest('/api/v1/bot/guardrails'),
  botUpdateGuardrails: (body) =>
    apiRequest('/api/v1/bot/guardrails', { method: 'PUT', body: JSON.stringify(body) }),
  botDirectives: () => apiRequest('/api/v1/bot/directives'),
  botUpdateDirectives: (body) =>
    apiRequest('/api/v1/bot/directives', { method: 'PUT', body: JSON.stringify(body) }),
  botSelfPrompt: (customPrompt) =>
    apiRequest('/api/v1/bot/self-prompt/run', {
      method: 'POST',
      body: JSON.stringify({ custom_user_prompt: customPrompt || null }),
    }),
  botPrompt: (prompt) =>
    apiRequest('/api/v1/bot/prompt', { method: 'POST', body: JSON.stringify({ prompt }) }),
  iacWorkspaces: () => apiRequest('/api/v1/iac/workspaces'),
  iacTerraformGenerate: (body) =>
    apiRequest('/api/v1/iac/terraform/generate', { method: 'POST', body: JSON.stringify(body) }),
  iacTerraformBuild: (body) =>
    apiRequest('/api/v1/iac/terraform/build', { method: 'POST', body: JSON.stringify(body) }),
  iacTerraformRun: (body) =>
    apiRequest('/api/v1/iac/terraform/run', { method: 'POST', body: JSON.stringify(body) }),
  iacDevSecOpsGraph: (body) =>
    apiRequest('/api/v1/iac/graph/devsecops', { method: 'POST', body: JSON.stringify(body) }),
  scriptBundles: () => apiRequest('/api/v1/scripts/bundles'),
  scriptWriteAnsible: (body) =>
    apiRequest('/api/v1/scripts/ansible/generate', { method: 'POST', body: JSON.stringify(body) }),
  scriptWriteHelm: (body) =>
    apiRequest('/api/v1/scripts/helm/generate', { method: 'POST', body: JSON.stringify(body) }),
  scriptWriteCicd: (body) =>
    apiRequest('/api/v1/scripts/cicd/generate', { method: 'POST', body: JSON.stringify(body) }),
  scriptWriteContainer: (body) =>
    apiRequest('/api/v1/scripts/container/generate', { method: 'POST', body: JSON.stringify(body) }),
  securityMcpStatus: () => apiRequest('/api/v1/security/mcp/status'),
  securityAssessments: () => apiRequest('/api/v1/security/assessments'),
  securityAssessTrivy: (body) =>
    apiRequest('/api/v1/security/assess/trivy', { method: 'POST', body: JSON.stringify(body) }),
  securityAssessBandit: (body) =>
    apiRequest('/api/v1/security/assess/bandit', { method: 'POST', body: JSON.stringify(body) }),
  securityAssessSast: (body) =>
    apiRequest('/api/v1/security/assess/sast', { method: 'POST', body: JSON.stringify(body) }),
  securityAssessDast: (body) =>
    apiRequest('/api/v1/security/assess/dast', { method: 'POST', body: JSON.stringify(body) }),
  securityAssessFull: (body) =>
    apiRequest('/api/v1/security/assess/full', { method: 'POST', body: JSON.stringify(body) }),
};
