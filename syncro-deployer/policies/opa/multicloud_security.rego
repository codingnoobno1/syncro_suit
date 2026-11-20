package aegisops.multicloud.security

# OPA Policy Gate: Multi-Cloud (AWS + GCP + Azure) Security & VM Compliance Baselines

default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    input.summary.critical > input.thresholds.max_critical
    msg := sprintf("CRITICAL findings (%d) exceed threshold (%d)", [input.summary.critical, input.thresholds.max_critical])
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "AWS-EC2-001"
    msg := "AWS EC2 MUST enforce IMDSv2 (metadata_options.http_tokens = 'required')"
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "AWS-SG-001"
    msg := "AWS Security Group MUST NOT allow SSH (22) or RDP (3389) from 0.0.0.0/0"
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "GCP-GCE-001"
    msg := "GCP Compute Engine MUST enable Shielded VM (enable_secure_boot and enable_vtpm)"
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "GCP-FW-001"
    msg := "GCP Firewall MUST NOT expose SSH/RDP to 0.0.0.0/0; use Identity-Aware Proxy (35.235.240.0/20)"
}

deny contains msg if {
    some finding in input.findings
    finding.rule_id == "AZ-VM-001"
    msg := "Azure Virtual Machines MUST disable password authentication and enable Trusted Launch (vTPM + Secure Boot)"
}
