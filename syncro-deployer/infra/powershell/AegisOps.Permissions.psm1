<#
.SYNOPSIS
    AegisOps Azure Least-Privilege RBAC & ABAC PowerShell Module.
.DESCRIPTION
    Provides auditable, -WhatIf-safe functions to plan, validate, apply, and revoke
    scoped Azure Custom Roles, OIDC Federated Workload Identities, and ABAC-guarded
    ephemeral destruction permissions.
#>

Set-StrictMode -Version Latest

function New-AegisRbacPlan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$SubscriptionId,
        [Parameter(Mandatory)] [string]$ResourceGroupName,
        [Parameter(Mandatory)] [string]$PrincipalObjectId,
        [Parameter(Mandatory)] [ValidateSet('auditor', 'deployer', 'destroyer')] [string]$Persona,
        [int]$PimMaxDurationHours = 1
    )

    $roleMap = @{
        auditor   = 'AegisOps Auditor (Read-Only)'
        deployer  = 'AegisOps Scoped Deployer'
        destroyer = 'AegisOps Ephemeral Destroyer'
    }

    $scope = if ($Persona -eq 'auditor') {
        "/subscriptions/$SubscriptionId"
    } else {
        "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName"
    }

    $abacCondition = if ($Persona -eq 'destroyer') {
        "((!(ActionMatches{'Microsoft.Resources/subscriptions/resourceGroups/delete'})) OR (@Resource[Microsoft.Resources/subscriptions/resourceGroups:tags] StringContains 'aegis:ephemeral=true'))"
    } else {
        ""
    }

    [PSCustomObject]@{
        SubscriptionId      = $SubscriptionId
        ResourceGroupName   = $ResourceGroupName
        PrincipalObjectId   = $PrincipalObjectId
        Persona             = $Persona
        RoleName            = $roleMap[$Persona]
        Scope               = $scope
        AbacCondition       = $abacCondition
        PimMaxDurationHours = $PimMaxDurationHours
        OidcFederated       = $true
        GeneratedAtUtc      = (Get-Date).ToUniversalTime().ToString("o")
    }
}

function Test-AegisPermissions {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [PSCustomObject]$Plan
    )

    $violations = @()

    if ($Plan.RoleName -eq 'Owner' -and $Plan.Scope -match '^/subscriptions/[^/]+$') {
        $violations += "CRITICAL: Subscription-wide Owner assignment is forbidden."
    }
    if ($Plan.Persona -eq 'destroyer' -and ($Plan.AbacCondition -notmatch 'aegis:ephemeral=true')) {
        $violations += "CRITICAL: Destroyer persona MUST include Azure ABAC tag condition aegis:ephemeral=true."
    }
    if ($Plan.Persona -eq 'destroyer' -and $Plan.PimMaxDurationHours -gt 2) {
        $violations += "HIGH: Destroyer PIM elevation duration ($($Plan.PimMaxDurationHours)h) exceeds 2h policy cap."
    }

    [PSCustomObject]@{
        Passed     = ($violations.Count -eq 0)
        Violations = $violations
        Plan       = $Plan
    }
}

function Grant-AegisScopedRole {
    [CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)] [PSCustomObject]$Plan
    )

    $audit = Test-AegisPermissions -Plan $Plan
    if (-not $audit.Passed) {
        throw "RBAC Policy Gate Denied: $($audit.Violations -join '; ')"
    }

    $actionDesc = "Assign '$($Plan.RoleName)' to $($Plan.PrincipalObjectId) at scope $($Plan.Scope)"
    if ($PSCmdlet.ShouldProcess($Plan.Scope, $actionDesc)) {
        if (Get-Command New-AzRoleAssignment -ErrorAction SilentlyContinue) {
            $params = @{
                ObjectId           = $Plan.PrincipalObjectId
                RoleDefinitionName = $Plan.RoleName
                Scope              = $Plan.Scope
            }
            if ($Plan.AbacCondition) {
                $params['Condition'] = $Plan.AbacCondition
                $params['ConditionVersion'] = '2.0'
            }
            New-AzRoleAssignment @params
        } else {
            Write-Warning "Az.Resources module not loaded; simulated execution only: $actionDesc"
        }
    }
}

function Revoke-AegisEphemeralAccess {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [Parameter(Mandatory)] [string]$SubscriptionId,
        [Parameter(Mandatory)] [string]$ResourceGroupName,
        [Parameter(Mandatory)] [string]$PrincipalObjectId
    )
    $scope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName"
    if ($PSCmdlet.ShouldProcess($scope, "Revoke ephemeral AegisOps role assignments for $PrincipalObjectId")) {
        if (Get-Command Remove-AzRoleAssignment -ErrorAction SilentlyContinue) {
            Remove-AzRoleAssignment -ObjectId $PrincipalObjectId -Scope $scope -RoleDefinitionName "AegisOps Ephemeral Destroyer" -ErrorAction SilentlyContinue
            Remove-AzRoleAssignment -ObjectId $PrincipalObjectId -Scope $scope -RoleDefinitionName "AegisOps Scoped Deployer" -ErrorAction SilentlyContinue
        } else {
            Write-Output "[SIMULATION] Revoked ephemeral assignments at $scope for $PrincipalObjectId"
        }
    }
}

Export-ModuleMember -Function New-AegisRbacPlan, Test-AegisPermissions, Grant-AegisScopedRole, Revoke-AegisEphemeralAccess
