"""Guardrailed Autonomous MCP Ops Bot orchestrating VMs, Kubernetes, Docker, Billing & Self-Prompting."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from aegisops.adapters.docker.docker_launcher import (
    DockerContainerStatus,
    DockerLauncherAdapter,
    DockerLaunchRequest,
)
from aegisops.bot.billing_reader import CloudBillingReader
from aegisops.bot.guardrail_engine import BotGuardrailEngine
from aegisops.bot.models import (
    AutoBotActionRecord,
    BotAutonomyMode,
    BotGuardrailSettings,
    CloudBillSnapshot,
    GeneratedPromptBundle,
    GuardrailDecision,
    SelfPromptCycleResult,
    UnifiedStatusSnapshot,
    UserPromptDirectives,
)
from aegisops.bot.prompt_composer import PromptDirectiveComposer
from aegisops.domain.exceptions import PolicyViolationError
from aegisops.domain.models import (
    CloudEvent,
    CloudProvider,
    EnvironmentStatus,
    K8sLaunchRequest,
    K8sLaunchResult,
    VmProvisionRequest,
    VmProvisionResult,
)

if TYPE_CHECKING:
    from aegisops.application.platform_service import PlatformService


class AegisMcpBotService:
    """Strict-guardrailed MCP Bot able to launch VMs/K8s/Docker, read all statuses & bills, and self-prompt cost savings."""

    def __init__(
        self,
        platform: PlatformService,
        docker: DockerLauncherAdapter,
        guardrails: BotGuardrailSettings | None = None,
        directives: UserPromptDirectives | None = None,
    ) -> None:
        self._platform = platform
        self.docker = docker
        self.guardrail_engine = BotGuardrailEngine(guardrails)
        self.billing_reader = CloudBillingReader()
        self.prompt_composer = PromptDirectiveComposer()
        self.directives = directives or UserPromptDirectives()
        self.action_feed: list[AutoBotActionRecord] = []
        self._guardrail_blocks = 0

    def update_guardrails(self, settings: BotGuardrailSettings) -> BotGuardrailSettings:
        updated = self.guardrail_engine.update_settings(settings)
        self.action_feed.insert(
            0,
            AutoBotActionRecord(
                action_type="guardrails.updated",
                summary=f"Guardrails updated: mode={updated.autonomy_mode.value}, hard cap=${updated.max_monthly_budget_usd:,.0f}/mo",
                status="executed",
            ),
        )
        return updated

    def update_directives(self, directives: UserPromptDirectives) -> UserPromptDirectives:
        self.directives = directives
        self.action_feed.insert(
            0,
            AutoBotActionRecord(
                action_type="directives.updated",
                summary=(
                    f"User directives injected: target=${directives.target_monthly_cap_usd:,.0f}/mo, "
                    f"traffic={len(directives.traffic_techniques)} techniques"
                ),
                status="executed",
            ),
        )
        return self.directives

    def read_live_bill(self) -> CloudBillSnapshot:
        return self.billing_reader.read_bill(
            environments=self._platform.environments,
            containers=self.docker.list_containers(),
            guardrails=self.guardrail_engine.settings,
            directives=self.directives,
        )

    def generate_prompts(self, custom_user_prompt: str | None = None) -> GeneratedPromptBundle:
        bill = self.read_live_bill()
        return self.prompt_composer.compose(
            guardrails=self.guardrail_engine.settings,
            directives=self.directives,
            bill=bill,
            custom_user_prompt=custom_user_prompt,
        )

    async def read_all_statuses(self) -> UnifiedStatusSnapshot:
        bill = self.read_live_bill()
        brokers = await self._platform.broker_health()
        active_envs = [
            e for e in self._platform.environments.values() if e.status != EnvironmentStatus.DESTROYED
        ]
        containers = self.docker.list_containers()
        running_ctrs = [c for c in containers if c.state == "running"]
        brokers_ok = all(
            brokers[k].get("status") == "healthy" for k in ("kafka", "rabbitmq", "redis")
        )
        return UnifiedStatusSnapshot(
            autonomy_mode=self.guardrail_engine.settings.autonomy_mode,
            clouds_connected=list(brokers.get("clouds", {}).keys()),
            vms_and_environments_active=len(active_envs),
            k8s_launches_count=len(self._platform.k8s_launches),
            docker_containers_running=len(running_ctrs),
            tri_broker_healthy=brokers_ok,
            bill_forecast_eom_usd=bill.forecasted_eom_usd,
            bill_target_cap_usd=self.directives.target_monthly_cap_usd,
            identifiable_monthly_savings_usd=bill.total_identifiable_monthly_savings_usd,
            guardrail_blocks_count=self._guardrail_blocks,
            environments=[e.model_dump(mode="json") for e in active_envs],
            docker_containers=[c.model_dump(mode="json") for c in containers],
            k8s_workloads=[k.model_dump(mode="json") for k in self._platform.k8s_launches[:15]],
            brokers=brokers,
            recent_bot_feed=self.action_feed[:20],
        )

    async def launch_vm_guardrailed(
        self, req: VmProvisionRequest
    ) -> tuple[GuardrailDecision, VmProvisionResult | None]:
        sku = self._platform.vm_selector.get_sku(req.cloud, req.sku)
        active_vms = sum(
            1
            for e in self._platform.environments.values()
            if e.status != EnvironmentStatus.DESTROYED
        )
        bill = self.read_live_bill()
        decision = self.guardrail_engine.evaluate_vm_launch(
            req=req,
            sku=sku,
            current_active_vms=active_vms,
            current_projected_monthly_usd=bill.forecasted_eom_usd,
        )
        if not decision.allowed:
            self._guardrail_blocks += 1
            await self._record_action(
                action_type="bot.launch_vm",
                summary=f"DENIED VM {req.cloud.value.upper()} {req.sku}: {decision.violations[0]}",
                status="blocked_by_guardrail",
                guardrail_allowed=False,
                details={"violations": decision.violations},
            )
            raise PolicyViolationError(
                f"MCP Bot Guardrail denied VM launch ({req.sku})", violations=decision.violations
            )

        effective_req = req.model_copy(
            update={
                "use_spot": bool(decision.enforced_overrides.get("use_spot", req.use_spot)),
                "ttl_hours": int(decision.enforced_overrides.get("ttl_hours", req.ttl_hours)),
            }
        )
        result = await self._platform.vm_selector.provision_ephemeral_vm(effective_req)
        await self._record_action(
            action_type="bot.launch_vm",
            summary=f"Launched {req.cloud.value.upper()} VM {sku.sku} ({result.environment.id}) · ${result.estimated_monthly_usd}/mo",
            status="executed",
            estimated_monthly_delta_usd=result.estimated_monthly_usd,
            details={"overrides": decision.enforced_overrides, "warnings": decision.warnings},
        )
        return decision, result

    async def launch_docker_guardrailed(
        self, req: DockerLaunchRequest
    ) -> tuple[GuardrailDecision, DockerContainerStatus | None]:
        running = sum(1 for c in self.docker.list_containers() if c.state == "running")
        decision = self.guardrail_engine.evaluate_docker_launch(req, running)
        if not decision.allowed:
            self._guardrail_blocks += 1
            await self._record_action(
                action_type="bot.launch_docker",
                summary=f"DENIED Docker '{req.name}' ({req.image}): {decision.violations[0]}",
                status="blocked_by_guardrail",
                guardrail_allowed=False,
                details={"violations": decision.violations},
            )
            raise PolicyViolationError(
                f"MCP Bot Guardrail denied Docker launch '{req.name}'", violations=decision.violations
            )

        status = await self.docker.launch_container(req)
        await self._record_action(
            action_type="bot.launch_docker",
            summary=f"Launched hardened Docker container '{status.name}' ({status.image}, non-root, RO-fs)",
            status="executed",
            estimated_monthly_delta_usd=round(status.hourly_cost_usd * 730.0, 2),
            details={"container_id": status.container_id},
        )
        return decision, status

    async def launch_k8s_guardrailed(
        self, req: K8sLaunchRequest
    ) -> tuple[GuardrailDecision, K8sLaunchResult | None]:
        decision = self.guardrail_engine.evaluate_k8s_launch(req)
        if not decision.allowed:
            self._guardrail_blocks += 1
            await self._record_action(
                action_type="bot.launch_k8s",
                summary=f"DENIED K8s '{req.workload_name}' on {req.cloud.value.upper()}: {decision.violations[0]}",
                status="blocked_by_guardrail",
                guardrail_allowed=False,
                details={"violations": decision.violations},
            )
            raise PolicyViolationError(
                f"MCP Bot Guardrail denied Kubernetes launch '{req.workload_name}'",
                violations=decision.violations,
            )

        res = await self._platform.launch_kubernetes_workload(req)
        await self._record_action(
            action_type="bot.launch_k8s",
            summary=f"Launched K8s {req.mode} '{req.workload_name}' on {req.cloud.value.upper()} ({res.status})",
            status="executed" if res.opa_gate.allowed else "blocked_by_guardrail",
            guardrail_allowed=res.opa_gate.allowed,
            details={"launch_id": res.launch_id},
        )
        return decision, res

    async def run_self_prompt_bill_saving_cycle(
        self, custom_user_prompt: str | None = None
    ) -> SelfPromptCycleResult:
        """Auto-Bot reads live bill, injects user cost/infra/traffic prompt, validates guardrails & optimizes."""
        safety = self.guardrail_engine.scan_prompt_safety(
            f"{self.directives.custom_billing_directive}\n{self.directives.custom_traffic_directive}\n{custom_user_prompt or ''}"
        )
        bill = self.read_live_bill()
        prompts = self.prompt_composer.compose(
            guardrails=self.guardrail_engine.settings,
            directives=self.directives,
            bill=bill,
            custom_user_prompt=custom_user_prompt,
        )

        if not safety.allowed:
            self._guardrail_blocks += 1
            rec = await self._record_action(
                action_type="bot.self_prompt_bill_save",
                summary=f"BLOCKED adversarial prompt injection: {safety.violations[0]}",
                status="injection_blocked",
                guardrail_allowed=False,
                details={"violations": safety.violations},
            )
            evt = await self._platform.kafka.publish(
                "aegis.security.findings",
                CloudEvent(
                    type="io.aegisops.bot.prompt_injection.blocked",
                    subject="bot/guardrail-firewall",
                    data={"violations": safety.violations},
                ),
            )
            return SelfPromptCycleResult(
                autonomy_mode=self.guardrail_engine.settings.autonomy_mode,
                injected_self_prompt=prompts.billing_self_prompt,
                guardrail_check=safety,
                bill_before_eom_usd=bill.forecasted_eom_usd,
                potential_monthly_savings_usd=bill.total_identifiable_monthly_savings_usd,
                applied_monthly_savings_usd=0.0,
                actions=[rec],
                audit_event_id=evt.id,
            )

        mode = self.guardrail_engine.settings.autonomy_mode
        actions: list[AutoBotActionRecord] = []
        applied_savings = 0.0

        for opp in bill.saving_opportunities:
            if mode == BotAutonomyMode.BOUNDED_AUTONOMOUS and opp.auto_executable and opp.risk_level == "LOW":
                # Safely apply bounded non-prod cost savings (Spot repricing / TTL clamp)
                target_env = self._platform.environments.get(opp.target_resource)
                if target_env is not None and target_env.tier.value == "ephemeral":
                    if opp.category == "spot-migration":
                        target_env.tags["aegis:spot"] = "true"
                        target_env.hourly_cost_usd = round(target_env.hourly_cost_usd * 0.38, 2)
                    elif opp.category == "ttl-reap":
                        target_env.ttl_hours = self.directives.auto_reap_idle_hours
                applied_savings += opp.estimated_monthly_savings_usd
                actions.append(
                    await self._record_action(
                        action_type=f"bot.auto_save.{opp.category}",
                        summary=f"[AUTO-APPLIED] {opp.title} (saved ~${opp.estimated_monthly_savings_usd:,.2f}/mo)",
                        status="executed",
                        estimated_monthly_delta_usd=-opp.estimated_monthly_savings_usd,
                        details={"directive": opp.injected_directive_source, "command": opp.recommended_command},
                    )
                )
            else:
                actions.append(
                    await self._record_action(
                        action_type=f"bot.advisory.{opp.category}",
                        summary=f"[AUTO-BOT ADVISORY] {opp.title} (save ~${opp.estimated_monthly_savings_usd:,.2f}/mo)",
                        status="recommended",
                        estimated_monthly_delta_usd=-opp.estimated_monthly_savings_usd,
                        details={"directive": opp.injected_directive_source, "command": opp.recommended_command},
                    )
                )

        evt = await self._platform.kafka.publish(
            "aegis.audit.events",
            CloudEvent(
                type="io.aegisops.bot.self_prompt.executed",
                subject="bot/bill-optimizer",
                data={
                    "autonomy_mode": mode.value,
                    "bill_eom_usd": bill.forecasted_eom_usd,
                    "potential_savings_usd": bill.total_identifiable_monthly_savings_usd,
                    "applied_savings_usd": round(applied_savings, 2),
                },
            ),
        )

        return SelfPromptCycleResult(
            autonomy_mode=mode,
            injected_self_prompt=prompts.billing_self_prompt,
            guardrail_check=safety,
            bill_before_eom_usd=bill.forecasted_eom_usd,
            potential_monthly_savings_usd=bill.total_identifiable_monthly_savings_usd,
            applied_monthly_savings_usd=round(applied_savings, 2),
            actions=actions,
            audit_event_id=evt.id,
        )

    async def execute_natural_prompt(self, prompt_text: str) -> dict[str, Any]:
        """Interprets natural-language MCP Bot commands behind the Prompt-Injection Firewall & Guardrails."""
        safety = self.guardrail_engine.scan_prompt_safety(prompt_text)
        if not safety.allowed:
            self._guardrail_blocks += 1
            await self._record_action(
                action_type="bot.prompt",
                summary=f"BLOCKED unsafe prompt: {safety.violations[0]}",
                status="injection_blocked",
                guardrail_allowed=False,
                details={"violations": safety.violations},
            )
            raise PolicyViolationError("Prompt blocked by MCP Bot Guardrail Firewall", violations=safety.violations)

        low = prompt_text.lower()
        if "bill" in low or "cost" in low or "save" in low:
            cycle = await self.run_self_prompt_bill_saving_cycle(custom_user_prompt=prompt_text)
            return {"intent": "bill_saving_self_prompt", "result": cycle.model_dump(mode="json")}

        if "docker" in low or "container" in low:
            img_match = re.search(r"([a-z0-9./_-]+:[a-z0-9._-]+)", low)
            image = img_match.group(1) if img_match else self.directives.favorite_docker_base
            dec, ctr = await self.launch_docker_guardrailed(
                DockerLaunchRequest(name="bot-svc-container", image=image)
            )
            return {
                "intent": "launch_docker",
                "guardrail": dec.model_dump(mode="json"),
                "container": ctr.model_dump(mode="json") if ctr else None,
            }

        if "kube" in low or "k8s" in low:
            cloud = self.directives.preferred_cloud_order[0]
            dec, k8s_res = await self.launch_k8s_guardrailed(
                K8sLaunchRequest(
                    project_id="edge-gateway",
                    environment_id="env-staging-edge",
                    cloud=cloud,
                    workload_name="bot-k8s-workload",
                    image="ghcr.io/aegisops/edge-gateway:1.4.2",
                )
            )
            return {
                "intent": "launch_k8s",
                "guardrail": dec.model_dump(mode="json"),
                "k8s": k8s_res.model_dump(mode="json") if k8s_res else None,
            }

        if "vm" in low or "launch" in low:
            cloud = (
                CloudProvider.AWS
                if "aws" in low
                else CloudProvider.GCP
                if "gcp" in low
                else CloudProvider.AZURE
                if "azure" in low
                else self.directives.preferred_cloud_order[0]
            )
            sku_map = {
                CloudProvider.AWS: "m7i.xlarge",
                CloudProvider.GCP: "n2d-standard-4",
                CloudProvider.AZURE: "Standard_DC4as_v5",
            }
            region = self.directives.favorite_regions.get(cloud.value, "us-central1")
            dec, vm_res = await self.launch_vm_guardrailed(
                VmProvisionRequest(
                    project_id="edge-gateway",
                    environment_name=f"bot-{cloud.value}-vm",
                    cloud=cloud,
                    sku=sku_map[cloud],
                    region=region,
                    use_spot=self.directives.prefer_spot_for_non_prod,
                    ttl_hours=self.directives.auto_reap_idle_hours,
                )
            )
            return {
                "intent": "launch_vm",
                "guardrail": dec.model_dump(mode="json"),
                "vm": vm_res.model_dump(mode="json") if vm_res else None,
            }

        status = await self.read_all_statuses()
        return {"intent": "read_all_statuses", "status": status.model_dump(mode="json")}

    async def _record_action(
        self,
        action_type: str,
        summary: str,
        status: str,
        estimated_monthly_delta_usd: float = 0.0,
        guardrail_allowed: bool = True,
        details: dict[str, Any] | None = None,
    ) -> AutoBotActionRecord:
        rec = AutoBotActionRecord(
            action_type=action_type,
            summary=summary,
            status=status,
            estimated_monthly_delta_usd=estimated_monthly_delta_usd,
            guardrail_allowed=guardrail_allowed,
            details=details or {},
        )
        self.action_feed.insert(0, rec)
        await self._platform.redis.publish_channel(
            "aegis:live",
            {
                "type": "bot.action",
                "action_type": action_type,
                "status": status,
                "summary": summary,
            },
        )
        return rec
