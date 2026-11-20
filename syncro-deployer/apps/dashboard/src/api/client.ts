export type CloudProvider = "aws" | "gcp" | "azure";

export interface Project {
  id: string;
  name: string;
  repository: string;
  primary_language: string;
  owner_team: string;
  azure_subscription_id: string;
  target_clouds: CloudProvider[];
}

export interface AzureResourceNode {
  id: string;
  name: string;
  resource_type: string;
  cloud: CloudProvider;
  hourly_cost_usd: number;
  depends_on: string[];
  protected: boolean;
}

export interface Environment {
  id: string;
  project_id: string;
  name: string;
  cloud: CloudProvider;
  tier: "ephemeral" | "staging" | "production";
  location: string;
  resource_group: string;
  vm_sku: string | null;
  status: string;
  ttl_hours: number | null;
  has_delete_lock: boolean;
  compliance_score: number;
  hourly_cost_usd: number;
  resources: AzureResourceNode[];
}

export interface VmSecurityFeatures {
  confidential_compute: boolean;
  confidential_tech: string | null;
  secure_boot: boolean;
  vtpm: boolean;
  imdsv2_or_oslogin: boolean;
  encryption_at_host: boolean;
  cis_hardened_image: string;
}

export interface VmSku {
  id: string;
  cloud: CloudProvider;
  sku: string;
  family: string;
  profile: string;
  architecture: "x86_64" | "arm64";
  vcpu: number;
  memory_gib: number;
  gpu_model: string | null;
  gpu_count: number;
  network_gbps: number;
  storage_iops: number;
  hourly_on_demand_usd: number;
  hourly_spot_usd: number;
  regions: string[];
  security: VmSecurityFeatures;
  compliance_badges: string[];
}

export interface VmRecommendation {
  sku: VmSku;
  fit_score: number;
  security_score: number;
  effective_hourly_usd: number;
  effective_monthly_usd: number;
  spot_savings_pct: number;
  recommended: boolean;
  rationale: string[];
  terraform_snippet: string;
}

export interface VmComparisonMatrix {
  best_by_cloud: Record<CloudProvider, VmRecommendation | null>;
  cheapest_cloud: string | null;
  highest_security_cloud: string | null;
  max_monthly_savings_vs_priciest_usd: number;
  ranked_matches: VmRecommendation[];
}

export interface FinOpsSummary {
  total_hourly_usd: number;
  total_monthly_projected_usd: number;
  total_ephemeral_reclaimable_monthly_usd: number;
  by_cloud: Array<{
    cloud: CloudProvider;
    active_environments: number;
    hourly_burn_usd: number;
    monthly_projected_usd: number;
    ephemeral_reclaimable_monthly_usd: number;
  }>;
}

export interface PolicyGateResult {
  policy_package: string;
  allowed: boolean;
  violations: string[];
  engine: string;
}

export interface SecurityFinding {
  id: string;
  scanner: string;
  rule_id: string;
  severity: string;
  title: string;
  file_path: string;
  line: number;
  remediation: string;
  cloud?: string;
}

export interface ScanReport {
  id: string;
  project_id: string;
  target_path: string;
  scanners_executed: string[];
  findings: SecurityFinding[];
  summary: Record<string, number>;
  compliance_score: number;
  opa_gate: PolicyGateResult;
  duration_ms: number;
}

export interface DestroyPreview {
  environment_id: string;
  cloud: CloudProvider;
  resource_group: string;
  tier: string;
  has_delete_lock: boolean;
  lock_mechanism: string;
  ordered_teardown_steps: string[];
  resources: AzureResourceNode[];
  blast_radius_count: number;
  estimated_hourly_savings_usd: number;
  estimated_monthly_savings_usd: number;
  opa_gate: PolicyGateResult;
  confirmation_token: string | null;
}

export interface ExtensionPlugin {
  id: string;
  name: string;
  version: string;
  language: string;
  transport: string;
  endpoint: string;
  capabilities: string[];
  subscribed_topics: string[];
  status: string;
  latency_ms: number;
}

export interface CloudEvent {
  id: string;
  type: string;
  subject: string;
  topic: string;
  time: string;
  project_id: string;
  data: Record<string, unknown>;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  overview: () => req<Record<string, unknown>>("/api/v1/overview"),
  finops: () => req<FinOpsSummary>("/api/v1/finops/summary"),
  projects: () => req<Project[]>("/api/v1/projects"),
  environments: () => req<Environment[]>("/api/v1/environments"),
  driftCheck: (envId: string) => req<Record<string, unknown>>(`/api/v1/drift/${envId}/check`, { method: "POST" }),
  vmCompare: (criteria: Record<string, unknown>) =>
    req<VmComparisonMatrix>("/api/v1/vms/compare", { method: "POST", body: JSON.stringify(criteria) }),
  vmProvision: (body: {
    project_id: string;
    environment_name: string;
    cloud: CloudProvider;
    sku: string;
    region: string;
    use_spot: boolean;
    ttl_hours: number;
  }) => req<Record<string, unknown>>("/api/v1/vms/provision", { method: "POST", body: JSON.stringify(body) }),
  runScan: (project_id: string, target_path: string | null, scanners: string[]) =>
    req<ScanReport>("/api/v1/scans", {
      method: "POST",
      body: JSON.stringify({ project_id, target_path, scanners }),
    }),
  scans: () => req<ScanReport[]>("/api/v1/scans"),
  opaPolicies: () => req<Array<{ name: string; path: string; content: string }>>("/api/v1/policies/opa"),
  destroyPreview: (envId: string) =>
    req<DestroyPreview>(`/api/v1/destroy/${envId}/preview`, { method: "POST" }),
  destroyExecute: (envId: string, confirmation_token: string, kill_switch: boolean) =>
    req<Record<string, unknown>>(`/api/v1/destroy/${envId}/execute`, {
      method: "POST",
      body: JSON.stringify({ confirmation_token, kill_switch, actor: "command-center" }),
    }),
  terraformPlan: (project_id: string, environment_id: string, ttl_hours: number, cloud: CloudProvider = "azure") =>
    req<Record<string, unknown>>("/api/v1/infra/terraform/plan", {
      method: "POST",
      body: JSON.stringify({ project_id, environment_id, ttl_hours, cloud }),
    }),
  ansibleRun: (project_id: string, playbook: string) =>
    req<Record<string, unknown>>("/api/v1/infra/ansible/run", {
      method: "POST",
      body: JSON.stringify({ project_id, playbook, check_mode: false }),
    }),
  k8sLaunch: (body: {
    project_id: string;
    environment_id: string;
    cloud: CloudProvider;
    namespace: string;
    workload_name: string;
    image: string;
    replicas: number;
    mode: string;
  }) => req<Record<string, unknown>>("/api/v1/k8s/launch", { method: "POST", body: JSON.stringify(body) }),
  rbacPlan: (body: {
    cloud: CloudProvider;
    resource_group: string;
    principal_object_id: string;
    personas: string[];
    pim_max_duration_hours: number;
    requested_role_override?: string | null;
  }) => req<Record<string, unknown>>("/api/v1/rbac/powershell-plan", { method: "POST", body: JSON.stringify(body) }),
  extensions: () => req<ExtensionPlugin[]>("/api/v1/extensions"),
  invokeExtension: (extId: string, hook_name: string, payload: Record<string, unknown>) =>
    req<Record<string, unknown>>(`/api/v1/extensions/${extId}/hooks`, {
      method: "POST",
      body: JSON.stringify({ hook_name, payload }),
    }),
  kafkaEvents: () => req<CloudEvent[]>("/api/v1/brokers/kafka/events?limit=25"),
  mcpCall: (payload: Record<string, unknown>) =>
    req<Record<string, unknown>>("/mcp", { method: "POST", body: JSON.stringify(payload) }),
  botStatus: () => req<Record<string, unknown>>("/api/v1/bot/status"),
  botBill: () => req<Record<string, unknown>>("/api/v1/bot/bill"),
  botGetGuardrails: () => req<Record<string, unknown>>("/api/v1/bot/guardrails"),
  botPutGuardrails: (body: Record<string, unknown>) =>
    req<Record<string, unknown>>("/api/v1/bot/guardrails", { method: "PUT", body: JSON.stringify(body) }),
  botGetDirectives: () => req<Record<string, unknown>>("/api/v1/bot/directives"),
  botPutDirectives: (body: Record<string, unknown>) =>
    req<Record<string, unknown>>("/api/v1/bot/directives", { method: "PUT", body: JSON.stringify(body) }),
  botGeneratePrompts: (custom_user_prompt?: string) =>
    req<Record<string, unknown>>("/api/v1/bot/prompts/generate", {
      method: "POST",
      body: JSON.stringify({ custom_user_prompt }),
    }),
  botRunSelfPrompt: (custom_user_prompt?: string) =>
    req<Record<string, unknown>>("/api/v1/bot/self-prompt/run", {
      method: "POST",
      body: JSON.stringify({ custom_user_prompt }),
    }),
  botNaturalPrompt: (prompt: string) =>
    req<Record<string, unknown>>("/api/v1/bot/prompt", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  botLaunchVm: (body: Record<string, unknown>) =>
    req<Record<string, unknown>>("/api/v1/bot/launch/vm", { method: "POST", body: JSON.stringify(body) }),
  botLaunchDocker: (body: Record<string, unknown>) =>
    req<Record<string, unknown>>("/api/v1/bot/launch/docker", { method: "POST", body: JSON.stringify(body) }),
};
