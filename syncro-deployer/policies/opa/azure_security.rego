package aegisops.azure.security

# OPA Policy Gate: Azure Infrastructure Security Baselines
# Denies Terraform plans or scan reports violating mandatory Azure CIS controls.

default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    input.summary.critical > input.thresholds.max_critical
    msg := sprintf("CRITICAL security findings (%d) exceed threshold (%d)", [input.summary.critical, input.thresholds.max_critical])
}

deny contains msg if {
    input.summary.high > input.thresholds.max_high
    msg := sprintf("HIGH security findings (%d) exceed threshold (%d)", [input.summary.high, input.thresholds.max_high])
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "AZ-KV-001"
    msg := "Azure Key Vault MUST enable purge_protection_enabled and soft_delete_retention_days >= 90"
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "AZ-NET-001"
    msg := "Azure NSG MUST NOT allow unrestricted inbound SSH (22) or RDP (3389) from 0.0.0.0/0"
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "AZ-AKS-001"
    msg := "AKS clusters MUST enable Azure AD RBAC and network_policy"
}
