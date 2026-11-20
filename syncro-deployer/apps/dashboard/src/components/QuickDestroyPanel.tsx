import React, { useState } from "react";
import { api, type DestroyPreview, type Environment } from "../api/client";

interface Props {
  environments: Environment[];
  onDestroyed: () => void;
}

export const QuickDestroyPanel: React.FC<Props> = ({ environments, onDestroyed }) => {
  const [envId, setEnvId] = useState(environments[0]?.id ?? "env-pr-412");
  const [preview, setPreview] = useState<DestroyPreview | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [killSwitch, setKillSwitch] = useState(true);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handlePreview = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const p = await api.destroyPreview(envId);
      setPreview(p);
      setTokenInput(p.confirmation_token ?? "");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleExecute = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.destroyExecute(envId, tokenInput, killSwitch);
      setResult(r);
      onDestroyed();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Quick Destruction &amp; Emergency Kill-Switch Engine</h2>
          <span className="badge badge-danger">Two-Phase HMAC + Redis Lock</span>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="destroy-env">Target Environment</label>
            <select
              id="destroy-env"
              className="select"
              value={envId}
              onChange={(e) => setEnvId(e.target.value)}
            >
              {environments.map((env) => (
                <option key={env.id} value={env.id}>
                  [{env.cloud.toUpperCase()}] {env.id} ({env.tier} · {env.status} · ${env.hourly_cost_usd.toFixed(2)}/hr)
                </option>
              ))}
            </select>
          </div>

          <button id="btn-destroy-preview" className="btn btn-primary" disabled={busy} onClick={handlePreview}>
            1. Compute Blast Radius &amp; Mint Token
          </button>
        </div>

        {error && (
          <div className="badge badge-danger" style={{ marginTop: 12, display: "block", padding: 10 }}>
            {error}
          </div>
        )}
      </section>

      {preview && (
        <section className="grid-2">
          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">[{preview.cloud.toUpperCase()}] Blast-Radius · {preview.resource_group}</h2>
              <span className={`badge ${preview.opa_gate.allowed ? "badge-ok" : "badge-danger"}`}>
                OPA {preview.opa_gate.allowed ? "CLEARED" : "BLOCKED"}
              </span>
            </div>

            <svg
              viewBox="0 0 480 185"
              style={{ width: "100%", height: 185, background: "var(--bg-well)", borderRadius: 4, border: "1px solid var(--border-hairline)" }}
              role="img"
              aria-label="Multi-cloud resource teardown dependency graph"
            >
              <rect x="16" y="18" width="128" height="44" rx="4" fill="hsl(218,14%,14%)" stroke="hsl(188,68%,44%)" />
              <text x="80" y="38" textAnchor="middle" fill="#eef2f6" fontSize="11" fontFamily="IBM Plex Mono">{preview.cloud.toUpperCase()} Scope</text>
              <text x="80" y="52" textAnchor="middle" fill="#8b99ab" fontSize="9.5" fontFamily="IBM Plex Mono">{preview.tier.toUpperCase()}</text>

              {preview.resources.map((res, i) => {
                const y = 16 + i * 42;
                return (
                  <g key={res.id}>
                    <line x1="144" y1="40" x2="210" y2={y + 16} stroke="hsl(217,12%,34%)" strokeWidth="1.2" />
                    <rect
                      x="210"
                      y={y}
                      width="254"
                      height="32"
                      rx="4"
                      fill="hsl(218,14%,13%)"
                      stroke={res.protected ? "hsl(4,76%,56%)" : "hsl(38,86%,54%)"}
                    />
                    <text x="220" y={y + 19} fill="#eef2f6" fontSize="10.5" fontFamily="IBM Plex Mono">
                      {res.name} (${res.hourly_cost_usd.toFixed(2)}/h)
                    </text>
                  </g>
                );
              })}
            </svg>

            <div className="mono" style={{ marginTop: 12, fontSize: 12, display: "grid", gap: 4 }}>
              <div>Blast Radius: {preview.blast_radius_count} {preview.cloud.toUpperCase()} resource(s)</div>
              <div>Estimated Monthly Savings: ${preview.estimated_monthly_savings_usd.toFixed(2)}/mo</div>
              <div>Delete Protection: {preview.has_delete_lock ? `ACTIVE (${preview.lock_mechanism})` : "None"}</div>
            </div>

            {!preview.opa_gate.allowed && (
              <div style={{ marginTop: 12 }}>
                {preview.opa_gate.violations.map((v) => (
                  <div key={v} className="badge badge-danger" style={{ display: "block", marginBottom: 6, padding: 8 }}>
                    {v}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">Ordered Teardown &amp; Execution</h2>
              {preview.confirmation_token && (
                <span className="badge badge-warn">HMAC: {preview.confirmation_token}</span>
              )}
            </div>

            <ol className="mono" style={{ fontSize: 12, paddingLeft: 18, color: "var(--text-secondary)", marginTop: 0 }}>
              {preview.ordered_teardown_steps.map((s) => (
                <li key={s} style={{ marginBottom: 6 }}>{s}</li>
              ))}
            </ol>

            <div className="form-row" style={{ marginTop: 14 }}>
              <div className="field">
                <label htmlFor="hmac-token">Confirmation Token</label>
                <input
                  id="hmac-token"
                  className="input"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Run preview to mint token"
                />
              </div>
              <label className="mono" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <input type="checkbox" checked={killSwitch} onChange={(e) => setKillSwitch(e.target.checked)} />
                Kill-Switch Quarantine
              </label>
              <button
                id="btn-destroy-execute"
                className="btn btn-danger"
                disabled={busy || !preview.opa_gate.allowed || !tokenInput}
                onClick={handleExecute}
              >
                2. Execute Quick Destroy
              </button>
            </div>

            {result && (
              <pre className="code-block" style={{ marginTop: 14 }}>
                {JSON.stringify(result, null, 2)}
              </pre>
            )}
          </div>
        </section>
      )}
    </>
  );
};
