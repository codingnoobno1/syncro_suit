"""Live Multi-Cloud Billing Reader & FinOps Cost-Saving Detector (AWS · GCP · Azure)."""

from __future__ import annotations

from datetime import UTC, datetime

from aegisops.adapters.docker.docker_launcher import DockerContainerStatus
from aegisops.bot.models import (
    BillLineItem,
    BotGuardrailSettings,
    CloudBillSnapshot,
    CostSavingOpportunity,
    TrafficTechnique,
    UserPromptDirectives,
)
from aegisops.domain.models import (
    CloudProvider,
    Environment,
    EnvironmentStatus,
    EnvironmentTier,
)


class CloudBillingReader:
    """Computes live itemized AWS/GCP/Azure billing snapshots and detects savings aligned to user directives."""

    def read_bill(
        self,
        environments: dict[str, Environment],
        containers: list[DockerContainerStatus],
        guardrails: BotGuardrailSettings,
        directives: UserPromptDirectives,
    ) -> CloudBillSnapshot:
        now = datetime.now(UTC)
        day_of_month = max(1, now.day)
        hours_elapsed = day_of_month * 24.0
        period = now.strftime("%Y-%m")

        line_items: list[BillLineItem] = []
        spend_by_cloud: dict[str, float] = {"aws": 0.0, "gcp": 0.0, "azure": 0.0}
        opportunities: list[CostSavingOpportunity] = []

        total_hourly = 0.0
        egress_monthly = 0.0

        for env in environments.values():
            if env.status == EnvironmentStatus.DESTROYED:
                continue
            hr = env.hourly_cost_usd
            proj_mo = round(hr * 730.0, 2)
            mtd = round(hr * hours_elapsed, 2)
            total_hourly += hr
            spend_by_cloud[env.cloud.value] = round(spend_by_cloud[env.cloud.value] + proj_mo, 2)

            opt_tag: str | None = None
            is_spot = env.tags.get("aegis:spot") == "true"

            if env.tier == EnvironmentTier.EPHEMERAL and not is_spot and directives.prefer_spot_for_non_prod:
                opt_tag = "spot-candidate"
                spot_save = round(proj_mo * 0.62, 2)
                opportunities.append(
                    CostSavingOpportunity(
                        category="spot-migration",
                        cloud=env.cloud.value,
                        title=f"Shift ephemeral '{env.id}' ({env.vm_sku or 'K8s'}) from On-Demand to Spot/Preemptible",
                        target_resource=env.id,
                        estimated_monthly_savings_usd=spot_save,
                        risk_level="LOW",
                        auto_executable=True,
                        injected_directive_source="billing.prefer_spot_for_non_prod",
                        recommended_command=f"aegis vm provision --cloud {env.cloud.value} --sku {env.vm_sku or 'n2d-standard-4'} --spot --ttl-hours {directives.auto_reap_idle_hours}",
                    )
                )

            if env.tier == EnvironmentTier.EPHEMERAL and (env.ttl_hours or 0) > directives.auto_reap_idle_hours:
                opt_tag = opt_tag or "ttl-trim-candidate"
                ttl_save = round(proj_mo * 0.35, 2)
                opportunities.append(
                    CostSavingOpportunity(
                        category="ttl-reap",
                        cloud=env.cloud.value,
                        title=f"Tighten TTL lease on '{env.id}' ({env.ttl_hours}h -> {directives.auto_reap_idle_hours}h) or schedule off-hours teardown",
                        target_resource=env.id,
                        estimated_monthly_savings_usd=ttl_save,
                        risk_level="LOW",
                        auto_executable=True,
                        injected_directive_source="billing.auto_reap_idle_hours",
                        recommended_command=f"aegis destroy preview --env {env.id}",
                    )
                )

            # Estimate egress line per active environment
            env_egress_mo = round(proj_mo * 0.14, 2)
            egress_monthly += env_egress_mo

            line_items.append(
                BillLineItem(
                    cloud=env.cloud,
                    service=f"{env.cloud.value.upper()} Compute/K8s ({env.vm_sku or 'managed'})",
                    resource_id=env.id,
                    tier=env.tier.value,
                    mtd_cost_usd=mtd,
                    hourly_rate_usd=hr,
                    projected_monthly_usd=proj_mo,
                    optimization_tag=opt_tag,
                )
            )

        # Include running Docker host footprint
        running_ctrs = [c for c in containers if c.state == "running"]
        if running_ctrs:
            ctr_hr = round(sum(c.hourly_cost_usd for c in running_ctrs), 3)
            ctr_mo = round(ctr_hr * 730.0, 2)
            total_hourly += ctr_hr
            spend_by_cloud["azure"] = round(spend_by_cloud["azure"] + ctr_mo, 2)
            line_items.append(
                BillLineItem(
                    cloud=CloudProvider.AZURE,
                    service=f"Docker Runtime ({len(running_ctrs)} containers)",
                    resource_id="docker-host-pool",
                    tier="platform",
                    mtd_cost_usd=round(ctr_hr * hours_elapsed, 2),
                    hourly_rate_usd=ctr_hr,
                    projected_monthly_usd=ctr_mo,
                )
            )

        # Egress & Traffic-Technique driven savings
        egress_monthly = round(egress_monthly, 2)
        if egress_monthly > 100.0 and TrafficTechnique.EDGE_CDN_CACHE_WAF in directives.traffic_techniques:
            cdn_save = round(egress_monthly * 0.55, 2)
            opportunities.append(
                CostSavingOpportunity(
                    category="edge-egress-cache",
                    cloud="multi",
                    title="Enable Edge CDN Cache + WAF Compression to slash cross-cloud egress by ~55%",
                    target_resource="ingress-egress-mesh",
                    estimated_monthly_savings_usd=cdn_save,
                    risk_level="LOW",
                    auto_executable=True,
                    injected_directive_source="traffic.edge-cdn-cache-waf",
                    recommended_command="Apply Edge CDN Cache-Control + Brotli rules on AWS CloudFront / Cloud CDN / Front Door",
                )
            )

        if TrafficTechnique.KEDA_SCALE_TO_ZERO in directives.traffic_techniques:
            keda_save = round(
                sum(
                    e.hourly_cost_usd * 730.0 * 0.28
                    for e in environments.values()
                    if e.status != EnvironmentStatus.DESTROYED and e.tier == EnvironmentTier.EPHEMERAL
                ),
                2,
            )
            if keda_save > 0:
                opportunities.append(
                    CostSavingOpportunity(
                        category="keda-scale-zero",
                        cloud="multi",
                        title="Attach KEDA RabbitMQ/Kafka Scaler (scale-to-zero) on non-prod worker pods",
                        target_resource="aegisops-workers",
                        estimated_monthly_savings_usd=keda_save,
                        risk_level="LOW",
                        auto_executable=True,
                        injected_directive_source="traffic.keda-scale-to-zero",
                        recommended_command="aegis k8s launch --mode helm --name aegisops-workers",
                    )
                )

        if directives.prefer_arm64_stateless:
            opportunities.append(
                CostSavingOpportunity(
                    category="arm64-rightsize",
                    cloud="aws",
                    title="Migrate stateless x86_64 edge gateways to Graviton3 (c7g) / Tau (t2a) / Ampere (D2ps_v5) ARM64",
                    target_resource="edge-gateway",
                    estimated_monthly_savings_usd=218.4,
                    risk_level="MEDIUM",
                    auto_executable=False,
                    injected_directive_source="billing.prefer_arm64_stateless",
                    recommended_command="aegis vm compare --vcpu 4 --ram 16 --arch arm64 --spot",
                )
            )

        forecast_eom = round(total_hourly * 730.0 + egress_monthly, 2)
        mtd_total = round(sum(i.mtd_cost_usd for i in line_items) + (egress_monthly * (day_of_month / 30.0)), 2)
        daily_burn = round((total_hourly * 24.0) + (egress_monthly / 30.0), 2)
        util_pct = round((forecast_eom / max(1.0, guardrails.max_monthly_budget_usd)) * 100.0, 1)
        total_savings = round(sum(o.estimated_monthly_savings_usd for o in opportunities), 2)

        opportunities.sort(key=lambda o: -o.estimated_monthly_savings_usd)

        return CloudBillSnapshot(
            billing_period=period,
            mtd_spend_usd=mtd_total,
            daily_burn_usd=daily_burn,
            forecasted_eom_usd=forecast_eom,
            hard_budget_cap_usd=guardrails.max_monthly_budget_usd,
            user_target_cap_usd=directives.target_monthly_cap_usd,
            budget_utilization_pct=util_pct,
            over_user_target=forecast_eom > directives.target_monthly_cap_usd,
            spend_by_cloud=spend_by_cloud,
            egress_monthly_usd=egress_monthly,
            line_items=line_items,
            saving_opportunities=opportunities,
            total_identifiable_monthly_savings_usd=total_savings,
        )
