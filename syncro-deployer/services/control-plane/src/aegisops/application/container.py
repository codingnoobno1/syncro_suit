"""Dependency Injection Container wiring Multi-Cloud (AWS, GCP, Azure) and Tri-Broker adapters."""

from __future__ import annotations

from aegisops.adapters.azure.azure_cli import AzureCliAdapter
from aegisops.adapters.cloud.aws_provider import AwsCloudAdapter
from aegisops.adapters.cloud.azure_provider import AzureCloudAdapter
from aegisops.adapters.cloud.cloud_registry import MultiCloudRegistry
from aegisops.adapters.cloud.gcp_provider import GcpCloudAdapter
from aegisops.adapters.iac.ansible_runner import AnsibleRunner
from aegisops.adapters.iac.terraform_runner import TerraformRunner
from aegisops.adapters.k8s.launcher import K8sLauncher
from aegisops.adapters.messaging.kafka_bus import KafkaEventBus
from aegisops.adapters.messaging.rabbitmq_queue import RabbitMQJobQueue
from aegisops.adapters.messaging.redis_store import RedisStateStore
from aegisops.adapters.powershell.rbac_planner import PowerShellRbacPlanner
from aegisops.application.extension_hub import ExtensionHub
from aegisops.application.platform_service import PlatformService
from aegisops.config import Settings
from aegisops.domain.models import CloudProvider
from aegisops.security.opa_gate import OpaPolicyGate
from aegisops.security.scanners import SecurityPipelineEngine


def build_platform(settings: Settings | None = None, seed_demo: bool = True) -> PlatformService:
    cfg = settings or Settings()
    kafka = KafkaEventBus(cfg.kafka_bootstrap_servers, backend=cfg.broker_backend)
    rabbitmq = RabbitMQJobQueue(cfg.rabbitmq_url, backend=cfg.broker_backend)
    redis = RedisStateStore(cfg.redis_url, backend=cfg.broker_backend)

    azure_cli = AzureCliAdapter(cfg.azure_subscription_id, cfg.azure_tenant_id, mode=cfg.mode)
    clouds = MultiCloudRegistry(
        {
            CloudProvider.AWS: AwsCloudAdapter(
                account_id=cfg.aws_account_id,
                default_region=cfg.aws_region,
                mode=cfg.mode,
            ),
            CloudProvider.GCP: GcpCloudAdapter(
                project_id=cfg.gcp_project_id,
                default_region=cfg.gcp_region,
                mode=cfg.mode,
            ),
            CloudProvider.AZURE: AzureCloudAdapter(azure_cli),
        }
    )

    terraform = TerraformRunner(cfg.terraform_dir, mode=cfg.mode)
    ansible = AnsibleRunner(cfg.ansible_dir, mode=cfg.mode)
    k8s = K8sLauncher(cfg.k8s_dir, mode=cfg.mode)
    rbac = PowerShellRbacPlanner(cfg.powershell_dir)
    opa_gate = OpaPolicyGate(
        policy_dir=cfg.opa_policy_dir,
        max_critical=cfg.max_critical_findings,
        max_high=cfg.max_high_findings,
        protected_envs=cfg.protected_env_set,
    )
    scanner = SecurityPipelineEngine(opa_gate=opa_gate)
    extensions = ExtensionHub(kafka=kafka)

    platform = PlatformService(
        settings=cfg,
        kafka=kafka,
        rabbitmq=rabbitmq,
        redis=redis,
        clouds=clouds,
        terraform=terraform,
        ansible=ansible,
        k8s=k8s,
        rbac=rbac,
        scanner=scanner,
        opa_gate=opa_gate,
        extensions=extensions,
    )
    if seed_demo:
        platform.seed_demo_topology()
    return platform
