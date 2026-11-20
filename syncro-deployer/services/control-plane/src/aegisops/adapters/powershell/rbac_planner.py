"""Multi-Cloud Least-Privilege IAM & ABAC Planner (Azure PowerShell · AWS IAM/PS · GCP gcloud CEL)."""

from __future__ import annotations

from pathlib import Path

from aegisops.domain.models import (
    CloudProvider,
    PolicyGateResult,
    PowerShellPermissionPlan,
    RbacAssignmentPlan,
)


class PowerShellRbacPlanner:
    """Generates, validates (OPA least-privilege), and renders IAM/ABAC plans across AWS, GCP, Azure."""

    AZURE_PERSONA_MAP: dict[str, tuple[str, str]] = {
        "auditor": ("AegisOps Auditor (Read-Only)", "infra/powershell/roles/aegis-auditor-role.json"),
        "deployer": ("AegisOps Scoped Deployer", "infra/powershell/roles/aegis-deployer-role.json"),
        "destroyer": ("AegisOps Ephemeral Destroyer", "infra/powershell/roles/aegis-destroyer-role.json"),
    }

    AWS_PERSONA_MAP: dict[str, tuple[str, str]] = {
        "auditor": ("AegisAwsSecurityAuditor", "infra/iam/aws/aegis-ephemeral-destroyer-policy.json"),
        "deployer": ("AegisAwsScopedDeployer", "infra/iam/aws/aegis-ephemeral-destroyer-policy.json"),
        "destroyer": ("AegisAwsEphemeralDestroyer", "infra/iam/aws/aegis-ephemeral-destroyer-policy.json"),
    }

    GCP_PERSONA_MAP: dict[str, tuple[str, str]] = {
        "auditor": ("roles/viewer", "infra/iam/gcp/aegis-ephemeral-destroyer-role.yaml"),
        "deployer": ("projects/aegisops/roles/aegisDeployer", "infra/iam/gcp/aegis-ephemeral-destroyer-role.yaml"),
        "destroyer": ("projects/aegisops/roles/aegisEphemeralDestroyer", "infra/iam/gcp/aegis-ephemeral-destroyer-role.yaml"),
    }

    FORBIDDEN_WIDE_ROLES = {"owner", "administratoraccess", "roles/owner", "*:*"}

    def __init__(self, powershell_dir: Path) -> None:
        self._powershell_dir = powershell_dir

    def create_plan(
        self,
        subscription_id: str,
        resource_group: str,
        principal_object_id: str,
        personas: list[str] | None = None,
        pim_max_duration_hours: int = 1,
        requested_role_override: str | None = None,
        cloud: CloudProvider = CloudProvider.AZURE,
    ) -> PowerShellPermissionPlan:
        selected = personas or ["auditor", "deployer", "destroyer"]
        assignments: list[RbacAssignmentPlan] = []

        role_table = {
            CloudProvider.AZURE: self.AZURE_PERSONA_MAP,
            CloudProvider.AWS: self.AWS_PERSONA_MAP,
            CloudProvider.GCP: self.GCP_PERSONA_MAP,
        }[cloud]

        for persona in selected:
            persona_key = persona.lower().strip()
            role_name, role_file = role_table.get(persona_key, role_table["auditor"])
            if requested_role_override:
                role_name = requested_role_override

            scope_level = "subscription" if persona_key == "auditor" else "resource_group"
            if cloud == CloudProvider.AZURE:
                scope = (
                    f"/subscriptions/{subscription_id}"
                    if scope_level == "subscription"
                    else f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
                )
                abac = (
                    "((!(ActionMatches{'Microsoft.Resources/subscriptions/resourceGroups/delete'})) "
                    "OR (@Resource[Microsoft.Resources/subscriptions/resourceGroups:tags] "
                    "StringContains 'aegis:ephemeral=true'))"
                    if persona_key == "destroyer"
                    else ""
                )
            elif cloud == CloudProvider.AWS:
                scope = (
                    f"arn:aws:iam::{subscription_id}:root"
                    if scope_level == "subscription"
                    else f"arn:aws:iam::{subscription_id}:role/{resource_group}"
                )
                abac = (
                    '{"StringEquals": {"aws:ResourceTag/aegis:ephemeral": "true", "aws:ResourceTag/aegis:managed": "true"}}'
                    if persona_key == "destroyer"
                    else ""
                )
            else:
                scope = (
                    f"projects/{subscription_id}"
                    if scope_level == "subscription"
                    else f"projects/{subscription_id}/locations/global/workloads/{resource_group}"
                )
                abac = (
                    "resource.matchTag('aegis_ephemeral', 'true') && request.time < timestamp('2027-01-01T00:00:00Z')"
                    if persona_key == "destroyer"
                    else ""
                )

            assignments.append(
                RbacAssignmentPlan(
                    cloud=cloud,
                    persona=persona_key,
                    role_name=role_name,
                    principal_object_id=principal_object_id,
                    scope=scope,
                    scope_level=scope_level,
                    abac_condition=abac,
                    pim_max_duration_hours=pim_max_duration_hours,
                    oidc_federated=True,
                    custom_role_file=role_file,
                )
            )

        opa_gate = self._evaluate_opa_rbac_policy(assignments)
        script, what_if_cmd = self._render_script(cloud, subscription_id, resource_group, principal_object_id, assignments, pim_max_duration_hours)

        return PowerShellPermissionPlan(
            cloud=cloud,
            subscription_id=subscription_id,
            resource_group=resource_group,
            assignments=assignments,
            opa_gate=opa_gate,
            powershell_script=script,
            what_if_command=what_if_cmd,
        )

    def _evaluate_opa_rbac_policy(self, assignments: list[RbacAssignmentPlan]) -> PolicyGateResult:
        violations: list[str] = []
        for item in assignments:
            if item.role_name.lower() in self.FORBIDDEN_WIDE_ROLES:
                violations.append(
                    f"[{item.cloud.value.upper()}] Principal '{item.principal_object_id}' cannot hold "
                    f"unrestricted '{item.role_name}' role; use a scoped custom role."
                )
            if item.persona == "destroyer" and "ephemeral" not in item.abac_condition.lower():
                violations.append(
                    f"[{item.cloud.value.upper()}] Destroyer assignment MUST enforce ABAC/CEL ephemeral tag condition"
                )
            if item.persona == "destroyer" and item.pim_max_duration_hours > 2:
                violations.append(
                    f"[{item.cloud.value.upper()}] Destroyer JIT/PIM elevation ({item.pim_max_duration_hours}h) exceeds 2h cap"
                )
        return PolicyGateResult(
            policy_package="aegisops.rbac.least_privilege",
            allowed=len(violations) == 0,
            violations=violations,
        )

    def _render_script(
        self,
        cloud: CloudProvider,
        account_scope: str,
        resource_group: str,
        principal: str,
        assignments: list[RbacAssignmentPlan],
        pim_hours: int,
    ) -> tuple[str, str]:
        if cloud == CloudProvider.AWS:
            lines = [
                "# Generated by AegisOps AWS Least-Privilege IAM & ABAC Planner (PowerShell / AWS CLI)",
                "# Requires AWSPowerShell.NetCore or AWS CLI v2 with OIDC Web Identity",
                f"$AccountId = '{account_scope}'",
                f"$StackScope = '{resource_group}'",
                "",
            ]
            for item in assignments:
                lines.extend(
                    [
                        f"# Persona: {item.persona.upper()} | Policy: {item.custom_role_file}",
                        f"aws iam create-policy --policy-name '{item.role_name}' --policy-document file://{item.custom_role_file} --dry-run",
                        f"aws iam attach-role-policy --role-name '{principal}' --policy-arn \"arn:aws:iam::$AccountId:policy/{item.role_name}\"",
                        f"# MaxSessionDuration enforced at {pim_hours * 3600}s (OIDC Federated)",
                        "",
                    ]
                )
            what_if = (
                f"aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::{account_scope}:role/{principal} "
                f"--action-names ec2:TerminateInstances --context-entries ContextKeyName=aws:ResourceTag/aegis:ephemeral,ContextKeyValues=true,ContextKeyType=string"
            )
            return "\n".join(lines), what_if

        if cloud == CloudProvider.GCP:
            lines = [
                "# Generated by AegisOps GCP Workload Identity & IAM CEL Condition Planner",
                f"export GCP_PROJECT='{account_scope}'",
                f"export MEMBER='principal://iam.googleapis.com/projects/{account_scope}/locations/global/workloadIdentityPools/aegis/subject/{principal}'",
                "",
            ]
            for item in assignments:
                cond_flag = (
                    f" --condition=\"expression={item.abac_condition},title=AegisEphemeralOnly\""
                    if item.abac_condition
                    else ""
                )
                lines.extend(
                    [
                        f"# Persona: {item.persona.upper()} | Custom Role YAML: {item.custom_role_file}",
                        f"gcloud projects add-iam-policy-binding \"$GCP_PROJECT\" --member=\"$MEMBER\" --role=\"{item.role_name}\"{cond_flag}",
                        "",
                    ]
                )
            what_if = f"gcloud projects get-iam-policy '{account_scope}' --format=json"
            return "\n".join(lines), what_if

        # Default: Microsoft Azure PowerShell
        lines = [
            "# Generated by AegisOps Azure PowerShell RBAC & ABAC Permissions Planner",
            "Set-StrictMode -Version Latest",
            "Import-Module ./infra/powershell/AegisOps.Permissions.psm1 -Force",
            "",
        ]
        for item in assignments:
            lines.extend(
                [
                    f"# Persona: {item.persona.upper()} | Custom Role: {item.custom_role_file}",
                    f"$plan_{item.persona} = New-AegisRbacPlan `",
                    f"    -SubscriptionId '{account_scope}' `",
                    f"    -ResourceGroupName '{resource_group}' `",
                    f"    -PrincipalObjectId '{item.principal_object_id}' `",
                    f"    -Persona '{item.persona}' `",
                    f"    -PimMaxDurationHours {item.pim_max_duration_hours}",
                    f"Grant-AegisScopedRole -Plan $plan_{item.persona} -WhatIf",
                    "",
                ]
            )
        what_if = (
            f"pwsh ./infra/powershell/Invoke-AegisPermissionPlan.ps1 "
            f"-SubscriptionId '{account_scope}' -ResourceGroupName '{resource_group}' "
            f"-PrincipalObjectId '{principal}' -Persona '{assignments[-1].persona}' "
            f"-PimMaxDurationHours {pim_hours} -WhatIf"
        )
        return "\n".join(lines), what_if
