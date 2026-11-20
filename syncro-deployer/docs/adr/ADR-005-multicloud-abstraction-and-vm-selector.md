# ADR-005: Multi-Cloud Provider Abstraction (AWS · GCP · Azure) & Intelligent VM Selector

- **Status**: Accepted
- **Date**: 2026-11-19

## Context

Enterprise DevSecOps teams frequently operate workloads across **AWS**, **GCP**, and **Azure** simultaneously (for example, AWS EC2/EKS for edge APIs, GCP Shielded/Confidential GCE & GKE for AI/ML workloads, and Azure AKS/Trusted Launch VMs for enterprise core services). Engineers also struggle to compare VM SKUs, confidential computing support, spot savings, and CIS-hardened images consistently across all three hyperscalers.

## Decision

1. **Uniform Multi-Cloud Port (`ports/cloud.py` -> `CloudProviderPort`)**:
   - Standardize account health, deletion lock / lien / termination-protection checks, ephemeral teardown, and IAM/ABAC policy generation behind a single protocol implemented by:
     - `AwsCloudAdapter` (`aws` CLI + IMDSv2 + Termination Protection + `aws:ResourceTag/aegis:ephemeral`)
     - `GcpCloudAdapter` (`gcloud` CLI + Shielded/Confidential VM + Project Lien + IAM CEL conditions)
     - `AzureCloudAdapter` (`az` CLI + Trusted Launch + `CanNotDelete` Lock + PowerShell ABAC conditions)
2. **Intelligent Multi-Cloud VM & Compute Selector (`vm_catalog.py` + `vm_selector_service.py`)**:
   - Curated cross-cloud SKU catalog covering AWS EC2, GCP Compute Engine, and Azure VMs across `general-purpose`, `compute-optimized`, `memory-optimized`, `confidential-sec`, and `gpu-ai` profiles.
   - Multi-factor composite scoring (cost efficiency, hardware security posture—SEV-SNP/TDX/Nitro Enclave/vTPM—right-sizing fit, and Spot/Preemptible savings).
   - Generates cloud-native, CIS-hardened Terraform HCL + Ansible inventory + IAM least-privilege plan directly from any selected VM SKU and supports 1-click ephemeral provisioning into the Control Plane.
3. **Unified Multi-Cloud Security & OPA Gates (`policies/opa/multicloud_security.rego`)**:
   - Enforces AWS IMDSv2 (`AWS-EC2-001`), AWS SG/S3 rules, GCP Shielded VM (`GCP-GCE-001`), GCP IAP-only Firewall (`GCP-FW-001`), and Azure Trusted Launch (`AZ-VM-001`) uniformly across repositories.
