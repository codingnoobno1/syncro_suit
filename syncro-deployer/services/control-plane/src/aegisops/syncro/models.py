"""Domain models for Syncro Deployer (Agentic Mode vs Manual DevOps Mode) and Flutter Desktop Agents."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from aegisops.bot.models import GuardrailDecision, TrafficTechnique
from aegisops.domain.models import CloudProvider, new_id, utc_now


class SyncroMode(StrEnum):
    AGENTIC = "agentic"
    MANUAL = "manual"


class DeploymentStrategy(StrEnum):
    CANARY = "canary"
    BLUE_GREEN = "blue-green"
    ROLLING = "rolling"


class DeploymentTargetType(StrEnum):
    VM = "vm"
    KUBERNETES = "kubernetes"
    DOCKER = "docker"


class DeploymentStage(StrEnum):
    PLANNED = "planned"
    PREFLIGHT_PASSED = "preflight_passed"
    CANARY_5 = "canary_5"
    CANARY_25 = "canary_25"
    PROMOTED_100 = "promoted_100"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"


class DeploymentCheckpoint(BaseModel):
    stage: DeploymentStage
    message: str
    traffic_canary_pct: int
    error_rate_pct: float = 0.0
    p99_latency_ms: float = 18.0
    timestamp: datetime = Field(default_factory=utc_now)


class SyncroDeployRequest(BaseModel):
    project_id: str = "edge-gateway"
    environment_name: str = "syncro-release-01"
    cloud: CloudProvider = CloudProvider.GCP
    target_type: DeploymentTargetType = DeploymentTargetType.KUBERNETES
    strategy: DeploymentStrategy = DeploymentStrategy.CANARY
    mode: SyncroMode | None = None
    vm_sku: str = "n2d-standard-4"
    region: str = "us-central1"
    image: str = "ghcr.io/aegisops/edge-gateway:1.5.0"
    use_spot: bool = True
    ttl_hours: int = 4
    idempotency_key: str | None = None
    traffic_techniques: list[TrafficTechnique] = Field(
        default_factory=lambda: [
            TrafficTechnique.CANARY_WEIGHTED,
            TrafficTechnique.EDGE_CDN_CACHE_WAF,
            TrafficTechnique.KEDA_SCALE_TO_ZERO,
        ]
    )
    auto_rollback_error_rate_pct: float = 2.0
    simulate_canary_fault: bool = False
    requested_by: str = "syncro-desktop"


class SyncroDeployment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("sync"))
    idempotency_key: str | None = None
    idempotent_replay: bool = False
    project_id: str
    environment_name: str
    cloud: CloudProvider
    target_type: DeploymentTargetType
    strategy: DeploymentStrategy
    mode: SyncroMode
    stage: DeploymentStage
    previous_revision: str = "rev-1.4.2-stable"
    target_revision: str = "rev-1.5.0-candidate"
    traffic_split: dict[str, int] = Field(default_factory=lambda: {"stable": 100, "canary": 0})
    vm_sku: str | None = None
    image: str | None = None
    preflight_compliance_score: float = 100.0
    guardrail_decision: GuardrailDecision | None = None
    auto_rolled_back: bool = False
    rollback_reason: str | None = None
    checkpoints: list[DeploymentCheckpoint] = Field(default_factory=list)
    audit_event_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DesktopAgentRegistration(BaseModel):
    agent_id: str = Field(default_factory=lambda: new_id("desk"))
    hostname: str = "workstation-01"
    os_platform: str = "linux"  # linux | macos | windows
    app_version: str = "0.1.0"
    active_mode: SyncroMode = SyncroMode.AGENTIC
    local_tools_detected: list[str] = Field(
        default_factory=lambda: ["docker", "kubectl", "terraform", "az", "aws", "gcloud", "pwsh"]
    )
    status: str = "online"
    last_heartbeat: datetime = Field(default_factory=utc_now)


class DesktopAgentHeartbeat(BaseModel):
    active_mode: SyncroMode = SyncroMode.AGENTIC
    local_tools_detected: list[str] | None = None
    cpu_load_pct: float = 14.2
    memory_used_mb: int = 412
    metadata: dict[str, Any] = Field(default_factory=dict)


class SyncroSuiteModule(BaseModel):
    """Represents a member product of the unified Syncro Suite (project-syncroo.netlify.app)."""

    id: str
    name: str
    role: str
    status: str  # active | connected | planned
    transport: str  # flutter-desktop | rest+ws | cli | mcp | sqlite-wal+redis | gitops-webhook | contract-ready
    capabilities: list[str] = Field(default_factory=list)
    reference_url: str = "https://project-syncroo.netlify.app"
