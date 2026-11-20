"""Domain models for the Guardrailed MCP Ops Bot, Live Billing Reader, and Self-Prompt Engine."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from aegisops.domain.models import CloudProvider, new_id, utc_now


class BotAutonomyMode(StrEnum):
    OBSERVE_ONLY = "observe_only"
    RECOMMEND_AND_CONFIRM = "recommend_and_confirm"
    BOUNDED_AUTONOMOUS = "bounded_autonomous"


class TrafficTechnique(StrEnum):
    CANARY_WEIGHTED = "canary-weighted"
    BLUE_GREEN = "blue-green-zero-downtime"
    GEO_LATENCY_ROUTING = "geo-latency-routing"
    EDGE_CDN_CACHE_WAF = "edge-cdn-cache-waf"
    TOKEN_BUCKET_RATE_LIMIT = "token-bucket-rate-limit"  # noqa: S105
    KEDA_SCALE_TO_ZERO = "keda-scale-to-zero"
    ADAPTIVE_LOAD_SHEDDING = "adaptive-load-shedding"


class BotGuardrailSettings(BaseModel):
    """Strict, hard-enforced safety and financial boundaries governing the MCP Ops Bot."""

    autonomy_mode: BotAutonomyMode = BotAutonomyMode.RECOMMEND_AND_CONFIRM
    allowed_clouds: list[CloudProvider] = Field(
        default_factory=lambda: [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE]
    )
    max_monthly_budget_usd: float = 22000.0
    max_single_vm_hourly_usd: float = 0.75
    require_spot_above_hourly_usd: float = 0.35
    max_active_vms: int = 12
    max_active_containers: int = 15
    max_ttl_hours: int = 12
    block_production_mutations: bool = True
    require_non_root_docker: bool = True
    require_read_only_docker_fs: bool = True
    block_latest_image_tag: bool = True
    require_confidential_for_regulated: bool = True
    enable_prompt_injection_firewall: bool = True


class UserPromptDirectives(BaseModel):
    """User-defined trusted directives injected into guardrail & self-prompting cycles."""

    # 1. Billing & Cost-Saving Directives
    target_monthly_cap_usd: float = 9500.0
    prefer_spot_for_non_prod: bool = True
    prefer_arm64_stateless: bool = True
    auto_reap_idle_hours: int = 4
    custom_billing_directive: str = (
        "Prioritize Spot/Preemptible compute for all ephemeral workloads, shift stateless services "
        "to ARM64 (Graviton/Tau/Ampere), and aggressively cache static/API reads at the edge to cut egress."
    )

    # 2. Favorite Infrastructure Stack
    preferred_cloud_order: list[CloudProvider] = Field(
        default_factory=lambda: [CloudProvider.GCP, CloudProvider.AWS, CloudProvider.AZURE]
    )
    favorite_vm_skus: list[str] = Field(
        default_factory=lambda: ["n2d-standard-4", "m7i.xlarge", "Standard_DC4as_v5"]
    )
    favorite_k8s_flavors: list[str] = Field(
        default_factory=lambda: ["GKE Autopilot", "EKS + Karpenter", "AKS + Cilium"]
    )
    favorite_docker_base: str = "gcr.io/distroless/static-debian12:nonroot"
    favorite_regions: dict[str, str] = Field(
        default_factory=lambda: {"aws": "us-east-1", "gcp": "us-central1", "azure": "eastus2"}
    )

    # 3. Favorite Traffic Handling Techniques
    traffic_techniques: list[TrafficTechnique] = Field(
        default_factory=lambda: [
            TrafficTechnique.EDGE_CDN_CACHE_WAF,
            TrafficTechnique.CANARY_WEIGHTED,
            TrafficTechnique.KEDA_SCALE_TO_ZERO,
            TrafficTechnique.TOKEN_BUCKET_RATE_LIMIT,
        ]
    )
    custom_traffic_directive: str = (
        "Route 5% canary traffic first with automated p99/5xx rollback, enforce Redis token-bucket "
        "rate limiting at ingress, and enable KEDA scale-to-zero on non-prod RabbitMQ/Kafka consumers."
    )


class GuardrailDecision(BaseModel):
    allowed: bool
    action_type: str
    policy_package: str = "aegisops.bot.guardrails"
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    enforced_overrides: dict[str, Any] = Field(default_factory=dict)
    prompt_injection_blocked: bool = False
    evaluated_at: datetime = Field(default_factory=utc_now)


class BillLineItem(BaseModel):
    cloud: CloudProvider
    service: str
    resource_id: str
    tier: str
    mtd_cost_usd: float
    hourly_rate_usd: float
    projected_monthly_usd: float
    optimization_tag: str | None = None


class CostSavingOpportunity(BaseModel):
    id: str = Field(default_factory=lambda: new_id("sav"))
    category: str  # spot-migration | ttl-reap | arm64-rightsize | keda-scale-zero | edge-egress-cache
    cloud: str
    title: str
    target_resource: str
    estimated_monthly_savings_usd: float
    risk_level: str = "LOW"
    auto_executable: bool = True
    injected_directive_source: str
    recommended_command: str


class CloudBillSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    billing_period: str
    mtd_spend_usd: float
    daily_burn_usd: float
    forecasted_eom_usd: float
    hard_budget_cap_usd: float
    user_target_cap_usd: float
    budget_utilization_pct: float
    over_user_target: bool
    spend_by_cloud: dict[str, float]
    egress_monthly_usd: float
    line_items: list[BillLineItem]
    saving_opportunities: list[CostSavingOpportunity]
    total_identifiable_monthly_savings_usd: float


class GeneratedPromptBundle(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    guardrail_system_prompt: str
    billing_self_prompt: str
    infra_and_traffic_prompt: str
    mcp_host_snippet: dict[str, Any]
    active_traffic_playbooks: list[dict[str, str]]


class AutoBotActionRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("botact"))
    timestamp: datetime = Field(default_factory=utc_now)
    action_type: str
    summary: str
    status: str  # executed | recommended | blocked_by_guardrail | injection_blocked
    estimated_monthly_delta_usd: float = 0.0
    guardrail_allowed: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


class SelfPromptCycleResult(BaseModel):
    cycle_id: str = Field(default_factory=lambda: new_id("cycle"))
    autonomy_mode: BotAutonomyMode
    injected_self_prompt: str
    guardrail_check: GuardrailDecision
    bill_before_eom_usd: float
    potential_monthly_savings_usd: float
    applied_monthly_savings_usd: float
    actions: list[AutoBotActionRecord]
    audit_event_id: str
    executed_at: datetime = Field(default_factory=utc_now)


class UnifiedStatusSnapshot(BaseModel):
    captured_at: datetime = Field(default_factory=utc_now)
    autonomy_mode: BotAutonomyMode
    clouds_connected: list[str]
    vms_and_environments_active: int
    k8s_launches_count: int
    docker_containers_running: int
    tri_broker_healthy: bool
    bill_forecast_eom_usd: float
    bill_target_cap_usd: float
    identifiable_monthly_savings_usd: float
    guardrail_blocks_count: int
    environments: list[dict[str, Any]]
    docker_containers: list[dict[str, Any]]
    k8s_workloads: list[dict[str, Any]]
    brokers: dict[str, Any]
    recent_bot_feed: list[AutoBotActionRecord]
