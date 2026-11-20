"""Tests for PowerShell Azure RBAC & ABAC Planner and Kubernetes OPA Launcher."""

from __future__ import annotations

from aegisops.application.platform_service import PlatformService
from aegisops.domain.models import K8sLaunchRequest


async def test_powershell_rbac_least_privilege_and_policy_denial(platform: PlatformService) -> None:
    good = await platform.generate_powershell_rbac_plan(
        resource_group="rg-aegis-payments-pr-412",
        principal_object_id="7b8f12c0-4a91-4d30-9f1a-000000000101",
        personas=["auditor", "deployer", "destroyer"],
        pim_max_duration_hours=1,
    )
    assert good.opa_gate.allowed is True
    assert "-WhatIf" in good.powershell_script
    destroyer = next(a for a in good.assignments if a.persona == "destroyer")
    assert "aegis:ephemeral=true" in destroyer.abac_condition

    bad_owner = await platform.generate_powershell_rbac_plan(
        resource_group="rg-aegis-payments-pr-412",
        principal_object_id="7b8f12c0-4a91-4d30-9f1a-000000000101",
        personas=["auditor"],
        requested_role_override="Owner",
    )
    assert bad_owner.opa_gate.allowed is False
    assert any("Owner" in v for v in bad_owner.opa_gate.violations)

    bad_pim = await platform.generate_powershell_rbac_plan(
        resource_group="rg-aegis-payments-pr-412",
        principal_object_id="7b8f12c0-4a91-4d30-9f1a-000000000101",
        personas=["destroyer"],
        pim_max_duration_hours=6,
    )
    assert bad_pim.opa_gate.allowed is False


async def test_kubernetes_launcher_enforces_immutable_image_tags(platform: PlatformService) -> None:
    ok_res = await platform.launch_kubernetes_workload(
        K8sLaunchRequest(
            project_id="edge-gateway",
            environment_id="env-staging-edge",
            workload_name="edge-gateway",
            image="acraegis.azurecr.io/edge-gateway:1.4.2",
            mode="ephemeral-job",
        )
    )
    assert ok_res.opa_gate.allowed is True
    assert ok_res.status == "launched"
    assert "runAsNonRoot: true" in ok_res.manifest_yaml

    denied = await platform.launch_kubernetes_workload(
        K8sLaunchRequest(
            project_id="edge-gateway",
            environment_id="env-staging-edge",
            workload_name="edge-gateway",
            image="acraegis.azurecr.io/edge-gateway:latest",
        )
    )
    assert denied.opa_gate.allowed is False
    assert denied.status == "denied_by_opa"
