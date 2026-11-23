"""Comprehensive tests for Multi-Cloud CLI Wrappers (az, gcloud, aws), Guardrails, REST API & MCP."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_cloud_cli_rest_endpoints_az_gcp_aws(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert "X-Request-Id" in health.headers
    assert "X-Response-Time-Ms" in health.headers
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    hdata = health.json()
    assert hdata["mcp_tools_count"] >= 34
    assert set(hdata["cloud_clis"].keys()) == {"az", "gcloud", "aws"}

    assert client.get("/api/v1/health/live").json()["status"] == "alive"
    assert client.get("/api/v1/health/ready").json()["status"] == "ready"

    status = client.get("/api/v1/cli/status").json()
    assert status["guardrails"]["zero_shell_execution"] is True
    assert status["cloud_clis"]["az"]["mcp_tool"] == "aegis_az_cli"
    assert status["cloud_clis"]["gcloud"]["mcp_tool"] == "aegis_gcp_cli"
    assert status["cloud_clis"]["aws"]["mcp_tool"] == "aegis_aws_cli"

    presets = client.get("/api/v1/cli/presets").json()
    assert len(presets) >= 12

    az_res = client.post("/api/v1/cli/az", json={"args": ["vm", "list"]}).json()
    assert az_res["exit_code"] == 0
    assert az_res["provider"] == "az"
    assert az_res["guardrail"]["allowed"] is True
    assert len(az_res["parsed_json"]["vms"]) >= 1

    gcp_res = client.post("/api/v1/cli/gcp", json={"args": ["compute", "instances", "list"]}).json()
    assert gcp_res["exit_code"] == 0
    assert gcp_res["provider"] == "gcloud"
    assert gcp_res["parsed_json"]["instances"][0]["confidentialInstanceConfig"]["enableConfidentialCompute"] is True

    aws_res = client.post("/api/v1/cli/aws", json={"args": ["ec2", "describe-instances"], "region": "us-east-1"}).json()
    assert aws_res["exit_code"] == 0
    assert aws_res["provider"] == "aws"
    assert "--region us-east-1" in aws_res["command_preview"]
    assert len(aws_res["parsed_json"]["Reservations"]) >= 1

    history = client.get("/api/v1/cli/history").json()
    assert len(history) >= 3


def test_cloud_cli_guardrails_block_injection_secrets_and_prod_destroy(client: TestClient) -> None:
    # 1. Shell metacharacter injection blocked
    inj = client.post(
        "/api/v1/cli/exec",
        json={"provider": "aws", "args": ["sts", "get-caller-identity; rm -rf /"]},
    ).json()
    assert inj["mode"] == "blocked"
    assert inj["exit_code"] == 126
    assert inj["guardrail"]["allowed"] is False

    # 2. Disallowed namespace blocked
    ns = client.post(
        "/api/v1/cli/exec",
        json={"provider": "az", "args": ["extension", "add", "--name", "evil"]},
    ).json()
    assert ns["mode"] == "blocked"
    assert ns["guardrail"]["allowed"] is False

    # 3. Secret exfiltration blocked by default
    sec = client.post(
        "/api/v1/cli/exec",
        json={"provider": "aws", "args": ["secretsmanager", "get-secret-value", "--secret-id", "db-pass"]},
    ).json()
    assert sec["mode"] == "blocked"
    assert sec["guardrail"]["allowed"] is False

    # 4. Production destructive command strictly blocked even with allow_destructive=True
    prod_del = client.post(
        "/api/v1/cli/exec",
        json={
            "provider": "az",
            "args": ["group", "delete", "--name", "rg-aegis-payments-prod"],
            "allow_destructive": True,
        },
    ).json()
    assert prod_del["mode"] == "blocked"
    assert prod_del["guardrail"]["risk_tier"] == "destructive"

    # 5. Ephemeral dry-run delete succeeds safely in dry_run mode
    dry_del = client.post(
        "/api/v1/cli/exec",
        json={
            "provider": "gcloud",
            "args": ["compute", "instances", "delete", "gce-ephemeral-pr-99"],
            "dry_run": True,
        },
    ).json()
    assert dry_del["mode"] == "dry_run"
    assert dry_del["exit_code"] == 0
    assert dry_del["guardrail"]["allowed"] is True


def test_cloud_cli_mcp_tools_resources_and_prompt(client: TestClient) -> None:
    tools = client.post("/mcp", json={"jsonrpc": "2.0", "id": 10, "method": "tools/list"}).json()
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {
        "aegis_az_cli",
        "aegis_gcp_cli",
        "aegis_aws_cli",
        "aegis_cloud_cli_status",
        "aegis_cloud_cli_history",
    } <= names

    az_call = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "aegis_az_cli", "arguments": {"args": ["account", "show"]}},
        },
    ).json()
    az_body = json.loads(az_call["result"]["content"][0]["text"])
    assert az_body["provider"] == "az"
    assert az_body["exit_code"] == 0

    gcp_call = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "aegis_gcp_cli", "arguments": {"args": ["container", "clusters", "list"]}},
        },
    ).json()
    gcp_body = json.loads(gcp_call["result"]["content"][0]["text"])
    assert gcp_body["provider"] == "gcloud"
    assert gcp_body["exit_code"] == 0

    aws_call = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "aegis_aws_cli", "arguments": {"args": ["sts", "get-caller-identity"]}},
        },
    ).json()
    aws_body = json.loads(aws_call["result"]["content"][0]["text"])
    assert aws_body["provider"] == "aws"
    assert aws_body["exit_code"] == 0

    res_read = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 14,
            "method": "resources/read",
            "params": {"uri": "aegis://cli/status"},
        },
    ).json()
    cli_status = json.loads(res_read["result"]["contents"][0]["text"])
    assert set(cli_status["cloud_clis"].keys()) == {"az", "gcloud", "aws"}

    prompt_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 15,
            "method": "prompts/get",
            "params": {"name": "multicloud_cli_diagnostics", "arguments": {"focus": "locks"}},
        },
    ).json()
    assert "aegis_az_cli" in prompt_resp["result"]["messages"][0]["content"]["text"]
