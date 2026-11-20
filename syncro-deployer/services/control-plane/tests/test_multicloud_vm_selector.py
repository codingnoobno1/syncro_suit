"""Comprehensive tests for Multi-Cloud (AWS, GCP, Azure), VM Selector, FinOps, Drift & Multi-Cloud Security."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aegisops.application.platform_service import PlatformService
from aegisops.domain.models import (
    CloudProvider,
    VmProvisionRequest,
    VmSelectionCriteria,
    WorkloadProfile,
)


async def test_vm_selector_compares_all_three_clouds_and_generates_hcl(
    platform: PlatformService,
) -> None:
    matrix = platform.vm_selector.compare_clouds(
        VmSelectionCriteria(
            min_vcpu=4,
            min_memory_gib=16,
            require_confidential_compute=True,
            prefer_spot=True,
        )
    )
    assert set(matrix.best_by_cloud.keys()) == {"aws", "gcp", "azure"}
    assert matrix.best_by_cloud["aws"] is not None
    assert matrix.best_by_cloud["gcp"] is not None
    assert matrix.best_by_cloud["azure"] is not None
    assert matrix.cheapest_cloud in {"aws", "gcp", "azure"}
    assert "http_tokens" in matrix.best_by_cloud["aws"].terraform_snippet
    assert "shielded_instance_config" in matrix.best_by_cloud["gcp"].terraform_snippet
    assert "secure_boot_enabled" in matrix.best_by_cloud["azure"].terraform_snippet


async def test_vm_selector_gpu_and_arm64_filters(platform: PlatformService) -> None:
    gpu_recs = platform.vm_selector.recommend(
        VmSelectionCriteria(workload_profile=WorkloadProfile.GPU_AI, require_gpu=True)
    )
    assert len(gpu_recs) == 3
    assert {r.sku.cloud for r in gpu_recs} == {
        CloudProvider.AWS,
        CloudProvider.GCP,
        CloudProvider.AZURE,
    }


async def test_provision_ephemeral_vm_across_clouds_and_quick_destroy(
    platform: PlatformService,
) -> None:
    for cloud, sku, region in (
        (CloudProvider.AWS, "m7i.xlarge", "us-east-1"),
        (CloudProvider.GCP, "n2d-standard-4", "us-central1"),
        (CloudProvider.AZURE, "Standard_DC4as_v5", "eastus2"),
    ):
        prov = await platform.vm_selector.provision_ephemeral_vm(
            VmProvisionRequest(
                project_id="edge-gateway",
                environment_name=f"test-{cloud.value}",
                cloud=cloud,
                sku=sku,
                region=region,
                use_spot=True,
                ttl_hours=2,
            )
        )
        assert prov.environment.cloud == cloud
        assert prov.environment.vm_sku == sku
        assert prov.environment.id in platform.environments

        preview = await platform.destroyer.preview(prov.environment.id)
        assert preview.cloud == cloud
        assert preview.opa_gate.allowed is True
        assert preview.confirmation_token is not None

        destroyed = await platform.destroyer.execute(
            prov.environment.id,
            confirmation_token=preview.confirmation_token,
            kill_switch=True,
        )
        assert destroyed.cloud == cloud
        assert destroyed.status == "destroyed"


async def test_multicloud_security_scanner_catches_aws_gcp_and_azure_vm_flaws(
    platform: PlatformService, tmp_path: Path
) -> None:
    (tmp_path / "aws_bad.tf").write_text(
        """
resource "aws_instance" "leaky" {
  ami           = "ami-123"
  instance_type = "m7i.xlarge"
  root_block_device { encrypted = false }
}
resource "aws_security_group" "open_ssh" {
  ingress {
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["0.0.0.0/0"]
  }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "gcp_bad.tf").write_text(
        """
resource "google_compute_instance" "unshielded" {
  name         = "bad-gce"
  machine_type = "n2d-standard-4"
}
resource "google_compute_firewall" "open_rdp" {
  allow { ports = ["3389"] }
  source_ranges = ["0.0.0.0/0"]
}
resource "google_storage_bucket" "legacy" {
  name = "bad-bucket"
  uniform_bucket_level_access = false
}
""",
        encoding="utf-8",
    )
    (tmp_path / "azure_vm_bad.tf").write_text(
        """
resource "azurerm_linux_virtual_machine" "weak_vm" {
  name = "weak"
  disable_password_authentication = false
}
""",
        encoding="utf-8",
    )

    report = await platform.run_security_scan("multicloud-bad", str(tmp_path))
    rules = {f.rule_id for f in report.findings}
    assert {"AWS-EC2-001", "AWS-SG-001", "AWS-EBS-001", "GCP-GCE-001", "GCP-FW-001", "GCP-GCS-001", "AZ-VM-001"} <= rules
    assert report.opa_gate.allowed is False


async def test_multicloud_iam_plans_and_policy_gates(platform: PlatformService) -> None:
    aws_plan = await platform.generate_powershell_rbac_plan(
        resource_group="aws-stack-edge-pr-501",
        principal_object_id="aegis-ci-role",
        cloud=CloudProvider.AWS,
    )
    assert aws_plan.opa_gate.allowed is True
    assert "aws:ResourceTag/aegis:ephemeral" in aws_plan.assignments[-1].abac_condition

    gcp_plan = await platform.generate_powershell_rbac_plan(
        resource_group="gcp-proj-ai-pr-608",
        principal_object_id="aegis-deployer",
        cloud=CloudProvider.GCP,
    )
    assert gcp_plan.opa_gate.allowed is True
    assert "resource.matchTag('aegis_ephemeral', 'true')" in gcp_plan.assignments[-1].abac_condition

    denied_aws = await platform.generate_powershell_rbac_plan(
        resource_group="aws-stack-edge-pr-501",
        principal_object_id="rogue-role",
        cloud=CloudProvider.AWS,
        requested_role_override="AdministratorAccess",
    )
    assert denied_aws.opa_gate.allowed is False


def test_multicloud_api_vm_finops_and_drift_endpoints(client: TestClient) -> None:
    assert len(client.get("/api/v1/vms/catalog").json()) >= 18
    assert len(client.get("/api/v1/vms/catalog?cloud=gcp").json()) >= 5

    comp = client.post(
        "/api/v1/vms/compare",
        json={"min_vcpu": 4, "min_memory_gib": 16, "require_confidential_compute": True},
    ).json()
    assert comp["best_by_cloud"]["aws"] is not None
    assert comp["best_by_cloud"]["gcp"] is not None
    assert comp["best_by_cloud"]["azure"] is not None

    finops = client.get("/api/v1/finops/summary").json()
    assert len(finops["by_cloud"]) == 3
    assert finops["total_hourly_usd"] > 0

    drift = client.post("/api/v1/drift/env-aws-edge-501/check").json()
    assert drift["cloud"] == "aws"
    assert drift["drifted_count"] == 0
