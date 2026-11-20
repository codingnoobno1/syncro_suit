import React, { useState } from "react";
import { api, type ExtensionPlugin } from "../api/client";

interface Props {
  extensions: ExtensionPlugin[];
  onAction: () => void;
}

export const McpExtensionsPanel: React.FC<Props> = ({ extensions, onAction }) => {
  const [mcpMethod, setMcpMethod] = useState("tools/list");
  const [toolName, setToolName] = useState("aegis_broker_health");
  const [mcpResp, setMcpResp] = useState<Record<string, unknown> | null>(null);
  const [extResp, setExtResp] = useState<Record<string, unknown> | null>(null);

  const sendMcp = async () => {
    const body =
      mcpMethod === "tools/call"
        ? { jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: { name: toolName, arguments: toolName === "aegis_security_scan" ? { project_id: "payments-core" } : {} } }
        : { jsonrpc: "2.0", id: Date.now(), method: mcpMethod };
    setMcpResp(await api.mcpCall(body));
    onAction();
  };

  const invokeExt = async (id: string) => {
    setExtResp(await api.invokeExtension(id, "drift_check", { environment_id: "env-pr-412" }));
    onAction();
  };

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Polyglot Extension Mesh (Go · TypeScript · Java 17)</h2>
          <span className="badge badge-steel">Protobuf v3 + CloudEvents 1.0</span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Extension</th>
              <th>Language</th>
              <th>Transport</th>
              <th>Capabilities</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {extensions.map((ext) => (
              <tr key={ext.id}>
                <td>
                  <div style={{ fontWeight: 600 }}>{ext.name}</div>
                  <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{ext.endpoint}</div>
                </td>
                <td><span className="badge badge-steel">{ext.language.toUpperCase()}</span></td>
                <td className="mono">{ext.transport}</td>
                <td className="mono" style={{ fontSize: 12 }}>{ext.capabilities.join(", ")}</td>
                <td>
                  <button className="btn" onClick={() => invokeExt(ext.id)}>Invoke Hook</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {extResp && <pre className="code-block" style={{ marginTop: 14 }}>{JSON.stringify(extResp, null, 2)}</pre>}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Model Context Protocol (MCP) Live JSON-RPC 2.0 Host</h2>
          <span className="badge badge-ok">POST /mcp · stdio ready</span>
        </div>

        <div className="form-row" style={{ marginBottom: 14 }}>
          <div className="field">
            <label htmlFor="mcp-method">JSON-RPC Method</label>
            <select id="mcp-method" className="select" value={mcpMethod} onChange={(e) => setMcpMethod(e.target.value)}>
              <option value="initialize">initialize</option>
              <option value="tools/list">tools/list</option>
              <option value="resources/list">resources/list</option>
              <option value="prompts/list">prompts/list</option>
              <option value="tools/call">tools/call</option>
            </select>
          </div>
          {mcpMethod === "tools/call" && (
            <div className="field">
              <label htmlFor="mcp-tool">MCP Tool</label>
              <select id="mcp-tool" className="select" value={toolName} onChange={(e) => setToolName(e.target.value)}>
                <option value="aegis_broker_health">aegis_broker_health</option>
                <option value="aegis_list_projects">aegis_list_projects</option>
                <option value="aegis_security_scan">aegis_security_scan</option>
              </select>
            </div>
          )}
          <button id="btn-mcp-send" className="btn btn-primary" onClick={sendMcp}>
            Send MCP JSON-RPC Request
          </button>
        </div>

        {mcpResp && <pre className="code-block">{JSON.stringify(mcpResp, null, 2)}</pre>}
      </section>
    </div>
  );
};
