"""End-to-end tests for IaC Terraform MCP (generate/build/run/graph), Script Writers (Ansible/Helm/CI-CD/Container), Security MCP (Trivy/Bandit/SAST/DAST), REST API & Syncro CLI."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from aegisops.cli.main import app as cli_app


def _rpc(client: TestClient, method: str, params: dict | None = None, rid: int = 1) -> dict:
    payload: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload).json()


def test_terraform_generate_build_run_and_devsecops_graph_end_to_end(
    client: TestClient, tmp_path: Path
) -> None:
    out_dir = tmp_path / "tf-aws-stack"
    gen = client.post(
        "/api/v1/iac/terraform/generate",
        json={
            "project_name": "edge-payments",
            "cloud": "aws",
            "blueprint": "vpc-k8s",
            "environment": "staging",
            "write_to_disk": True,
            "output_dir": str(out_dir),
        },
    )
    assert gen.status_code == 201
    ws = gen.json()
    assert ws["cloud"] == "aws"
    assert ws["written_to_disk"] is True
    assert len(ws["files"]) >= 5
    assert len(ws["resources"]) >= 6
    assert (out_dir / "main.tf").exists()
    assert (out_dir / "security.tf").exists()

    # Build & validate
    build = client.post("/api/v1/iac/terraform/build", json={"workspace_id": ws["workspace_id"]}).json()
    assert build["validate_ok"] is True
    assert build["syntax_issues"] == []
    assert len(build["resources_discovered"]) >= 6

    # Run plan/apply (dry_run=False simulated apply with guardrails)
    run = client.post(
        "/api/v1/iac/terraform/run",
        json={"workspace_id": ws["workspace_id"], "action": "apply", "dry_run": False, "auto_approve": True},
    ).json()
    assert run["guardrail_allowed"] is True
    assert run["status"] == "applied"
    assert run["devsecops_graph"] is not None
    graph = run["devsecops_graph"]
    assert graph["security_score"] == 100.0
    assert "flowchart LR" in graph["mermaid"]
    assert "digraph" in graph["dot"]
    assert len(graph["nodes"]) >= 8
    assert len(graph["edges"]) >= 5

    # Production destroy must be strictly blocked by guardrail
    blocked = client.post(
        "/api/v1/iac/terraform/run",
        json={
            "workspace_id": ws["workspace_id"],
            "action": "destroy",
            "dry_run": False,
            "environment": "production",
        },
    ).json()
    assert blocked["guardrail_allowed"] is False
    assert blocked["status"] == "blocked"
    assert blocked["exit_code"] == 126


def test_script_writers_ansible_helm_cicd_and_container(client: TestClient, tmp_path: Path) -> None:
    ans = client.post(
        "/api/v1/scripts/ansible/generate",
        json={"service_name": "ledger-nodes", "cloud": "gcp", "write_to_disk": True, "output_dir": str(tmp_path / "ans")},
    )
    assert ans.status_code == 201
    ans_data = ans.json()
    assert ans_data["validation"]["syntax_ok"] is True
    assert (tmp_path / "ans" / "site.yml").exists()

    helm = client.post(
        "/api/v1/scripts/helm/generate",
        json={"chart_name": "ledger-api", "cloud": "azure", "write_to_disk": True, "output_dir": str(tmp_path / "helm")},
    )
    assert helm.status_code == 201
    helm_data = helm.json()
    assert helm_data["validation"]["syntax_ok"] is True
    assert (tmp_path / "helm" / "Chart.yaml").exists()
    assert (tmp_path / "helm" / "templates" / "networkpolicy.yaml").exists()

    for plat, expected_file in [
        ("github-actions", ".github/workflows/ledger-api-devsecops.yml"),
        ("gitlab-ci", ".gitlab-ci.yml"),
        ("azure-devops", "azure-pipelines.yml"),
        ("jenkins", "Jenkinsfile"),
    ]:
        ci = client.post(
            "/api/v1/scripts/cicd/generate",
            json={
                "project_name": "ledger-api",
                "platform": plat,
                "cloud": "aws",
                "write_to_disk": True,
                "output_dir": str(tmp_path / f"ci-{plat}"),
            },
        )
        assert ci.status_code == 201
        ci_data = ci.json()
        assert ci_data["validation"]["syntax_ok"] is True
        written = tmp_path / f"ci-{plat}" / expected_file
        assert written.exists()
        text = written.read_text(encoding="utf-8")
        assert "syncro sec" in text
        assert "syncro iac" in text

    ctr = client.post(
        "/api/v1/scripts/container/generate",
        json={"service_name": "ledger-api", "language": "go", "write_to_disk": True, "output_dir": str(tmp_path / "ctr")},
    )
    assert ctr.status_code == 201
    assert ctr.json()["validation"]["non_root_user"] is True
    assert (tmp_path / "ctr" / "Dockerfile").exists()


def test_security_mcp_trivy_bandit_sast_dast_and_full_assessment(
    client: TestClient, tmp_path: Path
) -> None:
    # Seed intentionally vulnerable files in a temporary directory
    vuln_dir = tmp_path / "vuln_app"
    vuln_dir.mkdir()
    (vuln_dir / "Dockerfile").write_text("FROM python:latest\nRUN pip install flask\n", encoding="utf-8")
    (vuln_dir / "deploy.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nspec:\n  containers:\n    - securityContext:\n        privileged: true\n",
        encoding="utf-8",
    )
    (vuln_dir / "requirements.txt").write_text("pyyaml==5.3.1\n", encoding="utf-8")
    (vuln_dir / "app.py").write_text(
        "import subprocess, yaml, hashlib\n"
        "def bad(cmd, raw):\n"
        "    eval(raw)\n"
        "    subprocess.run(cmd, shell=True)\n"
        "    yaml.load(raw)\n"
        "    return hashlib.md5(b'x').hexdigest()\n",
        encoding="utf-8",
    )
    (vuln_dir / "web.js").write_text(
        "function render(u) { document.write(u); return eval(u); }\n",
        encoding="utf-8",
    )

    trivy = client.post("/api/v1/security/assess/trivy", json={"target_path": str(vuln_dir)}).json()
    trivy_rules = {f["rule_id"] for f in trivy["findings"]}
    assert {"DS001", "DS002", "KSV017", "CVE-2020-14343"} <= trivy_rules

    bandit = client.post("/api/v1/security/assess/bandit", json={"target_path": str(vuln_dir)}).json()
    bandit_rules = {f["rule_id"] for f in bandit["findings"]}
    assert {"B307", "B602", "B506", "B324"} <= bandit_rules

    sast = client.post("/api/v1/security/assess/sast", json={"target_path": str(vuln_dir)}).json()
    sast_rules = {f["rule_id"] for f in sast["findings"]}
    assert {"SAST-JS-XSS-001", "SAST-JS-EVAL-001"} <= sast_rules

    dast = client.post(
        "/api/v1/security/assess/dast",
        json={"target_url": "http://insecure.example.com/login", "live_probe": False},
    ).json()
    assert any(f["rule_id"] == "DAST-TLS-001" for f in dast["findings"])
    assert len(dast["dast_probes"]) >= 3

    full = client.post(
        "/api/v1/security/assess/full",
        json={
            "project_id": "vuln-demo",
            "target_path": str(vuln_dir),
            "target_url": "https://staging.example.com",
            "include_dast": True,
            "include_graph": True,
            "live_dast_probe": False,
        },
    ).json()
    assert full["opa_gate"]["allowed"] is False
    assert full["sarif"]["version"] == "2.1.0"
    assert full["devsecops_graph"] is not None
    assert full["devsecops_graph"]["blast_radius_summary"]["findings_overlaid"] >= 6


def test_mcp_jsonrpc_and_syncro_cli_iac_security_integration(client: TestClient, tmp_path: Path) -> None:
    tools = {t["name"]: t for t in _rpc(client, "tools/list")["result"]["tools"]}
    assert len(tools) >= 48
    expected_tools = {
        "aegis_iac_terraform_generate",
        "aegis_iac_terraform_build",
        "aegis_iac_terraform_run",
        "aegis_iac_devsecops_graph",
        "aegis_script_write_ansible",
        "aegis_script_write_helm",
        "aegis_script_write_cicd",
        "aegis_script_write_container",
        "aegis_security_mcp_status",
        "aegis_security_trivy_scan",
        "aegis_security_bandit_scan",
        "aegis_security_sast_scan",
        "aegis_security_dast_scan",
        "aegis_security_full_assessment",
    }
    assert expected_tools <= set(tools.keys())
    assert tools["aegis_security_trivy_scan"]["annotations"]["readOnlyHint"] is True
    assert tools["aegis_iac_terraform_generate"]["annotations"]["readOnlyHint"] is False

    # Call MCP Terraform generate + graph
    tf_call = _rpc(
        client,
        "tools/call",
        {
            "name": "aegis_iac_terraform_generate",
            "arguments": {"project_name": "mcp-gcp", "cloud": "gcp", "write_to_disk": False},
        },
        rid=20,
    )
    ws = json.loads(tf_call["result"]["content"][0]["text"])
    assert ws["cloud"] == "gcp"

    graph_call = _rpc(
        client,
        "tools/call",
        {"name": "aegis_iac_devsecops_graph", "arguments": {"workspace_id": ws["workspace_id"]}},
        rid=21,
    )
    g = json.loads(graph_call["result"]["content"][0]["text"])
    assert "flowchart LR" in g["mermaid"]

    # Syncro CLI smoke checks for `syncro iac` and `syncro sec`
    runner = CliRunner()
    out_tf = tmp_path / "cli-tf"
    assert runner.invoke(cli_app, ["iac", "tf-generate", "--name", "cli-demo", "--cloud", "azure", "--out", str(out_tf)]).exit_code == 0
    assert runner.invoke(cli_app, ["iac", "tf-build", "--dir", str(out_tf)]).exit_code == 0
    assert runner.invoke(cli_app, ["iac", "tf-run", "--dir", str(out_tf), "--action", "plan"]).exit_code == 0
    assert runner.invoke(cli_app, ["iac", "graph", "--dir", str(out_tf), "--format", "mermaid"]).exit_code == 0
    assert runner.invoke(cli_app, ["iac", "ansible", "--no-write"]).exit_code == 0
    assert runner.invoke(cli_app, ["iac", "helm", "--no-write"]).exit_code == 0
    assert runner.invoke(cli_app, ["iac", "cicd", "--platform", "github-actions", "--no-write"]).exit_code == 0
    assert runner.invoke(cli_app, ["iac", "container", "--no-write"]).exit_code == 0
    assert runner.invoke(cli_app, ["sec", "status"]).exit_code == 0
    assert runner.invoke(cli_app, ["sec", "trivy", "--path", str(out_tf)]).exit_code == 0
    assert runner.invoke(cli_app, ["sec", "bandit", "--path", str(out_tf)]).exit_code == 0
    assert runner.invoke(cli_app, ["sec", "sast", "--path", str(out_tf)]).exit_code == 0
    assert runner.invoke(cli_app, ["sec", "dast", "--url", "https://staging.syncro.internal", "--simulate"]).exit_code == 0
    sarif_file = tmp_path / "out.sarif"
    assert runner.invoke(cli_app, ["sec", "assess", "--path", str(out_tf), "--sarif-out", str(sarif_file)]).exit_code == 0
    assert sarif_file.exists()
