import React, { useState } from "react";
import { api, type CloudProvider } from "../api/client";

interface Props {
  onAction: () => void;
}

export const InfraK8sPanel: React.FC<Props> = ({ onAction }) => {
  const [cloud, setCloud] = useState<CloudProvider>("aws");
  const [tfOutput, setTfOutput] = useState<Record<string, unknown> | null>(null);
  const [ansibleOutput, setAnsibleOutput] = useState<Record<string, unknown> | null>(null);
  const [k8sOutput, setK8sOutput] = useState<Record<string, unknown> | null>(null);

  const [workloadName, setWorkloadName] = useState("edge-gateway");
  const [image, setImage] = useState("acraegis.azurecr.io/edge-gateway:1.4.2");
  const [k8sMode, setK8sMode] = useState("kustomize");

  const runTf = async () => {
    setTfOutput(await api.terraformPlan("payments-core", `env-${cloud}-412`, 4, cloud));
    onAction();
  };

  const runAnsible = async (playbook: string) => {
    setAnsibleOutput(await api.ansibleRun("payments-core", playbook));
    onAction();
  };

  const runK8s = async () => {
    setK8sOutput(
      await api.k8sLaunch({
        project_id: "edge-gateway",
        environment_id: "env-staging-edge",
        cloud,
        namespace: "aegisops",
        workload_name: workloadName,
        image,
        replicas: 2,
        mode: k8sMode,
      })
    );
    onAction();
  };

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Target Cloud Context (EKS · GKE · AKS &amp; Multi-Cloud Terraform)</h2>
          <div className="chip-group">
            {(["aws", "gcp", "azure"] as CloudProvider[]).map((c) => (
              <button key={c} type="button" className={`chip ${cloud === c ? "selected" : ""}`} onClick={() => setCloud(c)}>
                {c === "aws" ? "AWS (EC2 / EKS)" : c === "gcp" ? "GCP (GCE / GKE)" : "Azure (VM / AKS)"}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="grid-2">
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Terraform · {cloud.toUpperCase()} Landing Zone</h2>
            <button id="btn-tf-plan" className="btn btn-primary" onClick={runTf}>
              Run {cloud.toUpperCase()} Terraform Plan
            </button>
          </div>
          <p className="kpi-sub" style={{ marginTop: 0 }}>
            Composes hardened VPC/VNet, IMDSv2/Shielded/Trusted Launch Compute, KMS/Key Vault, and ephemeral TTL tags.
          </p>
          {tfOutput && <pre className="code-block">{JSON.stringify(tfOutput, null, 2)}</pre>}
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Ansible · Multi-Cloud CIS Hardening</h2>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" onClick={() => runAnsible("cis_azure_linux.yml")}>
                Run CIS Hardening
              </button>
              <button className="btn" onClick={() => runAnsible("emergency_quarantine.yml")}>
                Quarantine Playbook
              </button>
            </div>
          </div>
          <p className="kpi-sub" style={{ marginTop: 0 }}>
            Targets dynamic AWS EC2, GCP Compute, or Azure RM inventories for SSH/sysctl hardening or quarantine.
          </p>
          {ansibleOutput && <pre className="code-block">{JSON.stringify(ansibleOutput, null, 2)}</pre>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Kubernetes Workload Launcher ({cloud.toUpperCase()} · OPA Policy Gated)</h2>
          <span className="badge badge-steel">Kustomize · Helm v3 · Ephemeral Jobs</span>
        </div>

        <div className="form-row" style={{ marginBottom: 14 }}>
          <div className="field">
            <label htmlFor="k8s-name">Workload Name</label>
            <input id="k8s-name" className="input" value={workloadName} onChange={(e) => setWorkloadName(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 2 }}>
            <label htmlFor="k8s-image">Container Image (try `:latest` to test OPA deny)</label>
            <input id="k8s-image" className="input" value={image} onChange={(e) => setImage(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="k8s-mode">Launch Mode</label>
            <select id="k8s-mode" className="select" value={k8sMode} onChange={(e) => setK8sMode(e.target.value)}>
              <option value="kustomize">Deployment (Kustomize)</option>
              <option value="helm">Helm v3 Release</option>
              <option value="ephemeral-job">Ephemeral K8s Job</option>
            </select>
          </div>
          <button id="btn-k8s-launch" className="btn btn-primary" onClick={runK8s}>
            Launch on {cloud.toUpperCase()} K8s
          </button>
        </div>

        {k8sOutput && (
          <div className="grid-2">
            <pre className="code-block">{String(k8sOutput.manifest_yaml ?? "")}</pre>
            <pre className="code-block">{JSON.stringify({ cloud: k8sOutput.cloud, status: k8sOutput.status, opa_gate: k8sOutput.opa_gate, applied_resources: k8sOutput.applied_resources }, null, 2)}</pre>
          </div>
        )}
      </section>
    </div>
  );
};
