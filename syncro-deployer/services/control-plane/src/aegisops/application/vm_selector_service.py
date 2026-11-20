"""Intelligent Multi-Cloud VM Selector, Cross-Cloud Comparator, HCL Generator & Provisioner."""

from __future__ import annotations

from datetime import timedelta

from aegisops.adapters.cloud.vm_catalog import VM_CATALOG
from aegisops.adapters.messaging.kafka_bus import KafkaEventBus
from aegisops.adapters.messaging.rabbitmq_queue import RabbitMQJobQueue
from aegisops.adapters.messaging.redis_store import RedisStateStore
from aegisops.domain.exceptions import EntityNotFoundError
from aegisops.domain.models import (
    AzureResourceNode,
    CloudEvent,
    CloudProvider,
    Environment,
    EnvironmentStatus,
    EnvironmentTier,
    QueueJob,
    VmComparisonMatrix,
    VmProvisionRequest,
    VmProvisionResult,
    VmRecommendation,
    VmSelectionCriteria,
    VmSku,
    new_id,
    utc_now,
)


class VmSelectorService:
    """Scores, compares, renders CIS-hardened Terraform, and provisions VMs across AWS, GCP, Azure."""

    def __init__(
        self,
        environments: dict[str, Environment],
        kafka: KafkaEventBus,
        rabbitmq: RabbitMQJobQueue,
        redis: RedisStateStore,
    ) -> None:
        self._environments = environments
        self._kafka = kafka
        self._rabbitmq = rabbitmq
        self._redis = redis
        self._catalog_by_sku: dict[tuple[CloudProvider, str], VmSku] = {
            (item.cloud, item.sku.lower()): item for item in VM_CATALOG
        }

    def list_catalog(self, cloud: CloudProvider | None = None) -> list[VmSku]:
        if cloud is None:
            return list(VM_CATALOG)
        return [item for item in VM_CATALOG if item.cloud == cloud]

    def get_sku(self, cloud: CloudProvider, sku_name: str) -> VmSku:
        found = self._catalog_by_sku.get((cloud, sku_name.lower()))
        if found is None:
            raise EntityNotFoundError(f"VM SKU '{sku_name}' not found in {cloud.value.upper()} catalog")
        return found

    def _compute_security_score(self, sku: VmSku) -> float:
        score = 70.0
        if sku.security.confidential_compute:
            score += 18.0
        if sku.security.secure_boot and sku.security.vtpm:
            score += 6.0
        if sku.security.imdsv2_or_oslogin and sku.security.encryption_at_host:
            score += 4.0
        if "FedRAMP-High" in sku.compliance_badges:
            score += 2.0
        return round(min(100.0, score), 1)

    def render_terraform_hcl(
        self,
        sku: VmSku,
        region: str,
        project_id: str = "edge-gateway",
        env_id: str = "ephemeral-01",
        use_spot: bool = False,
        ttl_hours: int = 4,
    ) -> str:
        prefix = f"{project_id}-{env_id}"
        if sku.cloud == CloudProvider.AWS:
            market_block = (
                '  instance_market_options { market_type = "spot" }\n' if use_spot else ""
            )
            return (
                f'# AWS EC2 Hardened Compute ({sku.sku} · {sku.architecture.value})\n'
                f'resource "aws_instance" "{env_id.replace("-", "_")}" {{\n'
                f'  ami                         = "{sku.security.cis_hardened_image}"\n'
                f'  instance_type               = "{sku.sku}"\n'
                f'  associate_public_ip_address = false\n'
                f'  ebs_optimized               = true\n'
                f'{market_block}'
                f'  metadata_options {{\n'
                f'    http_endpoint = "enabled"\n'
                f'    http_tokens   = "required" # IMDSv2 Enforced\n'
                f'  }}\n'
                f'  enclave_options {{ enabled = {str(sku.security.confidential_compute).lower()} }}\n'
                f'  root_block_device {{ encrypted = true; volume_type = "gp3"; volume_size = 50 }}\n'
                f'  tags = {{ "aegis:ephemeral" = "true", "aegis:ttl_hours" = "{ttl_hours}", "aegis:region" = "{region}", Name = "ec2-{prefix}" }}\n'
                f'}}'
            )

        if sku.cloud == CloudProvider.GCP:
            prov_model = "SPOT" if use_spot else "STANDARD"
            maint = "TERMINATE" if (sku.security.confidential_compute or use_spot) else "MIGRATE"
            return (
                f'# GCP Shielded/Confidential GCE ({sku.sku} · {sku.architecture.value})\n'
                f'resource "google_compute_instance" "{env_id.replace("-", "_")}" {{\n'
                f'  name         = "gce-{prefix}"\n'
                f'  machine_type = "{sku.sku}"\n'
                f'  zone         = "{region}-a"\n'
                f'  boot_disk {{ initialize_params {{ image = "{sku.security.cis_hardened_image}"; size = 50 }} }}\n'
                f'  network_interface {{ subnetwork = "snet-{prefix}-priv" }}\n'
                f'  shielded_instance_config {{\n'
                f'    enable_secure_boot = true; enable_vtpm = true; enable_integrity_monitoring = true\n'
                f'  }}\n'
                f'  confidential_instance_config {{ enable_confidential_compute = {str(sku.security.confidential_compute).lower()} }}\n'
                f'  scheduling {{ provisioning_model = "{prov_model}"; on_host_maintenance = "{maint}" }}\n'
                f'  labels = {{ aegis_ephemeral = "true", aegis_ttl_hours = "{ttl_hours}" }}\n'
                f'}}'
            )

        priority_line = '  priority = "Spot"\n  eviction_policy = "Delete"\n' if use_spot else ""
        return (
            f'# Azure Trusted Launch / Confidential VM ({sku.sku} · {sku.architecture.value})\n'
            f'resource "azurerm_linux_virtual_machine" "{env_id.replace("-", "_")}" {{\n'
            f'  name                            = "vm-{prefix}"\n'
            f'  location                        = "{region}"\n'
            f'  size                            = "{sku.sku}"\n'
            f'  disable_password_authentication = true\n'
            f'  secure_boot_enabled             = true\n'
            f'  vtpm_enabled                    = true\n'
            f'  encryption_at_host_enabled      = true\n'
            f'{priority_line}'
            f'  identity {{ type = "SystemAssigned" }}\n'
            f'  tags = {{ "aegis:ephemeral" = "true", "aegis:ttl_hours" = "{ttl_hours}", "aegis:vm_sku" = "{sku.sku}" }}\n'
            f'}}'
        )

    def recommend(self, criteria: VmSelectionCriteria) -> list[VmRecommendation]:
        candidates: list[VmSku] = []
        for sku in VM_CATALOG:
            if sku.cloud not in criteria.clouds:
                continue
            if criteria.workload_profile and sku.profile != criteria.workload_profile:
                continue
            if criteria.architecture and sku.architecture != criteria.architecture:
                continue
            if sku.vcpu < criteria.min_vcpu or sku.memory_gib < criteria.min_memory_gib:
                continue
            if criteria.require_confidential_compute and not sku.security.confidential_compute:
                continue
            if criteria.require_gpu and sku.gpu_count == 0:
                continue
            if criteria.region and criteria.region not in sku.regions:
                continue
            if criteria.compliance_framework and criteria.compliance_framework.upper() not in {
                b.upper() for b in sku.compliance_badges
            }:
                continue
            effective_hr = sku.hourly_spot_usd if criteria.prefer_spot else sku.hourly_on_demand_usd
            if criteria.max_hourly_budget_usd is not None and effective_hr > criteria.max_hourly_budget_usd:
                continue
            candidates.append(sku)

        if not candidates:
            return []

        prices = [
            c.hourly_spot_usd if criteria.prefer_spot else c.hourly_on_demand_usd
            for c in candidates
        ]
        min_p, max_p = min(prices), max(prices)

        recs: list[VmRecommendation] = []
        for sku in candidates:
            eff_hr = sku.hourly_spot_usd if criteria.prefer_spot else sku.hourly_on_demand_usd
            eff_mo = round(eff_hr * 730.0, 2)
            spot_pct = round((1.0 - (sku.hourly_spot_usd / sku.hourly_on_demand_usd)) * 100.0, 1)
            sec_score = self._compute_security_score(sku)

            # Right-sizing score penalizes excessive over-provisioning vs requested vCPU/RAM
            vcpu_ratio = sku.vcpu / max(1, criteria.min_vcpu)
            ram_ratio = sku.memory_gib / max(1.0, criteria.min_memory_gib)
            right_size_score = max(35.0, 100.0 - (vcpu_ratio - 1.0) * 14.0 - (ram_ratio - 1.0) * 8.0)

            price_norm = 100.0 if max_p == min_p else 100.0 - ((eff_hr - min_p) / (max_p - min_p)) * 45.0
            fit_score = round(
                min(100.0, 0.42 * price_norm + 0.33 * sec_score + 0.25 * right_size_score),
                1,
            )

            rationale = [
                f"{sku.vcpu} vCPU / {int(sku.memory_gib)} GiB RAM ({sku.architecture.value}, {sku.network_gbps} Gbps)",
                f"Est. ${eff_hr:.4f}/hr (${eff_mo:.2f}/mo){' [SPOT]' if criteria.prefer_spot else ' [On-Demand]'} · {spot_pct}% spot discount",
            ]
            if sku.security.confidential_compute and sku.security.confidential_tech:
                rationale.append(f"Hardware Confidential Compute: {sku.security.confidential_tech}")
            if sku.gpu_model:
                rationale.append(f"GPU Accelerator: {sku.gpu_count}x {sku.gpu_model}")

            region = criteria.region if (criteria.region and criteria.region in sku.regions) else sku.regions[0]
            hcl = self.render_terraform_hcl(
                sku=sku,
                region=region,
                use_spot=criteria.prefer_spot,
            )
            recs.append(
                VmRecommendation(
                    sku=sku,
                    fit_score=fit_score,
                    security_score=sec_score,
                    effective_hourly_usd=round(eff_hr, 4),
                    effective_monthly_usd=eff_mo,
                    spot_savings_pct=spot_pct,
                    rationale=rationale,
                    terraform_snippet=hcl,
                )
            )

        recs.sort(key=lambda r: (-r.fit_score, r.effective_hourly_usd))
        if recs:
            recs[0].recommended = True
        return recs

    def compare_clouds(self, criteria: VmSelectionCriteria) -> VmComparisonMatrix:
        ranked = self.recommend(criteria)
        best_by_cloud: dict[str, VmRecommendation | None] = {
            CloudProvider.AWS.value: None,
            CloudProvider.GCP.value: None,
            CloudProvider.AZURE.value: None,
        }
        for rec in ranked:
            key = rec.sku.cloud.value
            if best_by_cloud[key] is None:
                best_by_cloud[key] = rec

        present = [r for r in best_by_cloud.values() if r is not None]
        cheapest_cloud = None
        highest_sec_cloud = None
        max_savings = 0.0
        if present:
            cheapest = min(present, key=lambda r: r.effective_monthly_usd)
            priciest = max(present, key=lambda r: r.effective_monthly_usd)
            best_sec = max(present, key=lambda r: (r.security_score, -r.effective_monthly_usd))
            cheapest_cloud = cheapest.sku.cloud.value
            highest_sec_cloud = best_sec.sku.cloud.value
            max_savings = round(priciest.effective_monthly_usd - cheapest.effective_monthly_usd, 2)

        return VmComparisonMatrix(
            criteria=criteria,
            best_by_cloud=best_by_cloud,
            cheapest_cloud=cheapest_cloud,
            highest_security_cloud=highest_sec_cloud,
            max_monthly_savings_vs_priciest_usd=max_savings,
            ranked_matches=ranked,
        )

    async def provision_ephemeral_vm(self, req: VmProvisionRequest) -> VmProvisionResult:
        sku = self.get_sku(req.cloud, req.sku)
        region = req.region if req.region in sku.regions else sku.regions[0]
        eff_hr = sku.hourly_spot_usd if req.use_spot else sku.hourly_on_demand_usd
        disk_hr = round(req.disk_gb * 0.00018, 4)
        net_hr = 0.05
        total_hr = round(eff_hr + disk_hr + net_hr, 4)
        env_id = new_id(f"env-{req.cloud.value}")
        scope_prefix = {
            CloudProvider.AWS: "aws-stack",
            CloudProvider.GCP: "gcp-proj",
            CloudProvider.AZURE: "rg-aegis",
        }[req.cloud]
        scope_name = f"{scope_prefix}-{req.project_id}-{req.environment_name}"

        compute_type = {
            CloudProvider.AWS: "AWS::EC2::Instance",
            CloudProvider.GCP: "compute.googleapis.com/Instance",
            CloudProvider.AZURE: "Microsoft.Compute/virtualMachines",
        }[req.cloud]
        net_type = {
            CloudProvider.AWS: "AWS::EC2::VPC",
            CloudProvider.GCP: "compute.googleapis.com/Subnetwork",
            CloudProvider.AZURE: "Microsoft.Network/virtualNetworks",
        }[req.cloud]
        kms_type = {
            CloudProvider.AWS: "AWS::KMS::Key",
            CloudProvider.GCP: "cloudkms.googleapis.com/CryptoKey",
            CloudProvider.AZURE: "Microsoft.KeyVault/vaults",
        }[req.cloud]

        now = utc_now()
        env = Environment(
            id=env_id,
            project_id=req.project_id,
            name=req.environment_name,
            cloud=req.cloud,
            tier=EnvironmentTier.EPHEMERAL,
            location=region,
            resource_group=scope_name,
            vm_sku=sku.sku,
            status=EnvironmentStatus.HARDENED,
            ttl_hours=req.ttl_hours,
            expires_at=now + timedelta(hours=req.ttl_hours),
            has_delete_lock=False,
            compliance_score=self._compute_security_score(sku),
            hourly_cost_usd=round(total_hr, 2),
            tags={
                "aegis:cloud": req.cloud.value,
                "aegis:ephemeral": "true",
                "aegis:vm_sku": sku.sku,
                "aegis:spot": str(req.use_spot).lower(),
                "aegis:ttl_hours": str(req.ttl_hours),
            },
            resources=[
                AzureResourceNode(
                    id=f"vm-{req.environment_name}",
                    name=f"{req.environment_name} ({sku.sku})",
                    resource_type=compute_type,
                    cloud=req.cloud,
                    hourly_cost_usd=round(eff_hr, 3),
                    depends_on=[f"net-{req.environment_name}", f"kms-{req.environment_name}"],
                ),
                AzureResourceNode(
                    id=f"net-{req.environment_name}",
                    name=f"vpc-{req.environment_name}",
                    resource_type=net_type,
                    cloud=req.cloud,
                    hourly_cost_usd=net_hr,
                ),
                AzureResourceNode(
                    id=f"kms-{req.environment_name}",
                    name=f"kms-{req.environment_name}",
                    resource_type=kms_type,
                    cloud=req.cloud,
                    hourly_cost_usd=round(disk_hr, 3),
                ),
            ],
        )
        self._environments[env.id] = env

        hcl = self.render_terraform_hcl(
            sku=sku,
            region=region,
            project_id=req.project_id,
            env_id=req.environment_name,
            use_spot=req.use_spot,
            ttl_hours=req.ttl_hours,
        )

        job = await self._rabbitmq.enqueue(
            QueueJob(
                queue="jobs.terraform",
                routing_key=f"terraform.provision.{req.cloud.value}",
                priority=6,
                project_id=req.project_id,
                environment_id=env.id,
                payload={"cloud": req.cloud.value, "sku": sku.sku, "region": region, "spot": req.use_spot},
            )
        )
        await self._rabbitmq.dequeue("jobs.terraform")
        await self._rabbitmq.complete(job.id, {"environment_id": env.id, "vm_sku": sku.sku})

        await self._redis.set_value(
            f"ttl:env:{env.id}",
            {"cloud": req.cloud.value, "sku": sku.sku, "ttl_hours": req.ttl_hours},
            ttl_seconds=req.ttl_hours * 3600,
        )

        evt = await self._kafka.publish(
            "aegis.infra.lifecycle",
            CloudEvent(
                type="io.aegisops.vm.provisioned",
                subject=f"{req.cloud.value}/env/{env.id}",
                project_id=req.project_id,
                data={
                    "environment_id": env.id,
                    "cloud": req.cloud.value,
                    "sku": sku.sku,
                    "region": region,
                    "spot": req.use_spot,
                    "confidential_compute": sku.security.confidential_compute,
                    "hourly_cost_usd": total_hr,
                },
            ),
        )
        await self._redis.publish_channel(
            "aegis:live",
            {
                "type": "vm.provisioned",
                "environment_id": env.id,
                "cloud": req.cloud.value,
                "sku": sku.sku,
            },
        )

        inv_group = {
            CloudProvider.AWS: "aws_ephemeral",
            CloudProvider.GCP: "gcp_compute",
            CloudProvider.AZURE: "aegis_ephemeral",
        }[req.cloud]
        abac_tag = {
            CloudProvider.AWS: "aws:ResourceTag/aegis:ephemeral == 'true'",
            CloudProvider.GCP: "resource.matchTag('aegis_ephemeral', 'true')",
            CloudProvider.AZURE: "@Resource[...:tags] StringContains 'aegis:ephemeral=true'",
        }[req.cloud]

        return VmProvisionResult(
            environment=env,
            selected_sku=sku,
            terraform_hcl=hcl,
            ansible_inventory_group=inv_group,
            iam_abac_tag=abac_tag,
            job_id=job.id,
            audit_event_id=evt.id,
            estimated_monthly_usd=round(total_hr * 730.0, 2),
        )
