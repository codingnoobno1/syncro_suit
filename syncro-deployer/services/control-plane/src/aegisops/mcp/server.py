"""Model Context Protocol (MCP) JSON-RPC 2.0 Server ("prompt and host") for AWS, GCP & Azure."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from aegisops.adapters.cloud.cli_wrapper import CliExecutionRequest, CliProvider
from aegisops.adapters.docker.docker_launcher import DockerLaunchRequest
from aegisops.application.container import build_platform
from aegisops.application.platform_service import PlatformService
from aegisops.bot.models import BotGuardrailSettings, UserPromptDirectives
from aegisops.domain.models import (
    CloudProvider,
    K8sLaunchRequest,
    Project,
    VmProvisionRequest,
    VmSelectionCriteria,
)
from aegisops.iac.models import (
    AnsibleGenerateRequest,
    CicdGenerateRequest,
    ContainerGenerateRequest,
    HelmGenerateRequest,
    TerraformGenerateRequest,
    TerraformRunRequest,
)
from aegisops.syncro.models import SyncroDeployRequest, SyncroMode


class AegisMcpServer:
    """Protocol-compliant MCP Server exposing Multi-Cloud DevSecOps Tools, Resources, and Prompts."""

    PROTOCOL_VERSION = "2024-11-05"

    # MCP tool annotations: lets clients auto-run safe reads and always gate destructive calls.
    READ_ONLY_TOOLS = frozenset(
        {
            "aegis_list_projects",
            "aegis_vm_compare_clouds",
            "aegis_security_scan",
            "aegis_terraform_plan",
            "aegis_preview_destroy",
            "aegis_powershell_rbac_plan",
            "aegis_finops_summary",
            "aegis_drift_scan",
            "aegis_broker_health",
            "aegis_bot_read_all_statuses",
            "aegis_bot_read_bill",
            "aegis_bot_generate_prompts",
            "aegis_syncro_suite_status",
            "aegis_cloud_cli_status",
            "aegis_cloud_cli_history",
            "aegis_iac_terraform_build",
            "aegis_iac_devsecops_graph",
            "aegis_security_mcp_status",
            "aegis_security_trivy_scan",
            "aegis_security_bandit_scan",
            "aegis_security_sast_scan",
            "aegis_security_dast_scan",
            "aegis_security_full_assessment",
        }
    )
    DESTRUCTIVE_TOOLS = frozenset({"aegis_quick_destroy"})

    @staticmethod
    def _compact_json(payload: Any) -> str:
        """Minified JSON keeps MCP tool results ~25-35% smaller for token-limited LLM clients."""
        return json.dumps(payload, separators=(",", ":"), default=str)

    def _annotate(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for tool in tools:
            name = tool["name"]
            tool["annotations"] = {
                "readOnlyHint": name in self.READ_ONLY_TOOLS,
                "destructiveHint": name in self.DESTRUCTIVE_TOOLS,
            }
        return tools

    def __init__(self, platform: PlatformService) -> None:
        self._platform = platform

    def list_tools(self) -> list[dict[str, Any]]:
        return self._annotate(self._tool_definitions())

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "aegis_list_projects",
                "description": "List registered multi-language projects and active AWS/GCP/Azure environments.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_register_project",
                "description": "Register a new Go, TypeScript, Java, or Python project into AegisOps.",
                "inputSchema": {
                    "type": "object",
                    "required": ["id", "name", "repository", "primary_language", "owner_team"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "repository": {"type": "string"},
                        "primary_language": {"type": "string"},
                        "owner_team": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_vm_compare_clouds",
                "description": "Compare and score optimal VM SKUs side-by-side across AWS EC2, GCP Compute Engine, and Azure VMs with Terraform HCL.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "min_vcpu": {"type": "integer", "default": 4},
                        "min_memory_gib": {"type": "number", "default": 16},
                        "workload_profile": {"type": "string"},
                        "require_confidential_compute": {"type": "boolean", "default": False},
                        "prefer_spot": {"type": "boolean", "default": False},
                        "max_hourly_budget_usd": {"type": "number"},
                    },
                },
            },
            {
                "name": "aegis_vm_provision",
                "description": "Provision a hardened ephemeral VM environment on AWS, GCP, or Azure with TTL lease and CIS Terraform HCL.",
                "inputSchema": {
                    "type": "object",
                    "required": ["cloud", "sku", "region"],
                    "properties": {
                        "project_id": {"type": "string", "default": "edge-gateway"},
                        "environment_name": {"type": "string", "default": "mcp-ephemeral-vm"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"]},
                        "sku": {"type": "string"},
                        "region": {"type": "string"},
                        "use_spot": {"type": "boolean", "default": False},
                        "ttl_hours": {"type": "integer", "default": 4},
                    },
                },
            },
            {
                "name": "aegis_security_scan",
                "description": "Run Checkov, Trivy, Bandit, tfsec, and OPA/Rego policy gates across AWS/GCP/Azure IaC, K8s & Python.",
                "inputSchema": {
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {"type": "string"},
                        "target_path": {"type": "string"},
                        "scanners": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            {
                "name": "aegis_terraform_plan",
                "description": "Generate an AWS, GCP, or Azure Landing Zone Terraform plan with ephemeral TTL tags.",
                "inputSchema": {
                    "type": "object",
                    "required": ["project_id", "environment_id"],
                    "properties": {
                        "project_id": {"type": "string"},
                        "environment_id": {"type": "string"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "azure"},
                        "ttl_hours": {"type": "integer", "default": 4},
                    },
                },
            },
            {
                "name": "aegis_ansible_harden",
                "description": "Execute CIS Linux hardening or emergency quarantine Ansible playbook.",
                "inputSchema": {
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {"type": "string"},
                        "playbook": {"type": "string", "default": "cis_azure_linux.yml"},
                        "check_mode": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "aegis_k8s_launch",
                "description": "Launch a hardened Kubernetes Deployment or ephemeral Job gated by OPA policies on EKS, GKE, or AKS.",
                "inputSchema": {
                    "type": "object",
                    "required": ["project_id", "environment_id", "workload_name", "image"],
                    "properties": {
                        "project_id": {"type": "string"},
                        "environment_id": {"type": "string"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "azure"},
                        "namespace": {"type": "string", "default": "aegisops"},
                        "workload_name": {"type": "string"},
                        "image": {"type": "string"},
                        "replicas": {"type": "integer", "default": 2},
                        "mode": {"type": "string", "default": "kustomize"},
                    },
                },
            },
            {
                "name": "aegis_preview_destroy",
                "description": "Preview multi-cloud blast-radius, cost savings, lock/lien guardrails, and mint an HMAC destroy token.",
                "inputSchema": {
                    "type": "object",
                    "required": ["environment_id"],
                    "properties": {"environment_id": {"type": "string"}},
                },
            },
            {
                "name": "aegis_quick_destroy",
                "description": "Execute two-phase Quick Destruction or emergency kill-switch across AWS, GCP, or Azure.",
                "inputSchema": {
                    "type": "object",
                    "required": ["environment_id", "confirmation_token"],
                    "properties": {
                        "environment_id": {"type": "string"},
                        "confirmation_token": {"type": "string"},
                        "kill_switch": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "aegis_powershell_rbac_plan",
                "description": "Generate an OPA-verified least-privilege IAM/ABAC permissions plan for Azure PowerShell, AWS IAM, or GCP gcloud CEL.",
                "inputSchema": {
                    "type": "object",
                    "required": ["resource_group", "principal_object_id"],
                    "properties": {
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "azure"},
                        "resource_group": {"type": "string"},
                        "principal_object_id": {"type": "string"},
                        "personas": {"type": "array", "items": {"type": "string"}},
                        "pim_max_duration_hours": {"type": "integer", "default": 1},
                    },
                },
            },
            {
                "name": "aegis_finops_summary",
                "description": "Return hourly, projected monthly, and reclaimable ephemeral spend broken down across AWS, GCP, and Azure.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_drift_scan",
                "description": "Invoke the Go Concurrent Drift Scanner extension against an AWS, GCP, or Azure environment.",
                "inputSchema": {
                    "type": "object",
                    "required": ["environment_id"],
                    "properties": {"environment_id": {"type": "string"}},
                },
            },
            {
                "name": "aegis_broker_health",
                "description": "Inspect live health of Kafka, RabbitMQ, Redis, and AWS/GCP/Azure adapters.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_bot_read_all_statuses",
                "description": "Read unified live status of all AWS/GCP/Azure VMs, K8s workloads, Docker containers, tri-broker mesh, live bill, and Auto-Bot feed.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_bot_read_bill",
                "description": "Read itemized live multi-cloud billing snapshot (MTD, EOM forecast, egress, and directive-aligned savings).",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_bot_launch_vm",
                "description": "Launch an AWS, GCP, or Azure VM through the strict Bot Guardrail Engine (budget, Spot, Confidential & TTL caps).",
                "inputSchema": {
                    "type": "object",
                    "required": ["cloud", "sku", "region"],
                    "properties": {
                        "project_id": {"type": "string", "default": "edge-gateway"},
                        "environment_name": {"type": "string", "default": "bot-vm"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"]},
                        "sku": {"type": "string"},
                        "region": {"type": "string"},
                        "use_spot": {"type": "boolean", "default": False},
                        "ttl_hours": {"type": "integer", "default": 4},
                    },
                },
            },
            {
                "name": "aegis_bot_launch_docker",
                "description": "Launch a CIS-hardened Docker container gated by strict Bot Guardrails (non-root, RO-fs, no :latest, no --privileged).",
                "inputSchema": {
                    "type": "object",
                    "required": ["name", "image"],
                    "properties": {
                        "name": {"type": "string"},
                        "image": {"type": "string"},
                        "run_as_non_root": {"type": "boolean", "default": True},
                        "read_only_root_fs": {"type": "boolean", "default": True},
                        "privileged": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "aegis_bot_launch_k8s",
                "description": "Launch a Kubernetes workload on EKS/GKE/AKS through strict Bot Guardrails & OPA policies.",
                "inputSchema": {
                    "type": "object",
                    "required": ["project_id", "environment_id", "workload_name", "image"],
                    "properties": {
                        "project_id": {"type": "string"},
                        "environment_id": {"type": "string"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "gcp"},
                        "namespace": {"type": "string", "default": "aegisops"},
                        "workload_name": {"type": "string"},
                        "image": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_bot_generate_prompts",
                "description": "Generate injectable Guardrail System Prompt, Bill-Saving Self-Prompt, and Favorite Infra + Traffic Handling prompts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"custom_user_prompt": {"type": "string"}},
                },
            },
            {
                "name": "aegis_bot_self_prompt_save_bill",
                "description": "Run an Auto-Bot bill-saving self-prompt cycle governed by user directives and strict guardrails.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"custom_user_prompt": {"type": "string"}},
                },
            },
            {
                "name": "aegis_bot_update_guardrails",
                "description": "Update strict MCP Bot guardrail settings (autonomy_mode, budget caps, allowed clouds, Spot threshold).",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "aegis_bot_update_directives",
                "description": "Inject user-defined billing caps, favorite infra, and favorite traffic handling techniques.",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "aegis_bot_prompt",
                "description": "Send a natural-language command to the Guardrailed MCP Bot (scanned by Prompt-Injection Firewall).",
                "inputSchema": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {"prompt": {"type": "string"}},
                },
            },
            {
                "name": "aegis_syncro_suite_status",
                "description": "Inspect all 7 Syncro Suite modules (Desktop, Deployer, CLI, IDE, DB, Git, Tester) and resilience health.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_syncro_set_mode",
                "description": "Switch Syncro Desktop & Deployer between 'agentic' mode and 'manual' DevOps mode.",
                "inputSchema": {
                    "type": "object",
                    "required": ["mode"],
                    "properties": {"mode": {"type": "string", "enum": ["agentic", "manual"]}},
                },
            },
            {
                "name": "aegis_syncro_deploy",
                "description": "Execute an idempotent, lock-safe, preflight-scanned Syncro deployment (Canary/Blue-Green/Rolling) with auto-rollback.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "edge-gateway"},
                        "environment_name": {"type": "string", "default": "syncro-mcp-01"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "gcp"},
                        "target_type": {"type": "string", "enum": ["vm", "kubernetes", "docker"], "default": "kubernetes"},
                        "mode": {"type": "string", "enum": ["agentic", "manual"]},
                        "idempotency_key": {"type": "string"},
                        "simulate_canary_fault": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "aegis_syncro_promote",
                "description": "Manually promote a Manual DevOps deployment gate (CANARY_5 -> CANARY_25 -> PROMOTED_100).",
                "inputSchema": {
                    "type": "object",
                    "required": ["deployment_id"],
                    "properties": {"deployment_id": {"type": "string"}},
                },
            },
            {
                "name": "aegis_syncro_rollback",
                "description": "Instantly rollback a Syncro deployment to its pre-deploy stable revision snapshot.",
                "inputSchema": {
                    "type": "object",
                    "required": ["deployment_id"],
                    "properties": {
                        "deployment_id": {"type": "string"},
                        "reason": {"type": "string", "default": "MCP operator rollback"},
                    },
                },
            },
            {
                "name": "aegis_az_cli",
                "description": "Guardrailed Azure CLI (`az`) MCP wrapper enforcing zero-shell execution, allowlisted namespaces, destructive/production locks, and secret redaction.",
                "inputSchema": {
                    "type": "object",
                    "required": ["args"],
                    "properties": {
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Azure CLI subcommand tokens, e.g. ['vm', 'list'] or ['account', 'show'].",
                        },
                        "dry_run": {"type": "boolean", "default": False},
                        "allow_destructive": {"type": "boolean", "default": False},
                        "allow_secrets": {"type": "boolean", "default": False},
                        "timeout_seconds": {"type": "integer", "default": 30},
                        "subscription": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_gcp_cli",
                "description": "Guardrailed Google Cloud CLI (`gcloud`) MCP wrapper enforcing zero-shell execution, allowlisted namespaces, lien/production locks, and secret redaction.",
                "inputSchema": {
                    "type": "object",
                    "required": ["args"],
                    "properties": {
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "gcloud subcommand tokens, e.g. ['compute', 'instances', 'list'] or ['config', 'list'].",
                        },
                        "dry_run": {"type": "boolean", "default": False},
                        "allow_destructive": {"type": "boolean", "default": False},
                        "allow_secrets": {"type": "boolean", "default": False},
                        "timeout_seconds": {"type": "integer", "default": 30},
                        "project": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_aws_cli",
                "description": "Guardrailed AWS CLI (`aws`) MCP wrapper enforcing zero-shell execution, allowlisted namespaces, destructive/production locks, and secret redaction.",
                "inputSchema": {
                    "type": "object",
                    "required": ["args"],
                    "properties": {
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "AWS CLI subcommand tokens, e.g. ['sts', 'get-caller-identity'] or ['ec2', 'describe-instances'].",
                        },
                        "dry_run": {"type": "boolean", "default": False},
                        "allow_destructive": {"type": "boolean", "default": False},
                        "allow_secrets": {"type": "boolean", "default": False},
                        "timeout_seconds": {"type": "integer", "default": 30},
                        "profile": {"type": "string"},
                        "region": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_cloud_cli_status",
                "description": "Inspect installed az, gcloud, aws, and DevOps CLI binaries, active execution modes, and CLI guardrail rules.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_cloud_cli_history",
                "description": "Retrieve audited execution history for Azure (`az`), GCP (`gcloud`), and AWS (`aws`) CLI invocations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["az", "gcloud", "aws"]},
                        "limit": {"type": "integer", "default": 25},
                    },
                },
            },
            {
                "name": "aegis_iac_terraform_generate",
                "description": "Generate production-hardened multi-file Terraform HCL (providers, variables, security, main, outputs) for AWS, GCP, or Azure.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "default": "syncro-workload"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "aws"},
                        "blueprint": {
                            "type": "string",
                            "enum": ["vpc-k8s", "hardened-vm", "serverless-api", "zero-trust-mesh", "data-platform"],
                            "default": "vpc-k8s",
                        },
                        "region": {"type": "string"},
                        "environment": {"type": "string", "default": "staging"},
                        "enable_waf": {"type": "boolean", "default": True},
                        "write_to_disk": {"type": "boolean", "default": True},
                        "output_dir": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_iac_terraform_build",
                "description": "Build and validate a Terraform workspace (init, fmt check, HCL/validate, resource & DAG extraction).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                        "workspace_dir": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_iac_terraform_run",
                "description": "Run Terraform plan, apply, or destroy with OPA/IaC security guardrails and return a DevSecOps architecture & security graph.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                        "workspace_dir": {"type": "string"},
                        "action": {"type": "string", "enum": ["plan", "apply", "destroy"], "default": "plan"},
                        "dry_run": {"type": "boolean", "default": True},
                        "auto_approve": {"type": "boolean", "default": False},
                        "environment": {"type": "string", "default": "staging"},
                    },
                },
            },
            {
                "name": "aegis_iac_devsecops_graph",
                "description": "Build a DevSecOps dependency & security posture graph (JSON nodes/edges, Mermaid, Graphviz DOT, ASCII) from Terraform IaC and security findings.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string"},
                        "workspace_dir": {"type": "string"},
                        "include_pipeline": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "aegis_script_write_ansible",
                "description": "Generate a CIS/Zero-Trust hardened Ansible playbook, role, handlers, inventory, and ansible.cfg.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string", "default": "syncro-edge"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "aws"},
                        "hardening_profile": {"type": "string", "enum": ["cis-l1", "cis-l2", "pci-dss", "zero-trust"], "default": "cis-l2"},
                        "include_docker": {"type": "boolean", "default": True},
                        "include_firewall": {"type": "boolean", "default": True},
                        "write_to_disk": {"type": "boolean", "default": True},
                        "output_dir": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_script_write_helm",
                "description": "Generate a Restricted Pod-Security Helm v3 chart (Chart.yaml, values.yaml, Deployment, Service, ServiceAccount, NetworkPolicy, HPA, PDB).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chart_name": {"type": "string", "default": "syncro-service"},
                        "image": {"type": "string", "default": "ghcr.io/syncrosuite/syncro-api:1.0.0"},
                        "port": {"type": "integer", "default": 8080},
                        "replicas": {"type": "integer", "default": 3},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "aws"},
                        "enable_network_policy": {"type": "boolean", "default": True},
                        "enable_hpa": {"type": "boolean", "default": True},
                        "write_to_disk": {"type": "boolean", "default": True},
                        "output_dir": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_script_write_cicd",
                "description": "Generate a DevSecOps CI/CD pipeline (GitHub Actions, GitLab CI, Azure DevOps, or Jenkinsfile) integrated with Syncro CLI, Trivy, Bandit, SAST, DAST, and Terraform.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "default": "syncro-service"},
                        "platform": {"type": "string", "enum": ["github-actions", "gitlab-ci", "azure-devops", "jenkins"], "default": "github-actions"},
                        "language": {"type": "string", "enum": ["python", "node", "go", "java", "dotnet"], "default": "python"},
                        "cloud": {"type": "string", "enum": ["aws", "gcp", "azure"], "default": "aws"},
                        "deploy_strategy": {"type": "string", "enum": ["canary", "blue-green", "rolling"], "default": "canary"},
                        "write_to_disk": {"type": "boolean", "default": True},
                        "output_dir": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_script_write_container",
                "description": "Generate a hardened multi-stage non-root Dockerfile (pinned base / distroless) and .dockerignore.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string", "default": "syncro-api"},
                        "language": {"type": "string", "enum": ["python", "node", "go", "java"], "default": "python"},
                        "port": {"type": "integer", "default": 8080},
                        "enable_distroless": {"type": "boolean", "default": True},
                        "write_to_disk": {"type": "boolean", "default": True},
                        "output_dir": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_security_mcp_status",
                "description": "Inspect installed Security & IaC MCP binaries (Trivy, Bandit, Semgrep, Checkov, OPA, Terraform, Ansible, Helm) and guardrails.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "aegis_security_trivy_scan",
                "description": "Run Trivy vulnerability, secret, Dockerfile, Kubernetes/Helm, and IaC misconfiguration assessment.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "syncro-workspace"},
                        "target_path": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_security_bandit_scan",
                "description": "Run Bandit Python AST security assessment (CWE & OWASP mapped).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "syncro-workspace"},
                        "target_path": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_security_sast_scan",
                "description": "Run multi-language SAST assessment (Python, JS/TS, Go, Java, C#, Shell) mapped to OWASP Top 10 & CWE.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "syncro-workspace"},
                        "target_path": {"type": "string"},
                    },
                },
            },
            {
                "name": "aegis_security_dast_scan",
                "description": "Run non-destructive OWASP DAST baseline assessment (TLS, CSP/HSTS/XFO headers, CORS, sensitive path exposure) against a target URL.",
                "inputSchema": {
                    "type": "object",
                    "required": ["target_url"],
                    "properties": {
                        "target_url": {"type": "string", "description": "HTTP/HTTPS endpoint URL to assess"},
                        "project_id": {"type": "string", "default": "syncro-workspace"},
                        "live_probe": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "aegis_security_full_assessment",
                "description": "Run unified DevSecOps security assessment (Trivy + Bandit + SAST + IaC/OPA + optional DAST) with compliance grade, SARIF 2.1.0, and DevSecOps security graph.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "default": "payments-core"},
                        "target_path": {"type": "string"},
                        "target_url": {"type": "string"},
                        "include_dast": {"type": "boolean", "default": True},
                        "include_graph": {"type": "boolean", "default": True},
                        "live_dast_probe": {"type": "boolean", "default": True},
                    },
                },
            },
        ]

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            {"uri": "aegis://syncro/suite", "name": "Syncro Suite 7-Module Topology", "mimeType": "application/json"},
            {"uri": "aegis://syncro/deployments", "name": "Syncro Deployer Persistent Timeline", "mimeType": "application/json"},
            {"uri": "aegis://cli/status", "name": "Multi-Cloud CLI Toolchain Status (az/gcloud/aws)", "mimeType": "application/json"},
            {"uri": "aegis://cli/history", "name": "Multi-Cloud CLI Audited Execution Trail", "mimeType": "application/json"},
            {"uri": "aegis://projects", "name": "Registered Projects", "mimeType": "application/json"},
            {"uri": "aegis://environments", "name": "Multi-Cloud Environments (AWS/GCP/Azure)", "mimeType": "application/json"},
            {"uri": "aegis://vms/catalog", "name": "Multi-Cloud VM SKU Catalog", "mimeType": "application/json"},
            {"uri": "aegis://finops/summary", "name": "Multi-Cloud FinOps Summary", "mimeType": "application/json"},
            {"uri": "aegis://bot/status", "name": "MCP Bot Unified All-Statuses View", "mimeType": "application/json"},
            {"uri": "aegis://bot/bill", "name": "Live Multi-Cloud Billing Snapshot", "mimeType": "application/json"},
            {"uri": "aegis://bot/guardrails", "name": "Strict MCP Bot Guardrail Settings", "mimeType": "application/json"},
            {"uri": "aegis://bot/prompts", "name": "Generated Guardrail & Cost-Saving Prompts", "mimeType": "application/json"},
            {"uri": "aegis://scans/latest", "name": "Latest DevSecOps Scans", "mimeType": "application/json"},
            {"uri": "aegis://policies/opa", "name": "OPA Rego Policies", "mimeType": "application/json"},
            {"uri": "aegis://events/kafka-tail", "name": "Kafka CloudEvents Tail", "mimeType": "application/json"},
            {"uri": "aegis://iac/workspaces", "name": "Generated Terraform IaC Workspaces", "mimeType": "application/json"},
            {"uri": "aegis://iac/graphs/latest", "name": "Latest DevSecOps Architecture & Security Graphs", "mimeType": "application/json"},
            {"uri": "aegis://scripts/bundles", "name": "Generated Ansible, Helm & CI/CD Script Bundles", "mimeType": "application/json"},
            {"uri": "aegis://security/assessments/latest", "name": "Latest Trivy/Bandit/SAST/DAST Security MCP Assessments", "mimeType": "application/json"},
        ]

    def list_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "devsecops_preflight_audit",
                "description": "Run a full multi-cloud pre-deployment DevSecOps audit (Checkov, Trivy, Bandit, tfsec, OPA).",
                "arguments": [{"name": "project_id", "required": True}],
            },
            {
                "name": "multicloud_cli_diagnostics",
                "description": "Inspect live AWS (`aws`), GCP (`gcloud`), and Azure (`az`) accounts, compute fleets, and deletion locks through MCP CLI wrappers.",
                "arguments": [{"name": "focus", "required": False}],
            },
            {
                "name": "multicloud_vm_selection",
                "description": "Compare AWS EC2, GCP Confidential GCE, and Azure Trusted Launch VMs and recommend the best SKU.",
                "arguments": [
                    {"name": "min_vcpu", "required": True},
                    {"name": "require_confidential_compute", "required": False},
                ],
            },
            {
                "name": "autobot_bill_saving_self_prompt",
                "description": "Inject live AWS/GCP/Azure bill + user billing/infra/traffic directives into the Guardrailed MCP Bot.",
                "arguments": [{"name": "custom_user_prompt", "required": False}],
            },
            {
                "name": "emergency_teardown_runbook",
                "description": "Safely preview blast radius, check AWS/GCP/Azure delete protections, and execute kill-switch.",
                "arguments": [{"name": "environment_id", "required": True}],
            },
            {
                "name": "multicloud_least_privilege_review",
                "description": "Audit AWS IAM, GCP CEL, or Azure PowerShell RBAC permissions and verify zero unrestricted Owner/Admin roles.",
                "arguments": [
                    {"name": "cloud", "required": True},
                    {"name": "resource_group", "required": True},
                ],
            },
            {
                "name": "iac_terraform_devsecops_workflow",
                "description": "Generate multi-cloud Terraform HCL, validate/build it, run a guardrailed plan/apply, and produce its DevSecOps architecture graph.",
                "arguments": [
                    {"name": "cloud", "required": True},
                    {"name": "project_name", "required": True},
                ],
            },
            {
                "name": "script_writer_release_bundle",
                "description": "Generate synchronized Ansible hardening, Restricted Helm v3 chart, hardened Dockerfile, and Syncro CLI CI/CD pipeline.",
                "arguments": [
                    {"name": "project_name", "required": True},
                    {"name": "platform", "required": False},
                ],
            },
            {
                "name": "security_mcp_full_audit",
                "description": "Run Trivy, Bandit, multi-language SAST, non-destructive DAST, OPA gate, SARIF 2.1.0 export, and DevSecOps security graph overlay.",
                "arguments": [
                    {"name": "project_id", "required": True},
                    {"name": "target_url", "required": False},
                ],
            },
        ]

    async def handle_jsonrpc(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params") or {}

        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": {"name": "aegisops-mcp", "version": "0.1.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                result = await self._call_tool(params.get("name", ""), params.get("arguments") or {})
            elif method == "resources/list":
                result = {"resources": self.list_resources()}
            elif method == "resources/read":
                result = await self._read_resource(params.get("uri", ""))
            elif method == "prompts/list":
                result = {"prompts": self.list_prompts()}
            elif method == "prompts/get":
                result = self._get_prompt(params.get("name", ""), params.get("arguments") or {})
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    async def _call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        payload: Any
        if name == "aegis_list_projects":
            payload = {
                "projects": [p.model_dump(mode="json") for p in self._platform.projects.values()],
                "environments": [
                    e.model_dump(mode="json") for e in self._platform.environments.values()
                ],
            }
        elif name == "aegis_register_project":
            proj = Project(
                id=args["id"],
                name=args["name"],
                repository=args["repository"],
                primary_language=args["primary_language"],
                owner_team=args["owner_team"],
                azure_subscription_id=self._platform.settings.azure_subscription_id,
            )
            payload = (await self._platform.register_project(proj)).model_dump(mode="json")
        elif name == "aegis_vm_compare_clouds":
            criteria = VmSelectionCriteria.model_validate(args)
            payload = self._platform.vm_selector.compare_clouds(criteria).model_dump(mode="json")
        elif name == "aegis_vm_provision":
            vm_req = VmProvisionRequest.model_validate(args)
            payload = (await self._platform.vm_selector.provision_ephemeral_vm(vm_req)).model_dump(
                mode="json"
            )
        elif name == "aegis_security_scan":
            report = await self._platform.run_security_scan(
                project_id=args["project_id"],
                target_path=args.get("target_path"),
                scanners=args.get("scanners"),
            )
            payload = report.model_dump(mode="json")
        elif name == "aegis_terraform_plan":
            payload = await self._platform.plan_terraform(
                project_id=args["project_id"],
                environment_id=args["environment_id"],
                ttl_hours=int(args.get("ttl_hours", 4)),
                cloud=CloudProvider(args.get("cloud", "azure")),
            )
        elif name == "aegis_ansible_harden":
            payload = await self._platform.run_ansible_hardening(
                project_id=args["project_id"],
                playbook=args.get("playbook", "cis_azure_linux.yml"),
                check_mode=bool(args.get("check_mode", False)),
            )
        elif name == "aegis_k8s_launch":
            k8s_req = K8sLaunchRequest.model_validate(args)
            payload = (await self._platform.launch_kubernetes_workload(k8s_req)).model_dump(mode="json")
        elif name == "aegis_preview_destroy":
            payload = (await self._platform.destroyer.preview(args["environment_id"])).model_dump(
                mode="json"
            )
        elif name == "aegis_quick_destroy":
            res = await self._platform.destroyer.execute(
                environment_id=args["environment_id"],
                confirmation_token=args["confirmation_token"],
                kill_switch=bool(args.get("kill_switch", False)),
                actor="mcp-client",
            )
            payload = res.model_dump(mode="json")
        elif name == "aegis_powershell_rbac_plan":
            plan = await self._platform.generate_powershell_rbac_plan(
                resource_group=args["resource_group"],
                principal_object_id=args["principal_object_id"],
                personas=args.get("personas"),
                pim_max_duration_hours=int(args.get("pim_max_duration_hours", 1)),
                cloud=CloudProvider(args.get("cloud", "azure")),
            )
            payload = plan.model_dump(mode="json")
        elif name == "aegis_finops_summary":
            payload = self._platform.finops_summary().model_dump(mode="json")
        elif name == "aegis_drift_scan":
            payload = (await self._platform.run_drift_check(args["environment_id"])).model_dump(
                mode="json"
            )
        elif name == "aegis_broker_health":
            payload = await self._platform.broker_health()
        elif name == "aegis_bot_read_all_statuses":
            payload = (await self._platform.bot.read_all_statuses()).model_dump(mode="json")
        elif name == "aegis_bot_read_bill":
            payload = self._platform.bot.read_live_bill().model_dump(mode="json")
        elif name == "aegis_bot_launch_vm":
            bot_vm_req = VmProvisionRequest.model_validate(args)
            dec_vm, res_vm = await self._platform.bot.launch_vm_guardrailed(bot_vm_req)
            payload = {
                "guardrail": dec_vm.model_dump(mode="json"),
                "provision": res_vm.model_dump(mode="json") if res_vm else None,
            }
        elif name == "aegis_bot_launch_docker":
            bot_dk_req = DockerLaunchRequest.model_validate(args)
            dec_dk, ctr = await self._platform.bot.launch_docker_guardrailed(bot_dk_req)
            payload = {
                "guardrail": dec_dk.model_dump(mode="json"),
                "container": ctr.model_dump(mode="json") if ctr else None,
            }
        elif name == "aegis_bot_launch_k8s":
            bot_k8s_req = K8sLaunchRequest.model_validate(args)
            dec_k8s, res_k8s = await self._platform.bot.launch_k8s_guardrailed(bot_k8s_req)
            payload = {
                "guardrail": dec_k8s.model_dump(mode="json"),
                "k8s": res_k8s.model_dump(mode="json") if res_k8s else None,
            }
        elif name == "aegis_bot_generate_prompts":
            payload = self._platform.bot.generate_prompts(
                custom_user_prompt=args.get("custom_user_prompt")
            ).model_dump(mode="json")
        elif name == "aegis_bot_self_prompt_save_bill":
            payload = (
                await self._platform.bot.run_self_prompt_bill_saving_cycle(
                    custom_user_prompt=args.get("custom_user_prompt")
                )
            ).model_dump(mode="json")
        elif name == "aegis_bot_update_guardrails":
            cfg = BotGuardrailSettings.model_validate(args)
            payload = self._platform.bot.update_guardrails(cfg).model_dump(mode="json")
        elif name == "aegis_bot_update_directives":
            dirs = UserPromptDirectives.model_validate(args)
            payload = self._platform.bot.update_directives(dirs).model_dump(mode="json")
        elif name == "aegis_bot_prompt":
            payload = await self._platform.bot.execute_natural_prompt(str(args["prompt"]))
        elif name == "aegis_syncro_suite_status":
            payload = {
                "suite_reference": "https://project-syncroo.netlify.app",
                "resilience": self._platform.syncro.resilience_health(),
                "modules": [m.model_dump(mode="json") for m in self._platform.syncro.suite_modules()],
            }
        elif name == "aegis_syncro_set_mode":
            payload = await self._platform.syncro.set_mode(SyncroMode(str(args["mode"]).lower()))
        elif name == "aegis_syncro_deploy":
            sync_req = SyncroDeployRequest.model_validate(args)
            payload = (await self._platform.syncro.deploy(sync_req)).model_dump(mode="json")
        elif name == "aegis_syncro_promote":
            payload = (await self._platform.syncro.promote(str(args["deployment_id"]), actor="mcp-client")).model_dump(
                mode="json"
            )
        elif name == "aegis_syncro_rollback":
            payload = (
                await self._platform.syncro.rollback(
                    str(args["deployment_id"]),
                    reason=str(args.get("reason", "MCP operator rollback")),
                    actor="mcp-client",
                )
            ).model_dump(mode="json")
        elif name in {"aegis_az_cli", "aegis_gcp_cli", "aegis_aws_cli"}:
            provider_map = {
                "aegis_az_cli": CliProvider.AZ,
                "aegis_gcp_cli": CliProvider.GCLOUD,
                "aegis_aws_cli": CliProvider.AWS,
            }
            sub_or_proj = args.get("subscription") or args.get("project") or args.get("profile")
            cli_req = CliExecutionRequest(
                provider=provider_map[name],
                args=[str(item) for item in (args.get("args") or [])],
                dry_run=bool(args.get("dry_run", False)),
                allow_destructive=bool(args.get("allow_destructive", False)),
                allow_secrets=bool(args.get("allow_secrets", False)),
                timeout_seconds=int(args.get("timeout_seconds", 30)),
                subscription_or_project=str(sub_or_proj) if sub_or_proj else None,
                region=str(args["region"]) if args.get("region") else None,
                actor="mcp-client",
            )
            payload = (await self._platform.cloud_cli.execute(cli_req)).model_dump(mode="json")
        elif name == "aegis_cloud_cli_status":
            payload = await self._platform.cloud_cli.toolchain_status()
        elif name == "aegis_cloud_cli_history":
            prov_arg = args.get("provider")
            prov = CliProvider(str(prov_arg).lower()) if prov_arg else None
            limit = int(args.get("limit", 25))
            payload = [
                item.model_dump(mode="json")
                for item in self._platform.cloud_cli.history(provider=prov, limit=limit)
            ]
        elif name == "aegis_iac_terraform_generate":
            tf_gen_req = TerraformGenerateRequest.model_validate(args)
            payload = self._platform.iac_studio.generate(tf_gen_req).model_dump(mode="json")
        elif name == "aegis_iac_terraform_build":
            payload = (
                await self._platform.iac_studio.build(
                    workspace_id=args.get("workspace_id"),
                    workspace_dir=args.get("workspace_dir"),
                )
            ).model_dump(mode="json")
        elif name == "aegis_iac_terraform_run":
            tf_run_req = TerraformRunRequest.model_validate(args)
            payload = (await self._platform.iac_studio.run(tf_run_req)).model_dump(mode="json")
        elif name == "aegis_iac_devsecops_graph":
            payload = self._platform.iac_studio.build_graph(
                workspace_id=args.get("workspace_id"),
                workspace_dir=args.get("workspace_dir"),
                include_pipeline=bool(args.get("include_pipeline", True)),
            ).model_dump(mode="json")
        elif name == "aegis_script_write_ansible":
            ans_req = AnsibleGenerateRequest.model_validate(args)
            payload = self._platform.script_writers.generate_ansible(ans_req).model_dump(mode="json")
        elif name == "aegis_script_write_helm":
            helm_req = HelmGenerateRequest.model_validate(args)
            payload = self._platform.script_writers.generate_helm(helm_req).model_dump(mode="json")
        elif name == "aegis_script_write_cicd":
            cicd_req = CicdGenerateRequest.model_validate(args)
            payload = self._platform.script_writers.generate_cicd(cicd_req).model_dump(mode="json")
        elif name == "aegis_script_write_container":
            ctr_req = ContainerGenerateRequest.model_validate(args)
            payload = self._platform.script_writers.generate_container(ctr_req).model_dump(mode="json")
        elif name == "aegis_security_mcp_status":
            payload = self._platform.security_mcp.toolchain_status()
        elif name == "aegis_security_trivy_scan":
            tpath = Path(args["target_path"]) if args.get("target_path") else self._platform.settings.repo_root
            payload = (
                await self._platform.security_mcp.run_trivy(
                    target_path=tpath,
                    project_id=str(args.get("project_id", "syncro-workspace")),
                )
            ).model_dump(mode="json")
        elif name == "aegis_security_bandit_scan":
            tpath = Path(args["target_path"]) if args.get("target_path") else self._platform.settings.repo_root
            payload = (
                await self._platform.security_mcp.run_bandit(
                    target_path=tpath,
                    project_id=str(args.get("project_id", "syncro-workspace")),
                )
            ).model_dump(mode="json")
        elif name == "aegis_security_sast_scan":
            tpath = Path(args["target_path"]) if args.get("target_path") else self._platform.settings.repo_root
            payload = (
                await self._platform.security_mcp.run_sast(
                    target_path=tpath,
                    project_id=str(args.get("project_id", "syncro-workspace")),
                )
            ).model_dump(mode="json")
        elif name == "aegis_security_dast_scan":
            payload = (
                await self._platform.security_mcp.run_dast(
                    target_url=str(args["target_url"]),
                    project_id=str(args.get("project_id", "syncro-workspace")),
                    live_probe=bool(args.get("live_probe", True)),
                )
            ).model_dump(mode="json")
        elif name == "aegis_security_full_assessment":
            tpath = Path(args["target_path"]) if args.get("target_path") else self._platform.settings.repo_root
            payload = (
                await self._platform.security_mcp.run_full_assessment(
                    project_id=str(args.get("project_id", "payments-core")),
                    target_path=tpath,
                    target_url=args.get("target_url"),
                    include_dast=bool(args.get("include_dast", True)),
                    include_graph=bool(args.get("include_graph", True)),
                    live_dast_probe=bool(args.get("live_dast_probe", True)),
                )
            ).model_dump(mode="json")
        else:
            raise ValueError(f"Unknown MCP tool: {name}")

        return {
            "content": [{"type": "text", "text": self._compact_json(payload)}],
            "isError": False,
        }

    async def _read_resource(self, uri: str) -> dict[str, Any]:
        data: Any
        if uri == "aegis://syncro/suite":
            data = [m.model_dump(mode="json") for m in self._platform.syncro.suite_modules()]
        elif uri == "aegis://syncro/deployments":
            data = [d.model_dump(mode="json") for d in self._platform.syncro.list_deployments()]
        elif uri == "aegis://cli/status":
            data = await self._platform.cloud_cli.toolchain_status()
        elif uri == "aegis://cli/history":
            data = [item.model_dump(mode="json") for item in self._platform.cloud_cli.history(limit=40)]
        elif uri == "aegis://projects":
            data = [p.model_dump(mode="json") for p in self._platform.projects.values()]
        elif uri == "aegis://environments":
            data = [e.model_dump(mode="json") for e in self._platform.environments.values()]
        elif uri == "aegis://vms/catalog":
            data = [sku.model_dump(mode="json") for sku in self._platform.vm_selector.list_catalog()]
        elif uri == "aegis://finops/summary":
            data = self._platform.finops_summary().model_dump(mode="json")
        elif uri == "aegis://bot/status":
            data = (await self._platform.bot.read_all_statuses()).model_dump(mode="json")
        elif uri == "aegis://bot/bill":
            data = self._platform.bot.read_live_bill().model_dump(mode="json")
        elif uri == "aegis://bot/guardrails":
            data = self._platform.bot.guardrail_engine.settings.model_dump(mode="json")
        elif uri == "aegis://bot/prompts":
            data = self._platform.bot.generate_prompts().model_dump(mode="json")
        elif uri == "aegis://scans/latest":
            data = [s.model_dump(mode="json") for s in self._platform.scan_history[:10]]
        elif uri == "aegis://policies/opa":
            data = self._platform.opa_gate.list_policy_files()
        elif uri == "aegis://events/kafka-tail":
            events = await self._platform.kafka.list_events(limit=20)
            data = [e.model_dump(mode="json") for e in events]
        elif uri == "aegis://iac/workspaces":
            data = [w.model_dump(mode="json") for w in self._platform.iac_studio.list_workspaces()]
        elif uri == "aegis://iac/graphs/latest":
            data = [g.model_dump(mode="json") for g in self._platform.iac_studio.latest_graphs[:5]]
        elif uri == "aegis://scripts/bundles":
            data = [b.model_dump(mode="json") for b in self._platform.script_writers.list_bundles()]
        elif uri == "aegis://security/assessments/latest":
            data = [a.model_dump(mode="json") for a in self._platform.security_mcp.history[:10]]
        else:
            raise ValueError(f"Unknown MCP resource URI: {uri}")

        return {
            "contents": [
                {"uri": uri, "mimeType": "application/json", "text": self._compact_json(data)}
            ]
        }

    def _get_prompt(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "autobot_bill_saving_self_prompt":
            bundle = self._platform.bot.generate_prompts(
                custom_user_prompt=args.get("custom_user_prompt")
            )
            return {
                "description": "AegisOps Guardrail + Bill-Saving Self-Prompt Bundle",
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": f"{bundle.guardrail_system_prompt}\n\n{bundle.billing_self_prompt}"}}
                ],
            }
        templates = {
            "devsecops_preflight_audit": (
                f"Run `aegis_security_scan` for project '{args.get('project_id', 'payments-core')}', "
                "inspect AWS/GCP/Azure OPA violations, and list prioritized remediation actions."
            ),
            "multicloud_cli_diagnostics": (
                f"Inspect multi-cloud posture ({args.get('focus', 'compute, locks, and billing')}) by calling "
                "`aegis_cloud_cli_status`, `aegis_az_cli` (['vm', 'list']), `aegis_gcp_cli` "
                "(['compute', 'instances', 'list']), and `aegis_aws_cli` (['ec2', 'describe-instances'])."
            ),
            "multicloud_vm_selection": (
                f"Call `aegis_vm_compare_clouds` with min_vcpu={args.get('min_vcpu', 4)} and "
                f"require_confidential_compute={args.get('require_confidential_compute', True)}, "
                "compare AWS EC2 vs GCP Shielded GCE vs Azure Confidential VM pricing and security."
            ),
            "emergency_teardown_runbook": (
                f"Call `aegis_preview_destroy` on '{args.get('environment_id', 'env-aws-edge-501')}', verify "
                "tier != production and no cloud delete lock/lien is active, then execute `aegis_quick_destroy`."
            ),
            "multicloud_least_privilege_review": (
                f"Generate a least-privilege IAM/ABAC plan on {args.get('cloud', 'aws')} for scope "
                f"'{args.get('resource_group', 'aws-stack-edge-pr-501')}' and verify zero Owner/Admin roles."
            ),
            "iac_terraform_devsecops_workflow": (
                f"Call `aegis_iac_terraform_generate` for project '{args.get('project_name', 'syncro-workload')}' on "
                f"{args.get('cloud', 'aws')}, run `aegis_iac_terraform_build` to validate HCL, run `aegis_iac_terraform_run` "
                "(dry_run=true), and inspect the emitted DevSecOps architecture graph."
            ),
            "script_writer_release_bundle": (
                f"Generate a complete DevSecOps release bundle for '{args.get('project_name', 'syncro-service')}' "
                f"(platform={args.get('platform', 'github-actions')}) using `aegis_script_write_ansible`, "
                "`aegis_script_write_helm`, `aegis_script_write_container`, and `aegis_script_write_cicd`."
            ),
            "security_mcp_full_audit": (
                f"Run `aegis_security_full_assessment` for project '{args.get('project_id', 'payments-core')}' "
                f"(target_url='{args.get('target_url', 'http://127.0.0.1:8080/api/v1/health')}'), review Trivy, Bandit, "
                "SAST, DAST, and OPA violations, and output prioritized remediation steps."
            ),
        }
        if name not in templates:
            raise ValueError(f"Unknown MCP prompt: {name}")
        return {
            "description": f"AegisOps prompt template: {name}",
            "messages": [{"role": "user", "content": {"type": "text", "text": templates[name]}}],
        }

    async def serve_stdio(self) -> None:
        """Line-delimited JSON-RPC 2.0 loop over stdin/stdout for local MCP hosts."""
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            raw = line.strip()
            if not raw:
                continue
            try:
                req = json.loads(raw)
            except json.JSONDecodeError as exc:
                err = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()
                continue
            resp = await self.handle_jsonrpc(req)
            if req.get("id") is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


def run_stdio_entrypoint() -> None:
    platform = build_platform()
    server = AegisMcpServer(platform)
    asyncio.run(server.serve_stdio())
