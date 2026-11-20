"""Tests for Checkov, Trivy, Bandit, tfsec, OPA Policy Gates, and SARIF 2.1.0 export."""

from __future__ import annotations

from pathlib import Path

from aegisops.application.platform_service import PlatformService


async def test_hardened_repo_infra_passes_opa_gate(platform: PlatformService) -> None:
    report = await platform.run_security_scan(
        project_id="payments-core",
        target_path=str(platform.settings.terraform_dir),
    )
    assert report.opa_gate.allowed is True
    assert report.compliance_score == 100.0
    assert report.summary["CRITICAL"] == 0
    sarif = platform.export_scan_sarif(report.id)
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "AegisOps DevSecOps Pipeline"


async def test_insecure_iac_k8s_and_python_triggers_all_scanners_and_opa_deny(
    platform: PlatformService, tmp_path: Path
) -> None:
    (tmp_path / "bad.tf").write_text(
        """
resource "azurerm_key_vault" "bad" {
  purge_protection_enabled = false
}
resource "azurerm_network_security_group" "open_ssh" {
  security_rule {
    access                   = "Allow"
    destination_port_range   = "22"
    source_address_prefix    = "0.0.0.0/0"
  }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text("FROM python:latest\nRUN echo hi\n", encoding="utf-8")
    (tmp_path / "unsafe.py").write_text(
        "import subprocess, yaml\nsubprocess.run('ls', shell=True)\nyaml.load('a: 1')\neval('1+1')\n",
        encoding="utf-8",
    )

    report = await platform.run_security_scan(
        project_id="bad-app",
        target_path=str(tmp_path),
    )

    rule_ids = {f.rule_id for f in report.findings}
    assert "AZ-KV-001" in rule_ids
    assert "AZ-NET-001" in rule_ids
    assert "TRIVY-DS001" in rule_ids
    assert "TRIVY-DS002" in rule_ids
    assert "B307" in rule_ids
    assert "B602" in rule_ids
    assert "B506" in rule_ids
    assert report.opa_gate.allowed is False
    assert len(report.opa_gate.violations) >= 2
    assert report.compliance_score < 50.0
