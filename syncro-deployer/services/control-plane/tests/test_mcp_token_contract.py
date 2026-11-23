"""Token-optimisation contract of the MCP server: tool annotations + minified tool output."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _rpc(client: TestClient, method: str, params: dict | None = None, rid: int = 1) -> dict:
    payload: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload).json()


def test_tools_expose_read_only_and_destructive_annotations(client: TestClient) -> None:
    tools = {t["name"]: t for t in _rpc(client, "tools/list")["result"]["tools"]}

    assert all("annotations" in t for t in tools.values())
    assert tools["aegis_vm_compare_clouds"]["annotations"]["readOnlyHint"] is True
    assert tools["aegis_bot_read_bill"]["annotations"]["readOnlyHint"] is True
    assert tools["aegis_bot_launch_vm"]["annotations"]["readOnlyHint"] is False
    # Acts on the bill (not a pure read) and natural-language bot prompts can launch resources.
    assert tools["aegis_bot_self_prompt_save_bill"]["annotations"]["readOnlyHint"] is False
    assert tools["aegis_bot_prompt"]["annotations"]["readOnlyHint"] is False
    assert tools["aegis_quick_destroy"]["annotations"]["destructiveHint"] is True
    assert tools["aegis_preview_destroy"]["annotations"]["destructiveHint"] is False


def test_tool_results_are_minified_json(client: TestClient) -> None:
    resp = _rpc(client, "tools/call", {"name": "aegis_finops_summary", "arguments": {}}, rid=2)
    text = resp["result"]["content"][0]["text"]

    assert "\n" not in text
    parsed = json.loads(text)
    assert json.dumps(parsed, separators=(",", ":"), default=str) == text
