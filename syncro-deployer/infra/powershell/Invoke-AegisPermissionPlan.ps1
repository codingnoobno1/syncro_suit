<#
.SYNOPSIS
    Idempotent, -WhatIf-safe runner for AegisOps Azure Least-Privilege RBAC & ABAC Permission Plans.
.EXAMPLE
    ./Invoke-AegisPermissionPlan.ps1 -SubscriptionId "0000-..." -ResourceGroupName "rg-aegis-payments-pr-412" -PrincipalObjectId "1111-..." -Persona destroyer -WhatIf
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory)] [string]$SubscriptionId,
    [Parameter(Mandatory)] [string]$ResourceGroupName,
    [Parameter(Mandatory)] [string]$PrincipalObjectId,
    [Parameter(Mandatory)] [ValidateSet('auditor', 'deployer', 'destroyer')] [string]$Persona,
    [int]$PimMaxDurationHours = 1,
    [string]$ExportJsonPath = ""
)

Import-Module (Join-Path $PSScriptRoot "AegisOps.Permissions.psm1") -Force

$plan = New-AegisRbacPlan `
    -SubscriptionId $SubscriptionId `
    -ResourceGroupName $ResourceGroupName `
    -PrincipalObjectId $PrincipalObjectId `
    -Persona $Persona `
    -PimMaxDurationHours $PimMaxDurationHours

$check = Test-AegisPermissions -Plan $plan
if (-not $check.Passed) {
    Write-Error "Policy Gate Failed:`n$($check.Violations -join "`n")"
    exit 1
}

if ($ExportJsonPath) {
    $plan | ConvertTo-Json -Depth 5 | Out-File -FilePath $ExportJsonPath -Encoding utf8
}

Grant-AegisScopedRole -Plan $plan -WhatIf:$WhatIfPreference
Write-Output "AegisOps PowerShell Permission Plan completed for persona '$Persona' at scope '$($plan.Scope)'."
