# ADR-004: PowerShell Azure Least-Privilege RBAC & ABAC Permissions Plan

- **Status**: Accepted
- **Date**: 2026-11-19

## Context

Enterprise Azure IAM governance relies heavily on PowerShell (`Az.Resources`, `Microsoft.Graph`) for auditable, `-WhatIf`-verifiable role assignments, custom role definitions, PIM elevation policies, and OIDC Federated Identity credentials. Granting CI pipelines subscription-wide `Owner` or `Contributor` violates CIS Azure Benchmarks.

## Decision

1. Ship a dedicated PowerShell module (`infra/powershell/AegisOps.Permissions.psm1`) and idempotent execution script (`infra/powershell/Invoke-AegisPermissionPlan.ps1`) supporting `-WhatIf` dry-runs and JSON audit exports.
2. Enforce strict **Three-Persona Role Separation**:
   - **Auditor** (`aegis-auditor-role.json`): Read-only compliance & Microsoft Defender assessments.
   - **Deployer** (`aegis-deployer-role.json`): Scoped to target Resource Group(s); explicitly denies `Microsoft.Authorization/*/write` and lock deletion.
   - **Destroyer** (`aegis-destroyer-role.json`): Restricted by **Azure ABAC Role Assignment Condition** to resource groups tagged `aegis:ephemeral=true` and time-bounded via PIM (<= 2h).
3. Validate every generated permission plan against `policies/opa/rbac_least_privilege.rego` via `aegis rbac plan` and the MCP server before operators execute PowerShell against Azure.
