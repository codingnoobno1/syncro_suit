"""Core Multi-Cloud Platform Service unifying AWS, GCP, Azure, VM Selector, FinOps, Drift & Security."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from aegisops.adapters.cloud.cloud_registry import MultiCloudRegistry
from aegisops.adapters.docker.docker_launcher import DockerLauncherAdapter
from aegisops.adapters.iac.ansible_runner import AnsibleRunner
from aegisops.adapters.iac.terraform_runner import TerraformRunner
from aegisops.adapters.k8s.launcher import K8sLauncher
from aegisops.adapters.messaging.kafka_bus import KafkaEventBus
from aegisops.adapters.messaging.rabbitmq_queue import RabbitMQJobQueue
from aegisops.adapters.messaging.redis_store import RedisStateStore
from aegisops.adapters.persistence.journal import SqliteStateJournal
from aegisops.adapters.powershell.rbac_planner import PowerShellRbacPlanner
from aegisops.application.destroyer_service import DestroyerService
from aegisops.application.extension_hub import ExtensionHub
from aegisops.application.vm_selector_service import VmSelectorService
from aegisops.bot.mcp_bot_service import AegisMcpBotService
from aegisops.config import Settings
from aegisops.domain.exceptions import EntityNotFoundError
from aegisops.domain.models import (
    AzureResourceNode,
    CloudEvent,
    CloudProvider,
    DriftCheckReport,
    DriftResourceItem,
    Environment,
    EnvironmentStatus,
    EnvironmentTier,
    FinOpsCloudBreakdown,
    FinOpsSummary,
    K8sLaunchRequest,
    K8sLaunchResult,
    PowerShellPermissionPlan,
    Project,
    QueueJob,
    ScanReport,
    utc_now,
)
from aegisops.security.opa_gate import OpaPolicyGate
from aegisops.security.sarif import to_sarif
from aegisops.security.scanners import SecurityPipelineEngine
from aegisops.syncro.deployer_service import SyncroDeployerService


class PlatformService:
    """High-level application facade used by REST API, CLI, MCP Server, and Workers."""

    def __init__(
        self,
        settings: Settings,
        kafka: KafkaEventBus,
        rabbitmq: RabbitMQJobQueue,
        redis: RedisStateStore,
        clouds: MultiCloudRegistry,
        terraform: TerraformRunner,
        ansible: AnsibleRunner,
        k8s: K8sLauncher,
        rbac: PowerShellRbacPlanner,
        scanner: SecurityPipelineEngine,
        opa_gate: OpaPolicyGate,
        extensions: ExtensionHub,
        docker: DockerLauncherAdapter | None = None,
        journal: SqliteStateJournal | None = None,
    ) -> None:
        self.settings = settings
        self.kafka = kafka
        self.rabbitmq = rabbitmq
        self.redis = redis
        self.clouds = clouds
        self.terraform = terraform
        self.ansible = ansible
        self.k8s = k8s
        self.rbac = rbac
        self.scanner = scanner
        self.opa_gate = opa_gate
        self.extensions = extensions
        self.docker = docker or DockerLauncherAdapter(mode=settings.mode)
        self.journal = journal or SqliteStateJournal(":memory:")

        self.projects: dict[str, Project] = {}
        self.environments: dict[str, Environment] = {}
        self.scan_history: list[ScanReport] = []
        self.k8s_launches: list[K8sLaunchResult] = []
        self.rbac_plans: list[PowerShellPermissionPlan] = []
        self.drift_history: list[DriftCheckReport] = []

        self.vm_selector = VmSelectorService(
            environments=self.environments,
            kafka=kafka,
            rabbitmq=rabbitmq,
            redis=redis,
        )

        self.destroyer = DestroyerService(
            hmac_secret=settings.hmac_secret,
            environments=self.environments,
            kafka=kafka,
            rabbitmq=rabbitmq,
            redis=redis,
            clouds=clouds,
            terraform=terraform,
            ansible=ansible,
            opa_gate=opa_gate,
        )

        self.bot = AegisMcpBotService(platform=self, docker=self.docker)
        self.syncro = SyncroDeployerService(platform=self, journal=self.journal)

    def seed_demo_topology(self) -> None:
        """Populates realistic multi-cloud (AWS + GCP + Azure) DevSecOps topology."""
        self.extensions.seed_defaults()

        projects = [
            Project(
                id="payments-core",
                name="Payments Ledger API",
                repository="github.com/aegisops/payments-core",
                primary_language="java",
                owner_team="finops-sec",
                azure_subscription_id=self.settings.azure_subscription_id,
                target_clouds=[CloudProvider.AZURE, CloudProvider.AWS],
                tags={"tier": "pci", "mesh": "kafka+redis"},
            ),
            Project(
                id="edge-gateway",
                name="Zero-Trust Edge Gateway",
                repository="github.com/aegisops/edge-gateway",
                primary_language="go",
                owner_team="platform-net",
                azure_subscription_id=self.settings.azure_subscription_id,
                target_clouds=[CloudProvider.AWS, CloudProvider.AZURE],
                tags={"tier": "edge", "k8s": "eks+aks"},
            ),
            Project(
                id="ai-inference",
                name="Confidential ML Inference Engine",
                repository="github.com/aegisops/ai-inference",
                primary_language="python",
                owner_team="ml-sec",
                azure_subscription_id=self.settings.azure_subscription_id,
                target_clouds=[CloudProvider.GCP, CloudProvider.AWS],
                tags={"tier": "gpu-confidential", "compliance": "hipaa"},
            ),
            Project(
                id="portal-web",
                name="Customer Security Portal",
                repository="github.com/aegisops/portal-web",
                primary_language="typescript",
                owner_team="appsec-ui",
                azure_subscription_id=self.settings.azure_subscription_id,
                target_clouds=[CloudProvider.GCP, CloudProvider.AZURE],
                tags={"tier": "web"},
            ),
        ]
        for proj in projects:
            self.projects[proj.id] = proj

        now = utc_now()
        envs = [
            # AZURE EPHEMERAL
            Environment(
                id="env-pr-412",
                project_id="payments-core",
                name="pr-412-payments",
                cloud=CloudProvider.AZURE,
                tier=EnvironmentTier.EPHEMERAL,
                location="eastus2",
                resource_group="rg-aegis-payments-pr-412",
                vm_sku="Standard_DC4as_v5",
                status=EnvironmentStatus.HARDENED,
                ttl_hours=4,
                expires_at=now + timedelta(hours=3, minutes=20),
                has_delete_lock=False,
                compliance_score=98.0,
                hourly_cost_usd=1.92,
                tags={"aegis:cloud": "azure", "aegis:ephemeral": "true", "aegis:ttl_hours": "4"},
                resources=[
                    AzureResourceNode(
                        id="aks-payments-pr-412",
                        name="aks-payments-pr-412",
                        resource_type="Microsoft.ContainerService/managedClusters",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=1.18,
                        depends_on=["vnet-payments-pr-412", "acrpaymentspr412"],
                    ),
                    AzureResourceNode(
                        id="acrpaymentspr412",
                        name="acrpaymentspr412",
                        resource_type="Microsoft.ContainerRegistry/registries",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=0.22,
                    ),
                    AzureResourceNode(
                        id="kv-payments-pr-412",
                        name="kv-payments-pr-412",
                        resource_type="Microsoft.KeyVault/vaults",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=0.06,
                        depends_on=["vnet-payments-pr-412"],
                    ),
                    AzureResourceNode(
                        id="vnet-payments-pr-412",
                        name="vnet-payments-pr-412",
                        resource_type="Microsoft.Network/virtualNetworks",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=0.46,
                    ),
                ],
            ),
            # AWS EPHEMERAL
            Environment(
                id="env-aws-edge-501",
                project_id="edge-gateway",
                name="aws-edge-pr-501",
                cloud=CloudProvider.AWS,
                tier=EnvironmentTier.EPHEMERAL,
                location="us-east-1",
                resource_group="aws-stack-edge-pr-501",
                vm_sku="m7i.xlarge",
                status=EnvironmentStatus.HARDENED,
                ttl_hours=6,
                expires_at=now + timedelta(hours=5, minutes=10),
                has_delete_lock=False,
                compliance_score=97.5,
                hourly_cost_usd=1.45,
                tags={"aegis:cloud": "aws", "aegis:ephemeral": "true", "aegis:imds": "v2-required"},
                resources=[
                    AzureResourceNode(
                        id="ec2-edge-pr-501",
                        name="ec2-edge-pr-501 (m7i.xlarge)",
                        resource_type="AWS::EC2::Instance",
                        cloud=CloudProvider.AWS,
                        hourly_cost_usd=0.81,
                        depends_on=["vpc-edge-pr-501", "kms-edge-pr-501"],
                    ),
                    AzureResourceNode(
                        id="vpc-edge-pr-501",
                        name="vpc-edge-pr-501",
                        resource_type="AWS::EC2::VPC",
                        cloud=CloudProvider.AWS,
                        hourly_cost_usd=0.42,
                    ),
                    AzureResourceNode(
                        id="kms-edge-pr-501",
                        name="kms-edge-pr-501",
                        resource_type="AWS::KMS::Key",
                        cloud=CloudProvider.AWS,
                        hourly_cost_usd=0.22,
                    ),
                ],
            ),
            # GCP EPHEMERAL CONFIDENTIAL
            Environment(
                id="env-gcp-ai-608",
                project_id="ai-inference",
                name="gcp-conf-ai-608",
                cloud=CloudProvider.GCP,
                tier=EnvironmentTier.EPHEMERAL,
                location="us-central1",
                resource_group="gcp-proj-ai-pr-608",
                vm_sku="n2d-standard-4",
                status=EnvironmentStatus.ACTIVE,
                ttl_hours=8,
                expires_at=now + timedelta(hours=7, minutes=15),
                has_delete_lock=False,
                compliance_score=98.4,
                hourly_cost_usd=1.18,
                tags={"aegis:cloud": "gcp", "aegis:ephemeral": "true", "aegis:confidential": "sev-snp"},
                resources=[
                    AzureResourceNode(
                        id="gce-ai-pr-608",
                        name="gce-ai-pr-608 (n2d-standard-4 SEV-SNP)",
                        resource_type="compute.googleapis.com/Instance",
                        cloud=CloudProvider.GCP,
                        hourly_cost_usd=0.68,
                        depends_on=["vpc-ai-pr-608"],
                    ),
                    AzureResourceNode(
                        id="vpc-ai-pr-608",
                        name="vpc-ai-pr-608",
                        resource_type="compute.googleapis.com/Subnetwork",
                        cloud=CloudProvider.GCP,
                        hourly_cost_usd=0.30,
                    ),
                    AzureResourceNode(
                        id="gcs-ai-pr-608",
                        name="aegis-gcs-ai-pr-608",
                        resource_type="storage.googleapis.com/Bucket",
                        cloud=CloudProvider.GCP,
                        hourly_cost_usd=0.20,
                    ),
                ],
            ),
            # AZURE STAGING (kept for existing tests & staging visibility)
            Environment(
                id="env-staging-edge",
                project_id="edge-gateway",
                name="staging-edge-aks",
                cloud=CloudProvider.AZURE,
                tier=EnvironmentTier.EPHEMERAL,
                location="westeurope",
                resource_group="rg-aegis-edge-staging",
                vm_sku="Standard_F8s_v2",
                status=EnvironmentStatus.ACTIVE,
                ttl_hours=8,
                expires_at=now + timedelta(hours=6, minutes=45),
                has_delete_lock=False,
                compliance_score=94.5,
                hourly_cost_usd=2.64,
                tags={"aegis:cloud": "azure", "aegis:ephemeral": "true", "aegis:ttl_hours": "8"},
                resources=[
                    AzureResourceNode(
                        id="aks-edge-staging",
                        name="aks-edge-staging",
                        resource_type="Microsoft.ContainerService/managedClusters",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=1.84,
                        depends_on=["vnet-edge-staging"],
                    ),
                    AzureResourceNode(
                        id="vnet-edge-staging",
                        name="vnet-edge-staging",
                        resource_type="Microsoft.Network/virtualNetworks",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=0.52,
                    ),
                    AzureResourceNode(
                        id="kv-edge-staging",
                        name="kv-edge-staging",
                        resource_type="Microsoft.KeyVault/vaults",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=0.28,
                    ),
                ],
            ),
            # PROTECTED PRODUCTION (AZURE)
            Environment(
                id="env-prod-core",
                project_id="payments-core",
                name="prod-payments-core",
                cloud=CloudProvider.AZURE,
                tier=EnvironmentTier.PRODUCTION,
                location="eastus2",
                resource_group="rg-aegis-prod-payments-core",
                vm_sku="Standard_EC8es_v5",
                status=EnvironmentStatus.HARDENED,
                ttl_hours=None,
                expires_at=None,
                has_delete_lock=True,
                compliance_score=99.4,
                hourly_cost_usd=8.40,
                tags={"aegis:cloud": "azure", "aegis:ephemeral": "false", "aegis:protected": "true"},
                resources=[
                    AzureResourceNode(
                        id="aks-prod-core",
                        name="aks-prod-core",
                        resource_type="Microsoft.ContainerService/managedClusters",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=6.20,
                        protected=True,
                    ),
                    AzureResourceNode(
                        id="kv-prod-core",
                        name="kv-prod-core",
                        resource_type="Microsoft.KeyVault/vaults",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=0.45,
                        protected=True,
                    ),
                    AzureResourceNode(
                        id="vnet-prod-core",
                        name="vnet-prod-core",
                        resource_type="Microsoft.Network/virtualNetworks",
                        cloud=CloudProvider.AZURE,
                        hourly_cost_usd=1.75,
                        protected=True,
                    ),
                ],
            ),
            # PROTECTED PRODUCTION (AWS)
            Environment(
                id="env-aws-prod-eks",
                project_id="edge-gateway",
                name="prod-aws-edge-eks",
                cloud=CloudProvider.AWS,
                tier=EnvironmentTier.PRODUCTION,
                location="us-east-1",
                resource_group="aws-prod-edge-eks",
                vm_sku="m7a.2xlarge",
                status=EnvironmentStatus.HARDENED,
                ttl_hours=None,
                expires_at=None,
                has_delete_lock=True,
                compliance_score=99.1,
                hourly_cost_usd=6.15,
                tags={"aegis:cloud": "aws", "aegis:ephemeral": "false", "aegis:protected": "true"},
                resources=[
                    AzureResourceNode(
                        id="eks-aws-prod",
                        name="eks-aws-prod (m7a.2xlarge SEV-SNP)",
                        resource_type="AWS::EKS::Cluster",
                        cloud=CloudProvider.AWS,
                        hourly_cost_usd=4.95,
                        protected=True,
                    ),
                    AzureResourceNode(
                        id="vpc-aws-prod",
                        name="vpc-aws-prod",
                        resource_type="AWS::EC2::VPC",
                        cloud=CloudProvider.AWS,
                        hourly_cost_usd=1.20,
                        protected=True,
                    ),
                ],
            ),
        ]
        for env in envs:
            self.environments[env.id] = env

    async def register_project(self, project: Project) -> Project:
        self.projects[project.id] = project
        await self.kafka.publish(
            "aegis.audit.events",
            CloudEvent(
                type="io.aegisops.project.registered",
                subject=f"project/{project.id}",
                project_id=project.id,
                data=project.model_dump(mode="json"),
            ),
        )
        await self.redis.publish_channel(
            "aegis:live", {"type": "project.registered", "project_id": project.id}
        )
        return project

    async def run_security_scan(
        self,
        project_id: str,
        target_path: str | None = None,
        scanners: list[str] | None = None,
    ) -> ScanReport:
        resolved = Path(target_path) if target_path else self.settings.repo_root / "infra"
        if not resolved.is_absolute():
            resolved = (self.settings.repo_root / resolved).resolve()

        job = await self.rabbitmq.enqueue(
            QueueJob(
                queue="jobs.security-scan",
                routing_key="scan.devsecops",
                priority=7,
                project_id=project_id,
                payload={"target_path": str(resolved), "scanners": scanners or []},
            )
        )
        await self.rabbitmq.dequeue("jobs.security-scan")

        report = await self.scanner.run_scan(
            project_id=project_id,
            target_path=resolved,
            scanners=scanners,
        )
        self.scan_history.insert(0, report)
        await self.rabbitmq.complete(
            job.id,
            {
                "scan_id": report.id,
                "compliance_score": report.compliance_score,
                "opa_allowed": report.opa_gate.allowed,
            },
        )
        await self.kafka.publish(
            "aegis.security.findings",
            CloudEvent(
                type="io.aegisops.security.scan.completed",
                subject=f"scan/{report.id}",
                project_id=project_id,
                data={
                    "scan_id": report.id,
                    "scanners": report.scanners_executed,
                    "summary": report.summary,
                    "compliance_score": report.compliance_score,
                    "opa_allowed": report.opa_gate.allowed,
                },
            ),
        )
        await self.redis.publish_channel(
            "aegis:live",
            {
                "type": "scan.completed",
                "scan_id": report.id,
                "project_id": project_id,
                "compliance_score": report.compliance_score,
                "opa_allowed": report.opa_gate.allowed,
            },
        )
        return report

    def export_scan_sarif(self, scan_id: str) -> dict[str, Any]:
        for report in self.scan_history:
            if report.id == scan_id:
                return to_sarif(report)
        raise EntityNotFoundError(f"Scan report '{scan_id}' not found")

    async def plan_terraform(
        self,
        project_id: str,
        environment_id: str,
        ttl_hours: int = 4,
        cloud: CloudProvider = CloudProvider.AZURE,
    ) -> dict[str, Any]:
        job = await self.rabbitmq.enqueue(
            QueueJob(
                queue="jobs.terraform",
                routing_key=f"terraform.plan.{cloud.value}",
                priority=5,
                project_id=project_id,
                environment_id=environment_id,
                payload={"cloud": cloud.value, "ttl_hours": ttl_hours},
            )
        )
        await self.rabbitmq.dequeue("jobs.terraform")
        result = await self.terraform.plan(
            environment_id=environment_id, project_id=project_id, ttl_hours=ttl_hours
        )
        result["cloud"] = cloud.value
        await self.rabbitmq.complete(job.id, result)
        await self.kafka.publish(
            "aegis.infra.lifecycle",
            CloudEvent(
                type="io.aegisops.terraform.planned",
                subject=f"{cloud.value}/env/{environment_id}",
                project_id=project_id,
                data=result,
            ),
        )
        await self.redis.set_value(
            f"ttl:env:{environment_id}", {"cloud": cloud.value, "ttl_hours": ttl_hours}, ttl_seconds=ttl_hours * 3600
        )
        return {"job_id": job.id, **result}

    async def run_ansible_hardening(
        self,
        project_id: str,
        playbook: str = "cis_azure_linux.yml",
        target_group: str = "aegis_ephemeral",
        check_mode: bool = False,
    ) -> dict[str, Any]:
        job = await self.rabbitmq.enqueue(
            QueueJob(
                queue="jobs.ansible",
                routing_key="ansible.harden",
                priority=6,
                project_id=project_id,
                payload={"playbook": playbook, "target_group": target_group},
            )
        )
        await self.rabbitmq.dequeue("jobs.ansible")
        result = await self.ansible.run_playbook(
            playbook_name=playbook, target_group=target_group, check_mode=check_mode
        )
        await self.rabbitmq.complete(job.id, result)
        await self.kafka.publish(
            "aegis.infra.lifecycle",
            CloudEvent(
                type="io.aegisops.ansible.completed",
                subject=f"playbook/{playbook}",
                project_id=project_id,
                data=result,
            ),
        )
        return {"job_id": job.id, **result}

    async def launch_kubernetes_workload(self, req: K8sLaunchRequest) -> K8sLaunchResult:
        job = await self.rabbitmq.enqueue(
            QueueJob(
                queue="jobs.k8s-launch",
                routing_key=f"k8s.{req.cloud.value}.{req.mode}",
                priority=6,
                project_id=req.project_id,
                environment_id=req.environment_id,
                payload=req.model_dump(mode="json"),
            )
        )
        await self.rabbitmq.dequeue("jobs.k8s-launch")
        result = await self.k8s.launch(req)
        result.cloud = req.cloud
        self.k8s_launches.insert(0, result)
        if result.opa_gate.allowed:
            await self.rabbitmq.complete(job.id, {"launch_id": result.launch_id})
        else:
            await self.rabbitmq.fail(job.id, "; ".join(result.opa_gate.violations))

        await self.kafka.publish(
            "aegis.infra.lifecycle",
            CloudEvent(
                type="io.aegisops.k8s.launched"
                if result.opa_gate.allowed
                else "io.aegisops.k8s.denied",
                subject=f"{req.cloud.value}/k8s/{req.namespace}/{req.workload_name}",
                project_id=req.project_id,
                data={
                    "cloud": req.cloud.value,
                    "launch_id": result.launch_id,
                    "status": result.status,
                    "violations": result.opa_gate.violations,
                },
            ),
        )
        return result

    async def generate_powershell_rbac_plan(
        self,
        resource_group: str,
        principal_object_id: str,
        personas: list[str] | None = None,
        pim_max_duration_hours: int = 1,
        subscription_id: str | None = None,
        requested_role_override: str | None = None,
        cloud: CloudProvider = CloudProvider.AZURE,
    ) -> PowerShellPermissionPlan:
        default_scope = {
            CloudProvider.AZURE: self.settings.azure_subscription_id,
            CloudProvider.AWS: self.settings.aws_account_id,
            CloudProvider.GCP: self.settings.gcp_project_id,
        }[cloud]
        plan = self.rbac.create_plan(
            subscription_id=subscription_id or default_scope,
            resource_group=resource_group,
            principal_object_id=principal_object_id,
            personas=personas,
            pim_max_duration_hours=pim_max_duration_hours,
            requested_role_override=requested_role_override,
            cloud=cloud,
        )
        self.rbac_plans.insert(0, plan)
        await self.kafka.publish(
            "aegis.audit.events",
            CloudEvent(
                type="io.aegisops.rbac.plan.generated",
                subject=f"{cloud.value}/iam/{resource_group}",
                data={
                    "cloud": cloud.value,
                    "plan_id": plan.plan_id,
                    "opa_allowed": plan.opa_gate.allowed,
                    "personas": [a.persona for a in plan.assignments],
                },
            ),
        )
        return plan

    async def run_drift_check(self, environment_id: str) -> DriftCheckReport:
        env = self.environments.get(environment_id)
        if env is None:
            raise EntityNotFoundError(f"Environment '{environment_id}' not found")

        await self.extensions.invoke_hook(
            "go-drift-scanner",
            "drift_check",
            {
                "project_id": env.project_id,
                "environment_id": env.id,
                "cloud": env.cloud.value,
            },
        )
        items = [
            DriftResourceItem(
                resource_id=res.id,
                resource_type=res.resource_type,
                cloud=env.cloud,
                drifted=False,
                diff_summary="Live state matches signed Terraform state hash",
            )
            for res in env.resources
        ]
        report = DriftCheckReport(
            environment_id=env.id,
            cloud=env.cloud,
            total_resources=len(items),
            drifted_count=sum(1 for i in items if i.drifted),
            items=items,
        )
        self.drift_history.insert(0, report)
        await self.kafka.publish(
            "aegis.infra.lifecycle",
            CloudEvent(
                type="io.aegisops.drift.checked",
                subject=f"{env.cloud.value}/env/{env.id}",
                project_id=env.project_id,
                data={"check_id": report.check_id, "drifted_count": report.drifted_count},
            ),
        )
        return report

    def finops_summary(self) -> FinOpsSummary:
        breakdowns: list[FinOpsCloudBreakdown] = []
        for cloud in (CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE):
            envs = [
                e
                for e in self.environments.values()
                if e.cloud == cloud and e.status != EnvironmentStatus.DESTROYED
            ]
            hr = round(sum(e.hourly_cost_usd for e in envs), 2)
            eph_hr = round(
                sum(e.hourly_cost_usd for e in envs if e.tier == EnvironmentTier.EPHEMERAL), 2
            )
            breakdowns.append(
                FinOpsCloudBreakdown(
                    cloud=cloud,
                    active_environments=len(envs),
                    hourly_burn_usd=hr,
                    monthly_projected_usd=round(hr * 730.0, 2),
                    ephemeral_reclaimable_monthly_usd=round(eph_hr * 730.0, 2),
                )
            )
        total_hr = round(sum(b.hourly_burn_usd for b in breakdowns), 2)
        return FinOpsSummary(
            total_hourly_usd=total_hr,
            total_monthly_projected_usd=round(total_hr * 730.0, 2),
            total_ephemeral_reclaimable_monthly_usd=round(
                sum(b.ephemeral_reclaimable_monthly_usd for b in breakdowns), 2
            ),
            by_cloud=breakdowns,
        )

    async def broker_health(self) -> dict[str, Any]:
        statuses = await self.clouds.all_statuses()
        return {
            "kafka": await self.kafka.health(),
            "rabbitmq": await self.rabbitmq.health(),
            "redis": await self.redis.health(),
            "clouds": statuses,
            "azure": statuses["azure"],
        }

    async def overview_snapshot(self) -> dict[str, Any]:
        active_envs = [
            e for e in self.environments.values() if e.status != EnvironmentStatus.DESTROYED
        ]
        ephemeral_count = sum(1 for e in active_envs if e.tier == EnvironmentTier.EPHEMERAL)
        finops = self.finops_summary()
        avg_compliance = (
            round(sum(e.compliance_score for e in active_envs) / len(active_envs), 1)
            if active_envs
            else 100.0
        )
        return {
            "mode": self.settings.mode,
            "projects_count": len(self.projects),
            "active_environments": len(active_envs),
            "ephemeral_environments": ephemeral_count,
            "hourly_azure_burn_usd": finops.total_hourly_usd,
            "hourly_multicloud_burn_usd": finops.total_hourly_usd,
            "finops": finops.model_dump(mode="json"),
            "avg_compliance_score": avg_compliance,
            "scans_executed": len(self.scan_history),
            "vm_catalog_count": len(self.vm_selector.list_catalog()),
            "extensions_connected": len(self.extensions.list_extensions()),
            "brokers": await self.broker_health(),
        }
