"""Pydantic v2 domain models for IaC Terraform Studio, Script Writers, and DevSecOps Graphs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from aegisops.domain.models import CloudProvider, new_id, utc_now


class IacBlueprintKind(StrEnum):
    VPC_K8S = "vpc-k8s"
    HARDENED_VM = "hardened-vm"
    SERVERLESS_API = "serverless-api"
    ZERO_TRUST_MESH = "zero-trust-mesh"
    DATA_PLATFORM = "data-platform"


class GeneratedFile(BaseModel):
    path: str
    content: str
    language: str = "hcl"
    lines: int = 0
    sha256: str = ""


class TerraformGenerateRequest(BaseModel):
    project_name: str = "syncro-workload"
    cloud: CloudProvider = CloudProvider.AWS
    blueprint: IacBlueprintKind = IacBlueprintKind.VPC_K8S
    region: str | None = None
    environment: str = "staging"
    enable_confidential_compute: bool = True
    enable_private_endpoints: bool = True
    enable_kms_encryption: bool = True
    enable_waf: bool = True
    enable_monitoring: bool = True
    write_to_disk: bool = True
    output_dir: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class TerraformWorkspaceBundle(BaseModel):
    workspace_id: str = Field(default_factory=lambda: new_id("tfws"))
    project_name: str
    cloud: CloudProvider
    blueprint: IacBlueprintKind
    region: str
    environment: str
    workspace_dir: str
    files: list[GeneratedFile] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    estimated_monthly_usd: float = 0.0
    compliance_controls: list[str] = Field(default_factory=list)
    written_to_disk: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class TerraformBuildResult(BaseModel):
    workspace_id: str
    workspace_dir: str
    engine: str
    init_ok: bool
    fmt_ok: bool
    validate_ok: bool
    syntax_issues: list[str] = Field(default_factory=list)
    resources_discovered: list[str] = Field(default_factory=list)
    modules_discovered: list[str] = Field(default_factory=list)
    variables_discovered: list[str] = Field(default_factory=list)
    outputs_discovered: list[str] = Field(default_factory=list)
    plan_summary: dict[str, int] = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 1


class TerraformRunRequest(BaseModel):
    workspace_id: str | None = None
    workspace_dir: str | None = None
    action: str = "plan"  # plan | apply | destroy
    dry_run: bool = True
    auto_approve: bool = False
    environment: str = "staging"
    vars: dict[str, str] = Field(default_factory=dict)


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    layer: str  # edge | identity | network | compute | data | observability | cicd | security
    cloud: str = "multi"
    risk_level: str = "ok"  # ok | low | medium | high | critical
    findings_count: int = 0
    controls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    encrypted: bool = True
    protocol: str = "TLS 1.3"
    risk_note: str | None = None


class DevSecOpsGraph(BaseModel):
    graph_id: str = Field(default_factory=lambda: new_id("graph"))
    title: str
    cloud: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    security_score: float = 100.0
    blast_radius_summary: dict[str, Any] = Field(default_factory=dict)
    mermaid: str = ""
    dot: str = ""
    ascii_summary: str = ""
    generated_at: datetime = Field(default_factory=utc_now)


class TerraformRunResult(BaseModel):
    workspace_id: str
    workspace_dir: str
    action: str
    engine: str
    dry_run: bool
    guardrail_allowed: bool
    guardrail_reasons: list[str] = Field(default_factory=list)
    exit_code: int = 0
    status: str
    applied_resources: list[str] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)
    devsecops_graph: DevSecOpsGraph | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 1


class AnsibleGenerateRequest(BaseModel):
    service_name: str = "syncro-edge"
    cloud: CloudProvider = CloudProvider.AWS
    os_family: str = "ubuntu-24.04"
    hardening_profile: str = "cis-l2"  # cis-l1 | cis-l2 | pci-dss | zero-trust
    include_docker: bool = True
    include_node_exporter: bool = True
    include_firewall: bool = True
    write_to_disk: bool = True
    output_dir: str | None = None


class HelmGenerateRequest(BaseModel):
    chart_name: str = "syncro-service"
    image: str = "ghcr.io/syncrosuite/syncro-api:1.0.0"
    port: int = 8080
    replicas: int = 3
    cloud: CloudProvider = CloudProvider.AWS
    enable_hpa: bool = True
    enable_network_policy: bool = True
    enable_ingress_tls: bool = True
    enable_pdb: bool = True
    enable_service_monitor: bool = True
    write_to_disk: bool = True
    output_dir: str | None = None


class CicdGenerateRequest(BaseModel):
    project_name: str = "syncro-service"
    platform: str = "github-actions"  # github-actions | gitlab-ci | azure-devops | jenkins
    language: str = "python"  # python | node | go | java | dotnet
    cloud: CloudProvider = CloudProvider.AWS
    deploy_strategy: str = "canary"  # canary | blue-green | rolling
    include_trivy: bool = True
    include_bandit: bool = True
    include_sast: bool = True
    include_dast: bool = True
    include_terraform: bool = True
    include_helm: bool = True
    include_sbom: bool = True
    write_to_disk: bool = True
    output_dir: str | None = None


class ContainerGenerateRequest(BaseModel):
    service_name: str = "syncro-api"
    language: str = "python"  # python | node | go | java
    port: int = 8080
    enable_distroless: bool = True
    write_to_disk: bool = True
    output_dir: str | None = None


class ScriptBundleResult(BaseModel):
    bundle_id: str = Field(default_factory=lambda: new_id("scr"))
    kind: str
    name: str
    output_dir: str
    files: list[GeneratedFile] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    security_controls: list[str] = Field(default_factory=list)
    cli_commands: list[str] = Field(default_factory=list)
    written_to_disk: bool = False
    created_at: datetime = Field(default_factory=utc_now)
