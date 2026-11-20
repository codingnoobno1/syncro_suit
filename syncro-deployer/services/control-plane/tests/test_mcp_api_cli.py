"""Tests for MCP Server JSON-RPC 2.0, FastAPI REST API, Polyglot Extension Hub, and CLI."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from aegisops.cli.main import app as cli_app


def test_mcp_jsonrpc_over_http(client: TestClient) -> None:
    init_resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}).json()
    assert init_resp["result"]["serverInfo"]["name"] == "aegisops-mcp"

    tools_resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()
    tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
    assert {"aegis_security_scan", "aegis_quick_destroy", "aegis_powershell_rbac_plan", "aegis_k8s_launch"} <= tool_names

    scan_call = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "aegis_security_scan", "arguments": {"project_id": "payments-core"}},
        },
    ).json()
    body = json.loads(scan_call["result"]["content"][0]["text"])
    assert body["project_id"] == "payments-core"
    assert body["opa_gate"]["allowed"] is True

    prompt_resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "prompts/get",
            "params": {"name": "emergency_teardown_runbook", "arguments": {"environment_id": "env-pr-412"}},
        },
    ).json()
    assert "env-pr-412" in prompt_resp["result"]["messages"][0]["content"]["text"]


def test_rest_api_and_polyglot_extensions(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200
    overview = client.get("/api/v1/overview").json()
    assert overview["projects_count"] == 4
    assert overview["extensions_connected"] == 3

    exts = client.get("/api/v1/extensions").json()
    langs = {e["language"] for e in exts}
    assert {"go", "typescript", "java"} <= langs

    hook = client.post(
        "/api/v1/extensions/go-drift-scanner/hooks",
        json={"hook_name": "drift_check", "payload": {"env": "env-pr-412"}},
    ).json()
    assert hook["allowed"] is True
    assert hook["language"] == "go"

    tf = client.post("/api/v1/infra/terraform/plan", json={"project_id": "payments-core", "environment_id": "env-pr-412"}).json()
    assert tf["status"] == "planned"
    assert tf["plan_summary"]["to_add"] >= 5

    ans = client.post("/api/v1/infra/ansible/run", json={"project_id": "payments-core"}).json()
    assert ans["status"] == "succeeded"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "aegisops_kafka_events_published_total" in metrics.text


def test_cli_commands_smoke() -> None:
    runner = CliRunner()
    assert runner.invoke(cli_app, ["version"]).exit_code == 0
    assert runner.invoke(cli_app, ["project", "list", "--json"]).exit_code == 0
    assert runner.invoke(cli_app, ["mcp", "tools"]).exit_code == 0
    assert runner.invoke(cli_app, ["broker", "health"]).exit_code == 0
    assert runner.invoke(cli_app, ["rbac", "plan"]).exit_code == 0
    assert runner.invoke(cli_app, ["destroy", "preview", "--env", "env-pr-412"]).exit_code == 0
