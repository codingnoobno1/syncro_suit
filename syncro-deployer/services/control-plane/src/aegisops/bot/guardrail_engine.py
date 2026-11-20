"""Strict Guardrail Engine + Adversarial Prompt-Injection Firewall governing the MCP Ops Bot."""

from __future__ import annotations

import re

from aegisops.adapters.docker.docker_launcher import DockerLaunchRequest
from aegisops.bot.models import BotGuardrailSettings, GuardrailDecision
from aegisops.domain.models import K8sLaunchRequest, VmProvisionRequest, VmSku


class BotGuardrailEngine:
    """Enforces non-bypassable financial, cloud, container, and prompt-safety guardrails."""

    _INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("guardrail-override", re.compile(r"(ignore|bypass|disable|turn\s+off|skip)\s+(all\s+)?(previous|prior|system|opa|safety|bot)?\s*(instructions|guardrails|policy|policies|rules|budget)", re.IGNORECASE)),
        ("privileged-escape", re.compile(r"(--privileged|privileged\s*[:=]\s*true|cap-add\s*=\s*SYS_ADMIN|hostPID|hostNetwork)", re.IGNORECASE)),
        ("prod-wipe", re.compile(r"(delete|destroy|wipe|drop)\s+(all\s+)?(prod|production|everything)", re.IGNORECASE)),
        ("shell-destructive", re.compile(r"(rm\s+-rf\s+/|curl\s+[^|]+\|\s*(ba)?sh|sudo\s+su)", re.IGNORECASE)),
    )

    def __init__(self, settings: BotGuardrailSettings | None = None) -> None:
        self.settings = settings or BotGuardrailSettings()

    def update_settings(self, new_settings: BotGuardrailSettings) -> BotGuardrailSettings:
        self.settings = new_settings
        return self.settings

    def scan_prompt_safety(self, prompt_text: str) -> GuardrailDecision:
        if not self.settings.enable_prompt_injection_firewall:
            return GuardrailDecision(
                allowed=True,
                action_type="prompt_safety_check",
                warnings=["Prompt-injection firewall is disabled by operator setting"],
            )

        violations: list[str] = []
        for label, pattern in self._INJECTION_PATTERNS:
            if pattern.search(prompt_text):
                violations.append(
                    f"Prompt-injection / unsafe override pattern '{label}' blocked by strict guardrail firewall"
                )

        return GuardrailDecision(
            allowed=len(violations) == 0,
            action_type="prompt_safety_check",
            violations=violations,
            prompt_injection_blocked=len(violations) > 0,
        )

    def evaluate_vm_launch(
        self,
        req: VmProvisionRequest,
        sku: VmSku,
        current_active_vms: int,
        current_projected_monthly_usd: float,
    ) -> GuardrailDecision:
        violations: list[str] = []
        warnings: list[str] = []
        overrides: dict[str, object] = {}

        if req.cloud not in self.settings.allowed_clouds:
            violations.append(
                f"Cloud '{req.cloud.value}' is not in guardrail allowed_clouds {[c.value for c in self.settings.allowed_clouds]}"
            )

        if current_active_vms >= self.settings.max_active_vms:
            violations.append(
                f"Active VM/environment count ({current_active_vms}) reached guardrail cap ({self.settings.max_active_vms})"
            )

        effective_use_spot = req.use_spot
        eff_hr = sku.hourly_spot_usd if effective_use_spot else sku.hourly_on_demand_usd

        if not effective_use_spot and eff_hr > self.settings.require_spot_above_hourly_usd:
            effective_use_spot = True
            eff_hr = sku.hourly_spot_usd
            overrides["use_spot"] = True
            warnings.append(
                f"Auto-enforced Spot/Preemptible pricing because On-Demand (${sku.hourly_on_demand_usd:.3f}/h) "
                f"exceeded require_spot_above_hourly_usd (${self.settings.require_spot_above_hourly_usd:.2f}/h)"
            )

        if eff_hr > self.settings.max_single_vm_hourly_usd:
            violations.append(
                f"VM SKU '{sku.sku}' hourly cost (${eff_hr:.3f}/h) exceeds max_single_vm_hourly_usd "
                f"(${self.settings.max_single_vm_hourly_usd:.2f}/h)"
            )

        new_monthly = round(current_projected_monthly_usd + eff_hr * 730.0, 2)
        if new_monthly > self.settings.max_monthly_budget_usd:
            violations.append(
                f"Projected monthly bill (${new_monthly:.2f}) would exceed hard max_monthly_budget_usd "
                f"(${self.settings.max_monthly_budget_usd:.2f})"
            )

        if req.ttl_hours > self.settings.max_ttl_hours:
            overrides["ttl_hours"] = self.settings.max_ttl_hours
            warnings.append(
                f"Clamped ephemeral TTL from {req.ttl_hours}h to guardrail max_ttl_hours ({self.settings.max_ttl_hours}h)"
            )

        if (
            self.settings.require_confidential_for_regulated
            and req.project_id in {"payments-core", "ai-inference"}
            and not sku.security.confidential_compute
        ):
            violations.append(
                f"Regulated project '{req.project_id}' requires Confidential Compute (SEV-SNP/TDX/Nitro), "
                f"but '{sku.sku}' lacks hardware confidential computing"
            )

        return GuardrailDecision(
            allowed=len(violations) == 0,
            action_type="launch_vm",
            violations=violations,
            warnings=warnings,
            enforced_overrides=overrides,
        )

    def evaluate_docker_launch(
        self, req: DockerLaunchRequest, current_running_containers: int
    ) -> GuardrailDecision:
        violations: list[str] = []
        warnings: list[str] = []

        if current_running_containers >= self.settings.max_active_containers:
            violations.append(
                f"Running Docker containers ({current_running_containers}) reached cap ({self.settings.max_active_containers})"
            )
        if req.privileged:
            violations.append("Privileged Docker containers (--privileged) are strictly forbidden")
        if self.settings.require_non_root_docker and not req.run_as_non_root:
            violations.append("Docker container MUST set run_as_non_root=True (UID 10001)")
        if self.settings.require_read_only_docker_fs and not req.read_only_root_fs:
            violations.append("Docker container MUST enforce read_only_root_fs=True")
        if self.settings.block_latest_image_tag and (
            req.image.endswith(":latest") or ":" not in req.image
        ):
            violations.append(
                f"Docker image '{req.image}' uses mutable ':latest' or untagged reference; pin immutable version"
            )
        if req.memory_limit_mb > 4096:
            violations.append(
                f"Docker memory limit ({req.memory_limit_mb}MiB) exceeds 4096MiB guardrail ceiling"
            )

        return GuardrailDecision(
            allowed=len(violations) == 0,
            action_type="launch_docker",
            violations=violations,
            warnings=warnings,
        )

    def evaluate_k8s_launch(self, req: K8sLaunchRequest) -> GuardrailDecision:
        violations: list[str] = []
        if req.cloud not in self.settings.allowed_clouds:
            violations.append(f"Kubernetes target cloud '{req.cloud.value}' is disallowed by guardrails")
        if self.settings.block_production_mutations and "prod" in req.namespace.lower():
            violations.append(
                f"Bot guardrail blocks direct mutations in production namespace '{req.namespace}'"
            )
        if self.settings.block_latest_image_tag and (
            req.image.endswith(":latest") or ":" not in req.image
        ):
            violations.append(
                f"Kubernetes image '{req.image}' uses mutable ':latest' tag; pin immutable digest/version"
            )
        if req.replicas > 10:
            violations.append(f"Replica count ({req.replicas}) exceeds bot guardrail limit of 10")

        return GuardrailDecision(
            allowed=len(violations) == 0,
            action_type="launch_k8s",
            violations=violations,
        )
