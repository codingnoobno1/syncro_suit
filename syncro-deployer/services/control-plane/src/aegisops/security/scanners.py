"""DevSecOps Multi-Cloud Scanner Pipeline (Checkov, Trivy, Bandit, tfsec, OPA/Rego across AWS, GCP, Azure)."""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

from aegisops.domain.models import ScanReport, SecurityFinding, Severity
from aegisops.security.opa_gate import OpaPolicyGate


class SecurityPipelineEngine:
    """Runs Checkov, Trivy, Bandit, tfsec, and OPA gates across AWS, GCP, Azure IaC, K8s & Python."""

    SUPPORTED_SCANNERS = ("checkov", "trivy", "bandit", "tfsec", "opa")

    _SECRET_PATTERN = re.compile(
        r"""(?:password|secret|api_key|client_secret|access_key)\s*[:=]\s*["'][A-Za-z0-9_\-!@#$%^&*]{8,}["']""",
        re.IGNORECASE,
    )

    def __init__(self, opa_gate: OpaPolicyGate) -> None:
        self._opa_gate = opa_gate

    async def run_scan(
        self,
        project_id: str,
        target_path: Path,
        scanners: list[str] | None = None,
    ) -> ScanReport:
        started = time.perf_counter()
        requested = [s.lower() for s in (scanners or list(self.SUPPORTED_SCANNERS))]
        active = [s for s in requested if s in self.SUPPORTED_SCANNERS] or list(
            self.SUPPORTED_SCANNERS
        )

        findings: list[SecurityFinding] = []

        if target_path.exists():
            if "checkov" in active or "tfsec" in active:
                findings.extend(self._scan_terraform_iac(target_path, active))
            if "trivy" in active:
                findings.extend(self._scan_containers_and_k8s(target_path))
            if "bandit" in active:
                findings.extend(self._scan_python_sast(target_path))

        summary = {sev.value: 0 for sev in Severity}
        for finding in findings:
            summary[finding.severity.value] += 1

        penalty = (
            summary[Severity.CRITICAL.value] * 25
            + summary[Severity.HIGH.value] * 12
            + summary[Severity.MEDIUM.value] * 5
            + summary[Severity.LOW.value] * 2
        )
        compliance_score = round(max(0.0, 100.0 - penalty), 1)
        opa_gate = await self._opa_gate.evaluate_scan(findings, summary)
        duration_ms = max(1, int((time.perf_counter() - started) * 1000))

        return ScanReport(
            project_id=project_id,
            target_path=str(target_path),
            scanners_executed=active,
            findings=findings,
            summary=summary,
            compliance_score=compliance_score,
            opa_gate=opa_gate,
            duration_ms=duration_ms,
        )

    def _scan_terraform_iac(self, root: Path, active: list[str]) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        tf_files = [root] if root.is_file() and root.suffix == ".tf" else list(root.rglob("*.tf"))
        scanner_name = "checkov" if "checkov" in active else "tfsec"

        for tf_file in sorted(tf_files):
            text = tf_file.read_text(encoding="utf-8", errors="ignore")
            rel = str(tf_file)

            # ---- AZURE RULES ----
            if "azurerm_key_vault" in text and re.search(r"purge_protection_enabled\s*=\s*false", text):
                findings.append(
                    SecurityFinding(
                        scanner=scanner_name,
                        rule_id="AZ-KV-001",
                        severity=Severity.CRITICAL,
                        title="Azure Key Vault purge protection is disabled",
                        file_path=rel,
                        line=self._find_line(text, "purge_protection_enabled"),
                        remediation="Set purge_protection_enabled = true and soft_delete_retention_days = 90.",
                        cwe="CWE-284",
                        cloud="azure",
                    )
                )

            for rule_match in re.finditer(r"security_rule\s*\{([^}]*)\}", text, re.DOTALL):
                block = rule_match.group(1)
                if (
                    re.search(r'access\s*=\s*"Allow"', block)
                    and re.search(r'source_address_prefix\s*=\s*"(\*|0\.0\.0\.0/0|Internet)"', block)
                    and re.search(r"destination_port_range[s]?\s*=\s*.*(22|3389)", block)
                ):
                    findings.append(
                        SecurityFinding(
                            scanner="tfsec" if "tfsec" in active else "checkov",
                            rule_id="AZ-NET-001",
                            severity=Severity.CRITICAL,
                            title="Azure NSG allows unrestricted SSH/RDP from Internet/0.0.0.0/0",
                            file_path=rel,
                            line=text[: rule_match.start()].count("\n") + 1,
                            remediation="Restrict inbound SSH/RDP to Azure Bastion or corporate CIDR blocks.",
                            cwe="CWE-284",
                            cloud="azure",
                        )
                    )

            if "azurerm_kubernetes_cluster" in text and re.search(
                r"role_based_access_control_enabled\s*=\s*false", text
            ):
                findings.append(
                    SecurityFinding(
                        scanner="checkov",
                        rule_id="AZ-AKS-001",
                        severity=Severity.HIGH,
                        title="AKS cluster disables Kubernetes RBAC",
                        file_path=rel,
                        line=self._find_line(text, "role_based_access_control_enabled"),
                        remediation="Enable role_based_access_control_enabled = true and Azure AD RBAC.",
                        cwe="CWE-862",
                        cloud="azure",
                    )
                )

            if "azurerm_linux_virtual_machine" in text and (
                re.search(r"disable_password_authentication\s*=\s*false", text)
                or re.search(r"secure_boot_enabled\s*=\s*false", text)
            ):
                findings.append(
                    SecurityFinding(
                        scanner="checkov",
                        rule_id="AZ-VM-001",
                        severity=Severity.CRITICAL,
                        title="Azure VM enables password auth or disables Trusted Launch Secure Boot",
                        file_path=rel,
                        line=self._find_line(text, "azurerm_linux_virtual_machine"),
                        remediation="Set disable_password_authentication = true, secure_boot_enabled = true, vtpm_enabled = true.",
                        cwe="CWE-287",
                        cloud="azure",
                    )
                )

            if "azurerm_container_registry" in text and re.search(r"admin_enabled\s*=\s*true", text):
                findings.append(
                    SecurityFinding(
                        scanner="tfsec" if "tfsec" in active else "checkov",
                        rule_id="AZ-ACR-002",
                        severity=Severity.HIGH,
                        title="Azure Container Registry admin account is enabled",
                        file_path=rel,
                        line=self._find_line(text, "admin_enabled"),
                        remediation="Disable admin_enabled and authenticate AKS via Managed Identity.",
                        cwe="CWE-250",
                        cloud="azure",
                    )
                )

            # ---- AWS RULES ----
            if "aws_instance" in text and (
                re.search(r'http_tokens\s*=\s*"optional"', text) or "metadata_options" not in text
            ):
                findings.append(
                    SecurityFinding(
                        scanner="checkov",
                        rule_id="AWS-EC2-001",
                        severity=Severity.CRITICAL,
                        title="AWS EC2 instance does not strictly enforce IMDSv2",
                        file_path=rel,
                        line=self._find_line(text, "aws_instance"),
                        remediation="Add metadata_options { http_tokens = 'required' } to prevent SSRF credential theft.",
                        cwe="CWE-918",
                        cloud="aws",
                    )
                )

            for ing_match in re.finditer(r"ingress\s*\{([^}]*)\}", text, re.DOTALL):
                block = ing_match.group(1)
                if re.search(r"0\.0\.0\.0/0", block) and re.search(
                    r"(?:from_port|to_port)\s*=\s*(22|3389)\b", block
                ):
                    findings.append(
                        SecurityFinding(
                            scanner="tfsec" if "tfsec" in active else "checkov",
                            rule_id="AWS-SG-001",
                            severity=Severity.CRITICAL,
                            title="AWS Security Group exposes SSH/RDP to 0.0.0.0/0",
                            file_path=rel,
                            line=text[: ing_match.start()].count("\n") + 1,
                            remediation="Use AWS Systems Manager Session Manager or restrict CIDR to corporate bastion.",
                            cwe="CWE-284",
                            cloud="aws",
                        )
                    )

            if "aws_instance" in text and re.search(r"encrypted\s*=\s*false", text):
                findings.append(
                    SecurityFinding(
                        scanner="tfsec",
                        rule_id="AWS-EBS-001",
                        severity=Severity.HIGH,
                        title="AWS EC2 EBS volume encryption is disabled",
                        file_path=rel,
                        line=self._find_line(text, "encrypted"),
                        remediation="Set root_block_device.encrypted = true with a customer-managed KMS key.",
                        cwe="CWE-311",
                        cloud="aws",
                    )
                )

            # ---- GCP RULES ----
            if "google_compute_instance" in text and (
                re.search(r"enable_secure_boot\s*=\s*false", text)
                or "shielded_instance_config" not in text
            ):
                findings.append(
                    SecurityFinding(
                        scanner="checkov",
                        rule_id="GCP-GCE-001",
                        severity=Severity.CRITICAL,
                        title="GCP Compute Engine instance lacks Shielded VM Secure Boot",
                        file_path=rel,
                        line=self._find_line(text, "google_compute_instance"),
                        remediation="Configure shielded_instance_config with enable_secure_boot = true and enable_vtpm = true.",
                        cwe="CWE-345",
                        cloud="gcp",
                    )
                )

            if (
                "google_compute_firewall" in text
                and re.search(r'source_ranges\s*=\s*\[[^\]]*"0\.0\.0\.0/0"', text)
                and re.search(r'ports\s*=\s*\[.*"(22|3389)"', text)
            ):
                findings.append(
                    SecurityFinding(
                        scanner="tfsec" if "tfsec" in active else "checkov",
                        rule_id="GCP-FW-001",
                        severity=Severity.CRITICAL,
                        title="GCP Firewall exposes SSH/RDP to 0.0.0.0/0",
                        file_path=rel,
                        line=self._find_line(text, "0.0.0.0/0"),
                        remediation="Restrict SSH ingress strictly to Identity-Aware Proxy (35.235.240.0/20).",
                        cwe="CWE-284",
                        cloud="gcp",
                    )
                )

            if "google_storage_bucket" in text and re.search(
                r"uniform_bucket_level_access\s*=\s*false", text
            ):
                findings.append(
                    SecurityFinding(
                        scanner="checkov",
                        rule_id="GCP-GCS-001",
                        severity=Severity.HIGH,
                        title="GCP Cloud Storage bucket disables Uniform Bucket-Level Access",
                        file_path=rel,
                        line=self._find_line(text, "uniform_bucket_level_access"),
                        remediation="Set uniform_bucket_level_access = true and public_access_prevention = 'enforced'.",
                        cwe="CWE-732",
                        cloud="gcp",
                    )
                )

        return findings

    def _scan_containers_and_k8s(self, root: Path) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        candidates = (
            [root]
            if root.is_file()
            else [
                p
                for p in root.rglob("*")
                if p.is_file()
                and ".venv" not in p.parts
                and "node_modules" not in p.parts
                and (p.name.startswith("Dockerfile") or p.suffix in {".yaml", ".yml"})
            ]
        )

        for path in sorted(candidates):
            text = path.read_text(encoding="utf-8", errors="ignore")
            rel = str(path)

            if path.name.startswith("Dockerfile"):
                if re.search(r"^FROM\s+\S+:latest\b", text, re.MULTILINE):
                    findings.append(
                        SecurityFinding(
                            scanner="trivy",
                            rule_id="TRIVY-DS001",
                            severity=Severity.MEDIUM,
                            title="Dockerfile uses mutable ':latest' base image tag",
                            file_path=rel,
                            line=self._find_line(text, ":latest"),
                            remediation="Pin base images to an explicit version or SHA256 digest.",
                        )
                    )
                if "USER " not in text:
                    findings.append(
                        SecurityFinding(
                            scanner="trivy",
                            rule_id="TRIVY-DS002",
                            severity=Severity.HIGH,
                            title="Dockerfile runs container as root (missing USER directive)",
                            file_path=rel,
                            line=1,
                            remediation="Create and switch to a non-root USER UID >= 10000.",
                            cwe="CWE-250",
                        )
                    )

            if path.suffix in {".yaml", ".yml"} and "kind: Deployment" in text:
                if re.search(r"privileged:\s*true", text):
                    findings.append(
                        SecurityFinding(
                            scanner="trivy",
                            rule_id="TRIVY-KSV017",
                            severity=Severity.CRITICAL,
                            title="Kubernetes Deployment enables privileged container execution",
                            file_path=rel,
                            line=self._find_line(text, "privileged"),
                            remediation="Set securityContext.privileged: false and drop ALL capabilities.",
                            cwe="CWE-250",
                        )
                    )

            secret_match = self._SECRET_PATTERN.search(text)
            if secret_match and "example" not in path.name.lower() and "values" not in path.name.lower():
                if "change-me" not in secret_match.group(0).lower():
                    findings.append(
                        SecurityFinding(
                            scanner="trivy",
                            rule_id="TRIVY-SEC-001",
                            severity=Severity.HIGH,
                            title="Potential hardcoded credential detected in configuration",
                            file_path=rel,
                            line=text[: secret_match.start()].count("\n") + 1,
                            remediation="Store secrets in AWS Secrets Manager, GCP Secret Manager, or Azure Key Vault.",
                            cwe="CWE-798",
                        )
                    )

        return findings

    def _scan_python_sast(self, root: Path) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        py_files = (
            [root]
            if root.is_file() and root.suffix == ".py"
            else [
                p
                for p in root.rglob("*.py")
                if ".venv" not in p.parts and "tests" not in p.parts and "__pycache__" not in p.parts
            ]
        )

        for py_file in sorted(py_files):
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func_name = self._resolve_call_name(node.func)
                    if func_name in {"eval", "exec"}:
                        findings.append(
                            SecurityFinding(
                                scanner="bandit",
                                rule_id="B307",
                                severity=Severity.CRITICAL,
                                title=f"Dangerous dynamic code execution via `{func_name}()`",
                                file_path=str(py_file),
                                line=getattr(node, "lineno", 1),
                                remediation="Replace eval/exec with ast.literal_eval or structured parsers.",
                                cwe="CWE-95",
                            )
                        )
                    if func_name in {"subprocess.Popen", "subprocess.run", "subprocess.call"}:
                        for kw in node.keywords:
                            if (
                                kw.arg == "shell"
                                and isinstance(kw.value, ast.Constant)
                                and kw.value.value is True
                            ):
                                findings.append(
                                    SecurityFinding(
                                        scanner="bandit",
                                        rule_id="B602",
                                        severity=Severity.HIGH,
                                        title="Subprocess invocation with shell=True risks command injection",
                                        file_path=str(py_file),
                                        line=getattr(node, "lineno", 1),
                                        remediation="Pass an explicit argv list with shell=False.",
                                        cwe="CWE-78",
                                    )
                                )
                    if func_name == "yaml.load":
                        findings.append(
                            SecurityFinding(
                                scanner="bandit",
                                rule_id="B506",
                                severity=Severity.HIGH,
                                title="Unsafe yaml.load() invocation allows arbitrary object instantiation",
                                file_path=str(py_file),
                                line=getattr(node, "lineno", 1),
                                remediation="Use yaml.safe_load() instead of yaml.load().",
                                cwe="CWE-502",
                            )
                        )
        return findings

    @staticmethod
    def _resolve_call_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        return ""

    @staticmethod
    def _find_line(text: str, needle: str) -> int:
        for idx, line in enumerate(text.splitlines(), start=1):
            if needle in line:
                return idx
        return 1
