import React, { useState } from "react";
import { api, type CloudProvider } from "../api/client";

interface Props {
  onAction: () => void;
}

export const RbacPowerShellPanel: React.FC<Props> = ({ onAction }) => {
  const [cloud, setCloud] = useState<CloudProvider>("azure");
  const [rg, setRg] = useState("rg-aegis-payments-pr-412");
  const [principal, setPrincipal] = useState("7b8f12c0-4a91-4d30-9f1a-000000000101");
  const [pimHours, setPimHours] = useState(1);
  const [personas, setPersonas] = useState<string[]>(["auditor", "deployer", "destroyer"]);
  const [overrideRole, setOverrideRole] = useState("");
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);

  const switchCloud = (c: CloudProvider) => {
    setCloud(c);
    if (c === "aws") {
      setRg("aws-stack-edge-pr-501");
      setPrincipal("aegis-oidc-deployer-role");
    } else if (c === "gcp") {
      setRg("gcp-proj-ai-pr-608");
      setPrincipal("aegis-wif-deployer");
    } else {
      setRg("rg-aegis-payments-pr-412");
      setPrincipal("7b8f12c0-4a91-4d30-9f1a-000000000101");
    }
  };

  const togglePersona = (p: string) => {
    setPersonas((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  };

  const generate = async () => {
    const res = await api.rbacPlan({
      cloud,
      resource_group: rg,
      principal_object_id: principal,
      personas,
      pim_max_duration_hours: pimHours,
      requested_role_override: overrideRole || null,
    });
    setPlan(res);
    onAction();
  };

  const gate = plan?.opa_gate as { allowed: boolean; violations: string[] } | undefined;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Multi-Cloud Least-Privilege IAM &amp; PowerShell ABAC Planner</h2>
          <span className="badge badge-steel">Azure PowerShell · AWS IAM ABAC · GCP CEL</span>
        </div>

        <div className="chip-group" style={{ marginBottom: 14 }}>
          {(["azure", "aws", "gcp"] as CloudProvider[]).map((c) => (
            <button
              key={c}
              type="button"
              className={`chip ${cloud === c ? "selected" : ""}`}
              onClick={() => switchCloud(c)}
            >
              {c === "azure" ? "Azure (PowerShell ABAC)" : c === "aws" ? "AWS (IAM Tag ABAC)" : "GCP (gcloud CEL)"}
            </button>
          ))}
        </div>

        <div className="form-row" style={{ marginBottom: 14 }}>
          <div className="field">
            <label htmlFor="rbac-rg">Target Scope / RG / Stack</label>
            <input id="rbac-rg" className="input" value={rg} onChange={(e) => setRg(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="rbac-principal">Identity / Role / Principal ID</label>
            <input id="rbac-principal" className="input" value={principal} onChange={(e) => setPrincipal(e.target.value)} />
          </div>
          <div className="field" style={{ maxWidth: 150 }}>
            <label htmlFor="rbac-pim">JIT / PIM Hours ({pimHours}h)</label>
            <input
              id="rbac-pim"
              className="input"
              type="number"
              min={1}
              max={8}
              value={pimHours}
              onChange={(e) => setPimHours(Number(e.target.value))}
            />
          </div>
          <div className="field" style={{ maxWidth: 210 }}>
            <label htmlFor="rbac-override">Role Override (test OPA deny)</label>
            <input
              id="rbac-override"
              className="input"
              placeholder="Owner / AdministratorAccess"
              value={overrideRole}
              onChange={(e) => setOverrideRole(e.target.value)}
            />
          </div>
          <button id="btn-rbac-plan" className="btn btn-primary" onClick={generate}>
            Generate {cloud.toUpperCase()} IAM Plan
          </button>
        </div>

        <div className="chip-group">
          {["auditor", "deployer", "destroyer"].map((p) => (
            <button
              key={p}
              type="button"
              className={`chip ${personas.includes(p) ? "selected" : ""}`}
              onClick={() => togglePersona(p)}
            >
              {personas.includes(p) ? "✓ " : ""}{p.toUpperCase()}
            </button>
          ))}
        </div>
      </section>

      {plan && (
        <section className="grid-2">
          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">Generated {cloud.toUpperCase()} Execution Script</h2>
              {gate && (
                <span className={`badge ${gate.allowed ? "badge-ok" : "badge-danger"}`}>
                  OPA {gate.allowed ? "LEAST-PRIVILEGE OK" : "POLICY VIOLATION"}
                </span>
              )}
            </div>
            {gate && !gate.allowed && (
              <div style={{ marginBottom: 12 }}>
                {gate.violations.map((v) => (
                  <div key={v} className="badge badge-danger" style={{ display: "block", marginBottom: 6, padding: 8 }}>
                    {v}
                  </div>
                ))}
              </div>
            )}
            <pre className="code-block">{String(plan.powershell_script ?? "")}</pre>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">ABAC / CEL Conditions &amp; Dry-Run Command</h2>
            </div>
            <pre className="code-block" style={{ marginBottom: 12 }}>{String(plan.what_if_command ?? "")}</pre>
            <pre className="code-block">{JSON.stringify(plan.assignments, null, 2)}</pre>
          </div>
        </section>
      )}
    </div>
  );
};
