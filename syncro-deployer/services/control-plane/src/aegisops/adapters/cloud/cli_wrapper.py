"""Production-hardened Multi-Cloud CLI Wrapper for Azure (az), GCP (gcloud), and AWS (aws).

Features:
- Strictly argv-based execution via asyncio.create_subprocess_exec (zero shell=True).
- Shell metacharacter injection guard, service namespace allowlists, secret-exfiltration
  blocking, production destructive guardrails, output redaction, and timeout enforcement.
- Live execution when mode == "live" and binary is present on PATH; rich deterministic
  simulation responses when mode == "simulation", dry_run=True, or binary is absent.
- Emits Kafka CloudEvents and Redis Pub/Sub live notifications for every invocation.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
import shutil
import time
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from aegisops.adapters.messaging.kafka_bus import KafkaEventBus
from aegisops.adapters.messaging.redis_store import RedisStateStore
from aegisops.config import Settings
from aegisops.domain.models import CloudEvent, utc_now


class CliProvider(StrEnum):
    AZ = "az"
    GCLOUD = "gcloud"
    AWS = "aws"


class CliRiskTier(StrEnum):
    READ_ONLY = "read_only"
    MUTATING = "mutating"
    DESTRUCTIVE = "destructive"


class CliExecutionRequest(BaseModel):
    provider: CliProvider
    args: list[str] = Field(min_length=1, max_length=64)
    dry_run: bool = False
    allow_destructive: bool = False
    allow_secrets: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    subscription_or_project: str | None = None
    region: str | None = None
    actor: str = "control-plane"


class CliGuardrailDecision(BaseModel):
    allowed: bool
    risk_tier: CliRiskTier
    violations: list[str] = Field(default_factory=list)
    redacted_fields_count: int = 0


class CliExecutionResult(BaseModel):
    execution_id: str
    provider: CliProvider
    binary: str
    command: list[str]
    command_preview: str
    mode: Literal["live", "simulation", "dry_run", "blocked"]
    risk_tier: CliRiskTier
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    parsed_json: Any | None = None
    guardrail: CliGuardrailDecision
    binary_installed: bool
    binary_path: str | None = None
    actor: str
    timestamp: datetime = Field(default_factory=utc_now)


class CliPreset(BaseModel):
    id: str
    provider: CliProvider
    title: str
    description: str
    args: list[str]
    risk_tier: CliRiskTier


_FORBIDDEN_SHELL_PATTERN = re.compile(r"(?:[;|`<>]|\$\(|&&|\|\||\r|\n|\x00)")
_SENSITIVE_KEY_RE = re.compile(
    r'("(?:SecretAccessKey|SessionToken|accessToken|refreshToken|clientSecret|password|private_key|privateKey|apiKey|token)"\s*:\s*")([^"]+)(")',
    re.IGNORECASE,
)

ALLOWED_NAMESPACES: dict[CliProvider, set[str]] = {
    CliProvider.AZ: {
        "account",
        "acr",
        "aks",
        "billing",
        "consumption",
        "costmanagement",
        "group",
        "keyvault",
        "lock",
        "monitor",
        "network",
        "policy",
        "resource",
        "role",
        "security",
        "storage",
        "version",
        "vm",
    },
    CliProvider.GCLOUD: {
        "auth",
        "billing",
        "compute",
        "config",
        "container",
        "iam",
        "kms",
        "logging",
        "monitoring",
        "projects",
        "resource-manager",
        "run",
        "scc",
        "secrets",
        "services",
        "storage",
        "version",
    },
    CliProvider.AWS: {
        "--version",
        "ce",
        "cloudformation",
        "cloudtrail",
        "cloudwatch",
        "ecr",
        "ecs",
        "ec2",
        "eks",
        "iam",
        "kms",
        "logs",
        "organizations",
        "rds",
        "s3",
        "s3api",
        "secretsmanager",
        "securityhub",
        "ssm",
        "sts",
    },
}

_DESTRUCTIVE_TOKENS = {
    "delete",
    "destroy",
    "purge",
    "remove",
    "rm",
    "rb",
    "wipe",
    "terminate",
    "terminate-instances",
    "delete-stack",
    "delete-cluster",
    "delete-bucket",
    "delete-db-instance",
    "delete-key",
    "delete-role",
    "delete-user",
    "deallocate",
    "schedule-key-deletion",
    "reset",
}

_MUTATING_PREFIXES = (
    "create",
    "update",
    "set",
    "put",
    "apply",
    "start",
    "stop",
    "restart",
    "scale",
    "deploy",
    "add",
    "attach",
    "detach",
    "assign",
    "enable",
    "disable",
    "run-instances",
    "modify",
    "patch",
    "tag",
    "untag",
    "sync",
    "cp",
    "mv",
)

_SECRET_SUBCOMMANDS: tuple[tuple[CliProvider, tuple[str, ...]], ...] = (
    (CliProvider.AZ, ("keyvault", "secret", "show")),
    (CliProvider.AZ, ("account", "get-access-token")),
    (CliProvider.GCLOUD, ("auth", "print-access-token")),
    (CliProvider.GCLOUD, ("auth", "print-identity-token")),
    (CliProvider.GCLOUD, ("secrets", "versions", "access")),
    (CliProvider.AWS, ("secretsmanager", "get-secret-value")),
    (CliProvider.AWS, ("ssm", "get-parameter")),
    (CliProvider.AWS, ("ecr", "get-login-password")),
)

_PROTECTED_PROD_KEYWORDS = ("prod", "production", "shared-core")
_MAX_OUTPUT_BYTES = 256_000


class MultiCloudCliWrapper:
    """Guardrailed, audited wrapper around Azure CLI (`az`), GCP CLI (`gcloud`), and AWS CLI (`aws`)."""

    def __init__(
        self,
        settings: Settings,
        kafka: KafkaEventBus,
        redis: RedisStateStore,
    ) -> None:
        self._settings = settings
        self._kafka = kafka
        self._redis = redis
        self._history: list[CliExecutionResult] = []
        self._max_history = 200

    def _normalize_args(self, provider: CliProvider, raw_args: list[str]) -> list[str]:
        cleaned = [tok.strip() for tok in raw_args if tok.strip()]
        if cleaned and cleaned[0].lower() == provider.value:
            cleaned = cleaned[1:]
        return cleaned

    def classify_risk(self, args: list[str]) -> CliRiskTier:
        lowered = [a.lower() for a in args]
        for tok in lowered:
            if tok in _DESTRUCTIVE_TOKENS or any(
                tok.startswith(f"{d}-") for d in ("delete", "destroy", "terminate", "purge", "remove")
            ):
                return CliRiskTier.DESTRUCTIVE
        for tok in lowered:
            if any(tok == p or tok.startswith(f"{p}-") for p in _MUTATING_PREFIXES):
                return CliRiskTier.MUTATING
        return CliRiskTier.READ_ONLY

    def evaluate_guardrails(self, req: CliExecutionRequest, args: list[str]) -> CliGuardrailDecision:
        violations: list[str] = []
        if not args:
            return CliGuardrailDecision(
                allowed=False,
                risk_tier=CliRiskTier.READ_ONLY,
                violations=["Command arguments cannot be empty."],
            )

        for tok in args:
            if _FORBIDDEN_SHELL_PATTERN.search(tok):
                violations.append(
                    f"Blocked unsafe shell metacharacter in argument '{tok}'. "
                    "CLI wrapper enforces strict argv execution without shell interpolation."
                )

        root_ns = args[0].lower()
        allowed_ns = ALLOWED_NAMESPACES[req.provider]
        if root_ns not in allowed_ns:
            violations.append(
                f"Service namespace '{root_ns}' is not in the approved {req.provider.value} allowlist "
                f"({', '.join(sorted(allowed_ns)[:8])}...)."
            )

        lowered_tuple = tuple(a.lower() for a in args)
        if not req.allow_secrets:
            for prov, seq in _SECRET_SUBCOMMANDS:
                if prov == req.provider and len(lowered_tuple) >= len(seq) and lowered_tuple[: len(seq)] == seq:
                    violations.append(
                        f"Secret retrieval command '{req.provider.value} {' '.join(seq)}' blocked by default "
                        "Secret-Exfiltration Guardrail (set allow_secrets=true for break-glass access)."
                    )

        risk_tier = self.classify_risk(args)
        if risk_tier == CliRiskTier.DESTRUCTIVE:
            joined = " ".join(lowered_tuple)
            if any(kw in joined for kw in _PROTECTED_PROD_KEYWORDS):
                violations.append(
                    "Destructive CLI invocation targeting a protected production scope is strictly blocked. "
                    "Use the Two-Phase HMAC Quick Destroyer workflow instead."
                )
            elif not req.allow_destructive and not req.dry_run:
                violations.append(
                    f"Destructive command '{req.provider.value} {' '.join(args)}' requires "
                    "allow_destructive=true or dry_run=true."
                )
            if "--all" in lowered_tuple or "--force" in lowered_tuple:
                violations.append(
                    "Broad blast-radius flags (--all / --force) are disallowed on destructive CLI commands."
                )

        return CliGuardrailDecision(
            allowed=len(violations) == 0,
            risk_tier=risk_tier,
            violations=violations,
        )

    def _build_full_command(self, req: CliExecutionRequest, args: list[str]) -> list[str]:
        cmd = [req.provider.value, *args]
        lowered = [a.lower() for a in args]

        if req.subscription_or_project:
            if req.provider == CliProvider.AZ and "--subscription" not in lowered:
                cmd.extend(["--subscription", req.subscription_or_project])
            elif req.provider == CliProvider.GCLOUD and "--project" not in lowered:
                cmd.extend(["--project", req.subscription_or_project])
            elif req.provider == CliProvider.AWS and "--profile" not in lowered:
                cmd.extend(["--profile", req.subscription_or_project])

        if req.region and req.provider == CliProvider.AWS and "--region" not in lowered:
            cmd.extend(["--region", req.region])

        # Enforce machine-readable JSON output when not already specified
        if req.provider == CliProvider.AZ:
            if "--output" not in lowered and "-o" not in lowered and args[0].lower() != "version":
                cmd.extend(["--output", "json"])
        elif req.provider == CliProvider.GCLOUD:
            if not any(a.startswith("--format") for a in lowered) and args[0].lower() != "version":
                cmd.append("--format=json")
        elif req.provider == CliProvider.AWS:
            if "--output" not in lowered and args[0].lower() != "--version":
                cmd.extend(["--output", "json"])

        return cmd

    def _redact_text(self, text: str) -> tuple[str, int]:
        count = 0

        def _repl(match: re.Match[str]) -> str:
            nonlocal count
            count += 1
            return f"{match.group(1)}***REDACTED***{match.group(3)}"

        return _SENSITIVE_KEY_RE.sub(_repl, text), count

    async def execute(self, req: CliExecutionRequest) -> CliExecutionResult:
        started = time.perf_counter()
        exec_id = f"cli-{uuid.uuid4().hex[:10]}"
        args = self._normalize_args(req.provider, req.args)
        decision = self.evaluate_guardrails(req, args)
        binary_path = shutil.which(req.provider.value)
        binary_installed = binary_path is not None

        full_cmd = self._build_full_command(req, args) if args else [req.provider.value]
        cmd_preview = shlex.join(full_cmd)

        if not decision.allowed:
            result = CliExecutionResult(
                execution_id=exec_id,
                provider=req.provider,
                binary=req.provider.value,
                command=full_cmd,
                command_preview=cmd_preview,
                mode="blocked",
                risk_tier=decision.risk_tier,
                exit_code=126,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                stdout="",
                stderr=" | ".join(decision.violations),
                parsed_json={"blocked": True, "violations": decision.violations},
                guardrail=decision,
                binary_installed=binary_installed,
                binary_path=binary_path,
                actor=req.actor,
            )
            await self._record_audit(result, event_type="aegis.cli.blocked")
            return result

        if req.dry_run:
            sim_data = self._simulate_output(req.provider, args, dry_run=True)
            stdout_raw = json.dumps(sim_data, indent=2)
            result = CliExecutionResult(
                execution_id=exec_id,
                provider=req.provider,
                binary=req.provider.value,
                command=full_cmd,
                command_preview=cmd_preview,
                mode="dry_run",
                risk_tier=decision.risk_tier,
                exit_code=0,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                stdout=stdout_raw,
                stderr="",
                parsed_json=sim_data,
                guardrail=decision,
                binary_installed=binary_installed,
                binary_path=binary_path,
                actor=req.actor,
            )
            await self._record_audit(result, event_type="aegis.cli.executed")
            return result

        if self._settings.mode == "live" and binary_installed:
            result = await self._execute_live(
                exec_id=exec_id,
                req=req,
                full_cmd=full_cmd,
                cmd_preview=cmd_preview,
                decision=decision,
                binary_path=binary_path,
                started=started,
            )
            await self._record_audit(result, event_type="aegis.cli.executed")
            return result

        # Deterministic simulation mode (safe local/CI execution without live cloud credentials)
        sim_data = self._simulate_output(req.provider, args, dry_run=False)
        stdout_raw, redacted = self._redact_text(json.dumps(sim_data, indent=2))
        decision.redacted_fields_count = redacted
        result = CliExecutionResult(
            execution_id=exec_id,
            provider=req.provider,
            binary=req.provider.value,
            command=full_cmd,
            command_preview=cmd_preview,
            mode="simulation",
            risk_tier=decision.risk_tier,
            exit_code=0,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            stdout=stdout_raw,
            stderr="",
            parsed_json=sim_data,
            guardrail=decision,
            binary_installed=binary_installed,
            binary_path=binary_path,
            actor=req.actor,
        )
        await self._record_audit(result, event_type="aegis.cli.executed")
        return result

    async def _execute_live(
        self,
        exec_id: str,
        req: CliExecutionRequest,
        full_cmd: list[str],
        cmd_preview: str,
        decision: CliGuardrailDecision,
        binary_path: str | None,
        started: float,
    ) -> CliExecutionResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                full_cmd[0],
                *full_cmd[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=float(req.timeout_seconds)
                )
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                return CliExecutionResult(
                    execution_id=exec_id,
                    provider=req.provider,
                    binary=req.provider.value,
                    command=full_cmd,
                    command_preview=cmd_preview,
                    mode="live",
                    risk_tier=decision.risk_tier,
                    exit_code=124,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    stdout="",
                    stderr=f"Command timed out after {req.timeout_seconds}s and was terminated.",
                    parsed_json=None,
                    guardrail=decision,
                    binary_installed=True,
                    binary_path=binary_path,
                    actor=req.actor,
                )

            stdout_str = stdout_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace").strip()
            stderr_str = stderr_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace").strip()
            stdout_str, r1 = self._redact_text(stdout_str)
            stderr_str, r2 = self._redact_text(stderr_str)
            decision.redacted_fields_count = r1 + r2

            parsed: Any | None = None
            if stdout_str:
                try:
                    parsed = json.loads(stdout_str)
                except json.JSONDecodeError:
                    parsed = None

            return CliExecutionResult(
                execution_id=exec_id,
                provider=req.provider,
                binary=req.provider.value,
                command=full_cmd,
                command_preview=cmd_preview,
                mode="live",
                risk_tier=decision.risk_tier,
                exit_code=int(proc.returncode or 0),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                stdout=stdout_str,
                stderr=stderr_str,
                parsed_json=parsed,
                guardrail=decision,
                binary_installed=True,
                binary_path=binary_path,
                actor=req.actor,
            )
        except Exception as exc:
            return CliExecutionResult(
                execution_id=exec_id,
                provider=req.provider,
                binary=req.provider.value,
                command=full_cmd,
                command_preview=cmd_preview,
                mode="live",
                risk_tier=decision.risk_tier,
                exit_code=1,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                stdout="",
                stderr=str(exc),
                parsed_json=None,
                guardrail=decision,
                binary_installed=True,
                binary_path=binary_path,
                actor=req.actor,
            )

    async def _record_audit(self, result: CliExecutionResult, event_type: str) -> None:
        self._history.insert(0, result)
        if len(self._history) > self._max_history:
            del self._history[self._max_history :]

        evt = CloudEvent(
            type=event_type,
            source=f"/aegisops/cli/{result.provider.value}",
            subject=result.execution_id,
            data={
                "provider": result.provider.value,
                "command": result.command_preview,
                "mode": result.mode,
                "risk_tier": result.risk_tier.value,
                "exit_code": result.exit_code,
                "allowed": result.guardrail.allowed,
                "duration_ms": result.duration_ms,
                "actor": result.actor,
            },
        )
        await self._kafka.publish("aegis.audit.events", evt)
        await self._redis.publish_channel(
            "aegis:live",
            {
                "type": event_type,
                "execution_id": result.execution_id,
                "provider": result.provider.value,
                "command": result.command_preview,
                "mode": result.mode,
                "risk_tier": result.risk_tier.value,
                "exit_code": result.exit_code,
                "allowed": result.guardrail.allowed,
            },
        )

    def history(self, provider: CliProvider | None = None, limit: int = 40) -> list[CliExecutionResult]:
        items = self._history
        if provider is not None:
            items = [i for i in items if i.provider == provider]
        return items[:limit]

    async def toolchain_status(self) -> dict[str, Any]:
        cloud_bins: dict[str, dict[str, Any]] = {}
        for prov in (CliProvider.AZ, CliProvider.GCLOUD, CliProvider.AWS):
            path = shutil.which(prov.value)
            cloud_bins[prov.value] = {
                "provider": prov.value,
                "installed": path is not None,
                "path": path,
                "execution_mode": "live" if (self._settings.mode == "live" and path) else "simulation",
                "allowed_namespaces": sorted(ALLOWED_NAMESPACES[prov]),
                "mcp_tool": f"aegis_{'gcp' if prov == CliProvider.GCLOUD else prov.value}_cli",
            }

        devops_bins = {
            tool: {"installed": shutil.which(tool) is not None, "path": shutil.which(tool)}
            for tool in ("terraform", "kubectl", "docker", "helm", "ansible-playbook", "pwsh", "git")
        }

        return {
            "control_plane_mode": self._settings.mode,
            "guardrails": {
                "zero_shell_execution": True,
                "destructive_requires_explicit_opt_in": True,
                "production_scope_delete_blocked": True,
                "secret_exfiltration_blocked_by_default": True,
                "output_redaction_enabled": True,
                "max_timeout_seconds": 120,
            },
            "cloud_clis": cloud_bins,
            "devops_toolchain": devops_bins,
            "total_executions_recorded": len(self._history),
        }

    def list_presets(self) -> list[CliPreset]:
        return [
            CliPreset(
                id="az-account-show",
                provider=CliProvider.AZ,
                title="Azure Active Subscription",
                description="Inspect current Azure subscription, tenant, and OIDC workload identity.",
                args=["account", "show"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="az-vm-list",
                provider=CliProvider.AZ,
                title="Azure Confidential VMs",
                description="List Azure Virtual Machines with Trusted Launch & vTPM posture.",
                args=["vm", "list"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="az-aks-list",
                provider=CliProvider.AZ,
                title="Azure AKS Clusters",
                description="Enumerate AKS clusters, Kubernetes versions, and private cluster flags.",
                args=["aks", "list"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="az-lock-list",
                provider=CliProvider.AZ,
                title="Azure CanNotDelete Locks",
                description="Audit management locks protecting production resource groups.",
                args=["lock", "list", "--resource-group", "rg-aegis-payments-prod"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="gcp-config-list",
                provider=CliProvider.GCLOUD,
                title="GCP Active Project & Auth",
                description="Inspect active gcloud project, default region, and Workload Identity config.",
                args=["config", "list"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="gcp-compute-list",
                provider=CliProvider.GCLOUD,
                title="GCE Shielded / SEV-SNP VMs",
                description="List Compute Engine instances with Shielded VM & Confidential Compute status.",
                args=["compute", "instances", "list"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="gcp-gke-list",
                provider=CliProvider.GCLOUD,
                title="GCP GKE Clusters",
                description="List GKE clusters with Workload Identity and Dataplane V2 telemetry.",
                args=["container", "clusters", "list"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="gcp-liens-list",
                provider=CliProvider.GCLOUD,
                title="GCP Resource Manager Liens",
                description="Audit active Resource Manager project deletion liens.",
                args=["resource-manager", "liens", "list"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="aws-sts-identity",
                provider=CliProvider.AWS,
                title="AWS STS Caller Identity",
                description="Verify active AWS IAM OIDC WebIdentity role & account ID.",
                args=["sts", "get-caller-identity"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="aws-ec2-instances",
                provider=CliProvider.AWS,
                title="AWS EC2 Fleet (IMDSv2)",
                description="Describe EC2 instances, Nitro Enclaves, Spot lifecycle, and IMDSv2 posture.",
                args=["ec2", "describe-instances"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="aws-eks-clusters",
                provider=CliProvider.AWS,
                title="AWS EKS Clusters",
                description="List Amazon EKS clusters across target regions.",
                args=["eks", "list-clusters"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
            CliPreset(
                id="aws-ce-cost",
                provider=CliProvider.AWS,
                title="AWS Cost Explorer Snapshot",
                description="Inspect MTD unblended AWS spend and Spot/Graviton savings telemetry.",
                args=["ce", "get-cost-and-usage", "--granularity", "MONTHLY"],
                risk_tier=CliRiskTier.READ_ONLY,
            ),
        ]

    def _simulate_output(self, provider: CliProvider, args: list[str], dry_run: bool) -> dict[str, Any]:
        ns = args[0].lower()
        sub = args[1].lower() if len(args) > 1 else ""
        base_meta = {
            "simulated": True,
            "dry_run": dry_run,
            "provider": provider.value,
            "command": f"{provider.value} {' '.join(args)}",
        }

        if provider == CliProvider.AZ:
            if ns == "account":
                return {
                    **base_meta,
                    "id": self._settings.azure_subscription_id,
                    "tenantId": self._settings.azure_tenant_id,
                    "name": "Syncro-AegisOps-Enterprise",
                    "state": "Enabled",
                    "environmentName": "AzureCloud",
                    "authMethod": "OIDC-Federated-Workload-Identity",
                }
            if ns == "vm":
                return {
                    **base_meta,
                    "vms": [
                        {
                            "name": "vm-syncro-payments-pr412",
                            "resourceGroup": "rg-aegis-payments-pr-412",
                            "location": self._settings.azure_location,
                            "vmSize": "Standard_DC4as_v5",
                            "securityType": "ConfidentialVM",
                            "vtpmEnabled": True,
                            "powerState": "VM running",
                        },
                        {
                            "name": "vm-syncro-payments-prod-01",
                            "resourceGroup": "rg-aegis-payments-prod",
                            "location": self._settings.azure_location,
                            "vmSize": "Standard_D8s_v5",
                            "securityType": "TrustedLaunch",
                            "vtpmEnabled": True,
                            "powerState": "VM running",
                        },
                    ],
                }
            if ns == "aks":
                return {
                    **base_meta,
                    "clusters": [
                        {
                            "name": "aks-syncro-payments-prod",
                            "resourceGroup": "rg-aegis-payments-prod",
                            "kubernetesVersion": "1.31.2",
                            "privateCluster": True,
                            "workloadIdentityEnabled": True,
                            "provisioningState": "Succeeded",
                        }
                    ],
                }
            if ns == "lock":
                return {
                    **base_meta,
                    "locks": [
                        {
                            "name": "lock-prod-cannot-delete",
                            "level": "CanNotDelete",
                            "resourceGroup": "rg-aegis-payments-prod",
                            "notes": "Protected production workload lock",
                        }
                    ],
                }
            if ns == "group":
                return {
                    **base_meta,
                    "resourceGroups": [
                        {"name": "rg-aegis-payments-pr-412", "location": self._settings.azure_location, "tier": "ephemeral"},
                        {"name": "rg-aegis-payments-prod", "location": self._settings.azure_location, "tier": "production"},
                    ],
                }
            return {**base_meta, "status": "ok", "namespace": ns, "subcommand": sub}

        if provider == CliProvider.GCLOUD:
            if ns == "config":
                return {
                    **base_meta,
                    "core": {
                        "project": self._settings.gcp_project_id,
                        "account": "syncro-deployer-sa@aegisops-devsecops-sim.iam.gserviceaccount.com",
                    },
                    "compute": {"region": self._settings.gcp_region, "zone": f"{self._settings.gcp_region}-a"},
                }
            if ns == "compute":
                return {
                    **base_meta,
                    "instances": [
                        {
                            "name": "gce-syncro-ml-confidential-01",
                            "zone": f"{self._settings.gcp_region}-a",
                            "machineType": "n2d-standard-4",
                            "confidentialInstanceConfig": {"enableConfidentialCompute": True, "confidentialInstanceType": "SEV_SNP"},
                            "shieldedInstanceConfig": {"enableSecureBoot": True, "enableVtpm": True},
                            "status": "RUNNING",
                        }
                    ],
                }
            if ns == "container":
                return {
                    **base_meta,
                    "clusters": [
                        {
                            "name": "gke-syncro-ml-autopilot",
                            "location": self._settings.gcp_region,
                            "currentMasterVersion": "1.31.2-gke.1100",
                            "autopilot": {"enabled": True},
                            "dataplaneProvider": "ADVANCED_DATAPATH",
                            "status": "RUNNING",
                        }
                    ],
                }
            if ns == "resource-manager":
                return {
                    **base_meta,
                    "liens": [
                        {
                            "name": "liens/p-prod-resourcemanager-guard",
                            "origin": "syncro-aegisops",
                            "reason": "Production workload deletion protection",
                            "restrictions": ["resourcemanager.projects.delete"],
                        }
                    ],
                }
            return {**base_meta, "status": "ok", "namespace": ns, "subcommand": sub}

        # AWS CLI
        if ns == "sts":
            return {
                **base_meta,
                "Account": self._settings.aws_account_id,
                "UserId": "AROASYNCROOIDCDEPLOYER:syncro-session",
                "Arn": f"arn:aws:sts::{self._settings.aws_account_id}:assumed-role/SyncroDeployerOIDCRole/syncro-session",
            }
        if ns == "ec2":
            return {
                **base_meta,
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-0a9f8c7b6e5d41001",
                                "InstanceType": "c7g.xlarge",
                                "State": {"Name": "running"},
                                "Placement": {"AvailabilityZone": f"{self._settings.aws_region}a"},
                                "MetadataOptions": {"HttpTokens": "required", "HttpEndpoint": "enabled"},
                                "InstanceLifecycle": "spot",
                            },
                            {
                                "InstanceId": "i-0a9f8c7b6e5d41002",
                                "InstanceType": "m7i.2xlarge",
                                "State": {"Name": "running"},
                                "Placement": {"AvailabilityZone": f"{self._settings.aws_region}b"},
                                "MetadataOptions": {"HttpTokens": "required", "HttpEndpoint": "enabled"},
                                "EnclaveOptions": {"Enabled": True},
                            },
                        ]
                    }
                ],
            }
        if ns == "eks":
            return {
                **base_meta,
                "clusters": ["eks-syncro-edge-pr501", "eks-syncro-core-prod"],
                "region": self._settings.aws_region,
            }
        if ns == "ce":
            return {
                **base_meta,
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2026-11-01", "End": "2026-11-23"},
                        "Total": {"UnblendedCost": {"Amount": "5184.42", "Unit": "USD"}},
                        "EstimatedSpotSavingsUsd": 1420.80,
                    }
                ],
            }
        return {**base_meta, "status": "ok", "namespace": ns, "subcommand": sub}
