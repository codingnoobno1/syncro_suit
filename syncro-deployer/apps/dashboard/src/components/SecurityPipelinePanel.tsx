import React, { useState } from "react";
import { api, type ScanReport } from "../api/client";

const ALL_SCANNERS = ["checkov", "trivy", "bandit", "tfsec", "opa"];

interface Props {
  scans: ScanReport[];
  policies: Array<{ name: string; path: string; content: string }>;
  onScanComplete: () => void;
}

export const SecurityPipelinePanel: React.FC<Props> = ({ scans, policies, onScanComplete }) => {
  const [projectId, setProjectId] = useState("payments-core");
  const [targetPath, setTargetPath] = useState("infra");
  const [selected, setSelected] = useState<string[]>(ALL_SCANNERS);
  const [running, setRunning] = useState(false);
  const [activePolicy, setActivePolicy] = useState(0);
  const [latest, setLatest] = useState<ScanReport | null>(scans[0] ?? null);

  const toggleScanner = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    );
  };

  const handleScan = async () => {
    setRunning(true);
    try {
      const report = await api.runScan(projectId, targetPath || null, selected);
      setLatest(report);
      onScanComplete();
    } finally {
      setRunning(false);
    }
  };

  const shown = latest ?? scans[0] ?? null;

  return (
    <>
      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">DevSecOps Multi-Scanner &amp; OPA Gate Runner</h2>
          <span className="badge badge-steel">SARIF 2.1.0</span>
        </div>

        <div className="form-row" style={{ marginBottom: 14 }}>
          <div className="field">
            <label htmlFor="scan-project">Project ID</label>
            <input
              id="scan-project"
              className="input"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="scan-target">Target Directory</label>
            <select
              id="scan-target"
              className="select"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
            >
              <option value="infra">infra (All 3 Clouds: AWS + GCP + Azure + Ansible + IAM)</option>
              <option value="infra/terraform/aws">infra/terraform/aws (AWS EC2 IMDSv2 + VPC + KMS)</option>
              <option value="infra/terraform/gcp">infra/terraform/gcp (GCP Shielded GCE + IAP + GCS)</option>
              <option value="infra/terraform/modules">infra/terraform/modules (Azure AKS + Trusted Launch VM + KV)</option>
              <option value="deploy/k8s">deploy/k8s (Kubernetes Manifests)</option>
              <option value="services/control-plane/src">services/control-plane/src (Python SAST)</option>
            </select>
          </div>
          <button
            id="btn-run-scan"
            className="btn btn-primary"
            disabled={running || selected.length === 0}
            onClick={handleScan}
          >
            {running ? "Scanning..." : "Execute Security Pipeline"}
          </button>
        </div>

        <div className="chip-group">
          {ALL_SCANNERS.map((sc) => (
            <button
              key={sc}
              type="button"
              className={`chip ${selected.includes(sc) ? "selected" : ""}`}
              onClick={() => toggleScanner(sc)}
            >
              {selected.includes(sc) ? "✓ " : ""}{sc.toUpperCase()}
            </button>
          ))}
        </div>
      </section>

      <section className="grid-2">
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Latest Scan Verdict</h2>
            {shown && (
              <span className={`badge ${shown.opa_gate.allowed ? "badge-ok" : "badge-danger"}`}>
                OPA {shown.opa_gate.allowed ? "ALLOWED" : "DENIED"}
              </span>
            )}
          </div>
          {shown ? (
            <div style={{ display: "grid", gap: 12 }}>
              <div className="kpi-value" style={{ margin: 0 }}>
                {shown.compliance_score}%
                <span className="mono" style={{ fontSize: 12, marginLeft: 10, color: "var(--text-muted)" }}>
                  ({shown.duration_ms}ms · {shown.id})
                </span>
              </div>
              <div className="chip-group">
                {Object.entries(shown.summary).map(([sev, count]) => (
                  <span
                    key={sev}
                    className={`badge ${sev === "CRITICAL" && count > 0 ? "badge-danger" : ""}`}
                  >
                    {sev}: {count}
                  </span>
                ))}
              </div>
              {shown.findings.length === 0 ? (
                <div className="kpi-sub">Zero security misconfigurations or SAST findings detected.</div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Rule</th>
                      <th>Scanner</th>
                      <th>Finding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.findings.map((f) => (
                      <tr key={f.id}>
                        <td className="mono">{f.rule_id}</td>
                        <td><span className="badge badge-warn">{f.scanner}</span></td>
                        <td>{f.title}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ) : (
            <p className="kpi-sub">Trigger a scan above to inspect findings, OPA gate status, and SARIF output.</p>
          )}
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">OPA / Rego Policy Library</h2>
            <span className="badge">{policies.length} policies</span>
          </div>
          <div className="chip-group" style={{ marginBottom: 12 }}>
            {policies.map((pol, idx) => (
              <button
                key={pol.name}
                type="button"
                className={`chip ${activePolicy === idx ? "selected" : ""}`}
                onClick={() => setActivePolicy(idx)}
              >
                {pol.name}
              </button>
            ))}
          </div>
          <pre className="code-block">{policies[activePolicy]?.content ?? "# No Rego policies loaded"}</pre>
        </div>
      </section>
    </>
  );
};
