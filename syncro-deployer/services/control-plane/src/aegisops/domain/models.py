"""Pure domain entities and value objects (zero framework or I/O dependencies)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


class CloudProvider(StrEnum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class WorkloadProfile(StrEnum):
    GENERAL_PURPOSE = "general-purpose"
    COMPUTE_OPTIMIZED = "compute-optimized"
    MEMORY_OPTIMIZED = "memory-optimized"
    CONFIDENTIAL_SEC = "confidential-sec"
    GPU_AI = "gpu-ai"


class VmArchitecture(StrEnum):
    X86_64 = "x86_64"
    ARM64 = "arm64"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class EnvironmentTier(StrEnum):
    EPHEMERAL = "ephemeral"
    STAGING = "staging"
    PRODUCTION = "production"


class EnvironmentStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    HARDENED = "hardened"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    QUARANTINED = "quarantined"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class Project(BaseModel):
    id: str
    name: str
    repository: str
    primary_language: str
    owner_team: str
    azure_subscription_id: str = ""
    target_clouds: list[CloudProvider] = Field(default_factory=lambda: [CloudProvider.AZURE])
    tags: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AzureResourceNode(BaseModel):
    """Cloud resource graph node (AWS, GCP, or Azure)."""

    id: str
    name: str
    resource_type: str
    hourly_cost_usd: float
    cloud: CloudProvider = CloudProvider.AZURE
    depends_on: list[str] = Field(default_factory=list)
    protected: bool = False


CloudResourceNode = AzureResourceNode


class Environment(BaseModel):
    id: str
    project_id: str
    name: str
    cloud: CloudProvider = CloudProvider.AZURE
    tier: EnvironmentTier
    location: str = "eastus2"
    resource_group: str
    vm_sku: str | None = None
    status: EnvironmentStatus = EnvironmentStatus.ACTIVE
    ttl_hours: int | None = 4
    expires_at: datetime | None = None
    has_delete_lock: bool = False
    compliance_score: float = 96.0
    hourly_cost_usd: float = 1.85
    resources: list[AzureResourceNode] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class VmSecurityFeatures(BaseModel):
    confidential_compute: bool = False
    confidential_tech: str | None = None  # e.g., AMD SEV-SNP, Intel TDX, AWS Nitro Enclave
    secure_boot: bool = True
    vtpm: bool = True
    imdsv2_or_oslogin: bool = True
    encryption_at_host: bool = True
    cis_hardened_image: str


class VmSku(BaseModel):
    id: str
    cloud: CloudProvider
    sku: str
    family: str
    profile: WorkloadProfile
    architecture: VmArchitecture
    vcpu: int
    memory_gib: float
    gpu_model: str | None = None
    gpu_count: int = 0
    network_gbps: float
    storage_iops: int
    hourly_on_demand_usd: float
    hourly_spot_usd: float
    regions: list[str]
    security: VmSecurityFeatures
    compliance_badges: list[str] = Field(default_factory=list)


class VmSelectionCriteria(BaseModel):
    clouds: list[CloudProvider] = Field(
        default_factory=lambda: [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE]
    )
    workload_profile: WorkloadProfile | None = None
    architecture: VmArchitecture | None = None
    min_vcpu: int = 2
    min_memory_gib: float = 4.0
    max_hourly_budget_usd: float | None = None
    require_confidential_compute: bool = False
    require_gpu: bool = False
    prefer_spot: bool = False
    region: str | None = None
    compliance_framework: str | None = None


class VmRecommendation(BaseModel):
    sku: VmSku
    fit_score: float
    security_score: float
    effective_hourly_usd: float
    effective_monthly_usd: float
    spot_savings_pct: float
    recommended: bool = False
    rationale: list[str] = Field(default_factory=list)
    terraform_snippet: str


class VmComparisonMatrix(BaseModel):
    criteria: VmSelectionCriteria
    best_by_cloud: dict[str, VmRecommendation | None]
    cheapest_cloud: str | None = None
    highest_security_cloud: str | None = None
    max_monthly_savings_vs_priciest_usd: float = 0.0
    ranked_matches: list[VmRecommendation] = Field(default_factory=list)


class VmProvisionRequest(BaseModel):
    project_id: str = "edge-gateway"
    environment_name: str = "ephemeral-vm-01"
    cloud: CloudProvider
    sku: str
    region: str
    use_spot: bool = False
    ttl_hours: int = 4
    enable_confidential_compute: bool = True
    disk_gb: int = 50


class VmProvisionResult(BaseModel):
    provision_id: str = Field(default_factory=lambda: new_id("vmprov"))
    environment: Environment
    selected_sku: VmSku
    terraform_hcl: str
    ansible_inventory_group: str
    iam_abac_tag: str
    job_id: str
    audit_event_id: str
    estimated_monthly_usd: float


class SecurityFinding(BaseModel):
    id: str = Field(default_factory=lambda: new_id("fnd"))
    scanner: str
    rule_id: str
    severity: Severity
    title: str
    file_path: str
    line: int = 1
    remediation: str
    cwe: str | None = None
    cloud: str = "multi"


class PolicyGateResult(BaseModel):
    policy_package: str
    allowed: bool
    violations: list[str] = Field(default_factory=list)
    engine: str = "aegis-rego-evaluator"


class ScanReport(BaseModel):
    id: str = Field(default_factory=lambda: new_id("scan"))
    project_id: str
    target_path: str
    scanners_executed: list[str]
    findings: list[SecurityFinding] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    compliance_score: float
    opa_gate: PolicyGateResult
    sarif_version: str = "2.1.0"
    duration_ms: int
    created_at: datetime = Field(default_factory=utc_now)


class DestroyPreview(BaseModel):
    environment_id: str
    cloud: CloudProvider = CloudProvider.AZURE
    resource_group: str
    tier: EnvironmentTier
    has_delete_lock: bool
    lock_mechanism: str = "Azure CanNotDelete Lock"
    ordered_teardown_steps: list[str]
    resources: list[AzureResourceNode]
    blast_radius_count: int
    estimated_hourly_savings_usd: float
    estimated_monthly_savings_usd: float
    opa_gate: PolicyGateResult
    confirmation_token: str | None = None
    token_expires_in_seconds: int = 300


class DestroyExecutionResult(BaseModel):
    execution_id: str = Field(default_factory=lambda: new_id("dst"))
    environment_id: str
    cloud: CloudProvider = CloudProvider.AZURE
    kill_switch: bool
    status: str
    job_id: str
    steps_completed: list[str]
    resources_destroyed: int
    estimated_monthly_savings_usd: float
    audit_event_id: str
    completed_at: datetime = Field(default_factory=utc_now)


class RbacAssignmentPlan(BaseModel):
    cloud: CloudProvider = CloudProvider.AZURE
    persona: str
    role_name: str
    principal_object_id: str
    scope: str
    scope_level: str
    abac_condition: str = ""
    pim_max_duration_hours: int = 1
    oidc_federated: bool = True
    custom_role_file: str


class PowerShellPermissionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: new_id("rbac"))
    cloud: CloudProvider = CloudProvider.AZURE
    subscription_id: str
    resource_group: str
    assignments: list[RbacAssignmentPlan]
    opa_gate: PolicyGateResult
    powershell_script: str
    what_if_command: str
    created_at: datetime = Field(default_factory=utc_now)


class K8sLaunchRequest(BaseModel):
    project_id: str
    environment_id: str
    cloud: CloudProvider = CloudProvider.AZURE
    namespace: str = "aegisops"
    workload_name: str
    image: str
    replicas: int = 2
    mode: str = "kustomize"  # kustomize | helm | ephemeral-job


class K8sLaunchResult(BaseModel):
    launch_id: str = Field(default_factory=lambda: new_id("k8s"))
    project_id: str
    environment_id: str
    cloud: CloudProvider = CloudProvider.AZURE
    namespace: str
    workload_name: str
    mode: str
    opa_gate: PolicyGateResult
    manifest_yaml: str
    applied_resources: list[str]
    status: str
    created_at: datetime = Field(default_factory=utc_now)


class DriftResourceItem(BaseModel):
    resource_id: str
    resource_type: str
    cloud: CloudProvider
    drifted: bool
    diff_summary: str


class DriftCheckReport(BaseModel):
    check_id: str = Field(default_factory=lambda: new_id("drft"))
    environment_id: str
    cloud: CloudProvider
    engine: str = "go-drift-scanner"
    total_resources: int
    drifted_count: int
    items: list[DriftResourceItem]
    checked_at: datetime = Field(default_factory=utc_now)


class FinOpsCloudBreakdown(BaseModel):
    cloud: CloudProvider
    active_environments: int
    hourly_burn_usd: float
    monthly_projected_usd: float
    ephemeral_reclaimable_monthly_usd: float


class FinOpsSummary(BaseModel):
    total_hourly_usd: float
    total_monthly_projected_usd: float
    total_ephemeral_reclaimable_monthly_usd: float
    by_cloud: list[FinOpsCloudBreakdown]


class ExtensionPlugin(BaseModel):
    id: str
    name: str
    version: str
    language: str  # go | typescript | java | python
    transport: str  # http | grpc | kafka
    endpoint: str
    capabilities: list[str]
    subscribed_topics: list[str] = Field(default_factory=list)
    status: str = "healthy"
    latency_ms: float = 4.2
    registered_at: datetime = Field(default_factory=utc_now)


class CloudEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evt"))
    specversion: str = "1.0"
    type: str
    source: str = "/aegisops/control-plane"
    subject: str
    time: str = Field(default_factory=lambda: utc_now().isoformat())
    datacontenttype: str = "application/json"
    project_id: str = "platform"
    correlation_id: str = Field(default_factory=lambda: new_id("corr"))
    topic: str = "aegis.audit.events"
    data: dict[str, Any] = Field(default_factory=dict)


class QueueJob(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job"))
    queue: str
    routing_key: str
    priority: int = 5
    project_id: str
    environment_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
