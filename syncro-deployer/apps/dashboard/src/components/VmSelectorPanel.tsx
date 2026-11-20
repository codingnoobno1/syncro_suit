import React, { useCallback, useEffect, useState } from "react";
import {
  api,
  type CloudProvider,
  type VmComparisonMatrix,
  type VmRecommendation,
} from "../api/client";

interface Props {
  onProvisioned: () => void;
}

const CLOUDS: CloudProvider[] = ["aws", "gcp", "azure"];
const PROFILES = [
  { key: "", label: "All Profiles" },
  { key: "general-purpose", label: "General Purpose" },
  { key: "compute-optimized", label: "Compute Optimized" },
  { key: "memory-optimized", label: "Memory Optimized" },
  { key: "confidential-sec", label: "Confidential Compute" },
  { key: "gpu-ai", label: "GPU / AI Inference" },
];

export const VmSelectorPanel: React.FC<Props> = ({ onProvisioned }) => {
  const [clouds, setClouds] = useState<CloudProvider[]>(["aws", "gcp", "azure"]);
  const [profile, setProfile] = useState("");
  const [arch, setArch] = useState("");
  const [minVcpu, setMinVcpu] = useState(4);
  const [minRam, setMinRam] = useState(16);
  const [maxBudget, setMaxBudget] = useState("");
  const [confidentialOnly, setConfidentialOnly] = useState(false);
  const [preferSpot, setPreferSpot] = useState(false);

  const [matrix, setMatrix] = useState<VmComparisonMatrix | null>(null);
  const [selected, setSelected] = useState<VmRecommendation | null>(null);
  const [envName, setEnvName] = useState("ephemeral-vm-01");
  const [ttlHours, setTtlHours] = useState(4);
  const [selectedRegion, setSelectedRegion] = useState("");
  const [provisioned, setProvisioned] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const runCompare = useCallback(async () => {
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        clouds: clouds.length > 0 ? clouds : ["aws", "gcp", "azure"],
        min_vcpu: minVcpu,
        min_memory_gib: minRam,
        require_confidential_compute: confidentialOnly,
        require_gpu: profile === "gpu-ai",
        prefer_spot: preferSpot,
      };
      if (profile) payload.workload_profile = profile;
      if (arch) payload.architecture = arch;
      if (maxBudget) payload.max_hourly_budget_usd = Number(maxBudget);

      const res = await api.vmCompare(payload);
      setMatrix(res);
      const first = res.ranked_matches[0] ?? null;
      setSelected(first);
      if (first) setSelectedRegion(first.sku.regions[0] ?? "");
    } finally {
      setBusy(false);
    }
  }, [clouds, profile, arch, minVcpu, minRam, maxBudget, confidentialOnly, preferSpot]);

  useEffect(() => {
    void runCompare();
  }, [runCompare]);

  const toggleCloud = (c: CloudProvider) => {
    setClouds((prev) =>
      prev.includes(c) ? (prev.length > 1 ? prev.filter((x) => x !== c) : prev) : [...prev, c]
    );
  };

  const handleProvision = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const res = await api.vmProvision({
        project_id: selected.sku.cloud === "gcp" ? "ai-inference" : "edge-gateway",
        environment_name: envName,
        cloud: selected.sku.cloud,
        sku: selected.sku.sku,
        region: selectedRegion || selected.sku.regions[0],
        use_spot: preferSpot,
        ttl_hours: ttlHours,
      });
      setProvisioned(res);
      onProvisioned();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Filter Controls */}
      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Intelligent Multi-Cloud VM Selector (AWS · GCP · Azure)</h2>
          <span className="badge badge-steel">19 Hardened SKUs · SEV-SNP / TDX / Nitro</span>
        </div>

        <div style={{ display: "grid", gap: 12 }}>
          <div className="chip-group">
            {CLOUDS.map((c) => (
              <button
                key={c}
                type="button"
                className={`chip ${clouds.includes(c) ? "selected" : ""}`}
                onClick={() => toggleCloud(c)}
              >
                {clouds.includes(c) ? "✓ " : ""}{c.toUpperCase()}
              </button>
            ))}
            <span style={{ width: 1, background: "var(--border-hairline)", margin: "0 4px" }} />
            {PROFILES.map((p) => (
              <button
                key={p.key || "all"}
                type="button"
                className={`chip ${profile === p.key ? "selected" : ""}`}
                onClick={() => setProfile(p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="form-row">
            <div className="field" style={{ maxWidth: 150 }}>
              <label htmlFor="vm-vcpu">Min vCPU ({minVcpu})</label>
              <select id="vm-vcpu" className="select" value={minVcpu} onChange={(e) => setMinVcpu(Number(e.target.value))}>
                <option value={2}>2+ vCPU</option>
                <option value={4}>4+ vCPU</option>
                <option value={8}>8+ vCPU</option>
              </select>
            </div>
            <div className="field" style={{ maxWidth: 160 }}>
              <label htmlFor="vm-ram">Min RAM ({minRam} GiB)</label>
              <select id="vm-ram" className="select" value={minRam} onChange={(e) => setMinRam(Number(e.target.value))}>
                <option value={4}>4+ GiB</option>
                <option value={8}>8+ GiB</option>
                <option value={16}>16+ GiB</option>
                <option value={32}>32+ GiB</option>
                <option value={64}>64+ GiB</option>
              </select>
            </div>
            <div className="field" style={{ maxWidth: 150 }}>
              <label htmlFor="vm-arch">Architecture</label>
              <select id="vm-arch" className="select" value={arch} onChange={(e) => setArch(e.target.value)}>
                <option value="">Any CPU</option>
                <option value="x86_64">x86_64 (Intel/AMD)</option>
                <option value="arm64">ARM64 (Graviton/Tau/Ampere)</option>
              </select>
            </div>
            <div className="field" style={{ maxWidth: 170 }}>
              <label htmlFor="vm-budget">Max $/hr Budget</label>
              <input
                id="vm-budget"
                className="input"
                type="number"
                step="0.05"
                placeholder="No cap"
                value={maxBudget}
                onChange={(e) => setMaxBudget(e.target.value)}
              />
            </div>
            <label className="mono" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={confidentialOnly}
                onChange={(e) => setConfidentialOnly(e.target.checked)}
              />
              Confidential Compute Only
            </label>
            <label className="mono" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={preferSpot}
                onChange={(e) => setPreferSpot(e.target.checked)}
              />
              Spot / Preemptible
            </label>
          </div>
        </div>
      </section>

      {/* Side-by-Side AWS vs GCP vs Azure Parity Cards */}
      {matrix && (
        <section className="grid-3" aria-label="Cross-cloud VM parity comparison">
          {CLOUDS.map((cloud) => {
            const best = matrix.best_by_cloud[cloud];
            const isCheapest = matrix.cheapest_cloud === cloud;
            const isTopSec = matrix.highest_security_cloud === cloud;
            return (
              <div
                key={cloud}
                className="panel"
                style={{
                  borderColor: selected?.sku.id === best?.sku.id ? "var(--accent-steel)" : undefined,
                  cursor: best ? "pointer" : "default",
                }}
                onClick={() => {
                  if (best) {
                    setSelected(best);
                    setSelectedRegion(best.sku.regions[0] ?? "");
                  }
                }}
              >
                <div className="panel-header">
                  <h3 className="panel-title">{cloud.toUpperCase()} Best Match</h3>
                  <div style={{ display: "flex", gap: 6 }}>
                    {isCheapest && <span className="badge badge-ok">Lowest Cost</span>}
                    {isTopSec && <span className="badge badge-steel">Top Security</span>}
                  </div>
                </div>
                {best ? (
                  <div style={{ display: "grid", gap: 6 }}>
                    <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>
                      {best.sku.sku}
                    </div>
                    <div className="kpi-sub">
                      {best.sku.family} · {best.sku.vcpu} vCPU / {best.sku.memory_gib} GiB ({best.sku.architecture})
                    </div>
                    <div className="kpi-value" style={{ fontSize: 22, margin: "4px 0" }}>
                      ${best.effective_monthly_usd.toFixed(2)}
                      <span className="kpi-sub" style={{ marginLeft: 6 }}>/mo (${best.effective_hourly_usd}/h)</span>
                    </div>
                    <div className="mono" style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                      Fit: {best.fit_score}/100 · Sec: {best.security_score}/100 · Spot -{best.spot_savings_pct}%
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--accent-steel)" }}>
                      {best.sku.security.confidential_tech ?? "Trusted Launch / Shielded vTPM"}
                    </div>
                  </div>
                ) : (
                  <div className="kpi-sub">No {cloud.toUpperCase()} SKU matches current filters.</div>
                )}
              </div>
            );
          })}
        </section>
      )}

      {/* Ranked Table + Terraform HCL & 1-Click Ephemeral Provisioner */}
      {matrix && (
        <section className="grid-2">
          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">Ranked Multi-Cloud Candidates</h2>
              <span className="badge">
                {matrix.ranked_matches.length} matches · Max Save ${matrix.max_monthly_savings_vs_priciest_usd}/mo
              </span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Cloud / SKU</th>
                  <th>Specs</th>
                  <th>Security</th>
                  <th>$/mo</th>
                  <th>Fit</th>
                </tr>
              </thead>
              <tbody>
                {matrix.ranked_matches.slice(0, 8).map((rec) => (
                  <tr
                    key={rec.sku.id}
                    onClick={() => {
                      setSelected(rec);
                      setSelectedRegion(rec.sku.regions[0] ?? "");
                    }}
                    style={{
                      cursor: "pointer",
                      background: selected?.sku.id === rec.sku.id ? "var(--bg-surface-alt)" : undefined,
                    }}
                  >
                    <td>
                      <span className="badge badge-steel" style={{ marginRight: 6 }}>
                        {rec.sku.cloud.toUpperCase()}
                      </span>
                      <span className="mono" style={{ fontWeight: 600 }}>{rec.sku.sku}</span>
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {rec.sku.vcpu}c / {rec.sku.memory_gib}G {rec.sku.gpu_model ? `· ${rec.sku.gpu_model}` : ""}
                    </td>
                    <td>
                      <span className={`badge ${rec.sku.security.confidential_compute ? "badge-ok" : ""}`}>
                        {rec.sku.security.confidential_compute ? "Confidential" : "Hardened"}
                      </span>
                    </td>
                    <td className="mono">${rec.effective_monthly_usd.toFixed(0)}</td>
                    <td className="mono">{rec.fit_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2 className="panel-title">
                CIS-Hardened HCL &amp; 1-Click Ephemeral Provisioner
              </h2>
              {selected && (
                <span className="badge badge-ok">
                  {selected.sku.cloud.toUpperCase()} · {selected.sku.sku}
                </span>
              )}
            </div>
            {selected ? (
              <div style={{ display: "grid", gap: 12 }}>
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="prov-name">Environment Name</label>
                    <input
                      id="prov-name"
                      className="input"
                      value={envName}
                      onChange={(e) => setEnvName(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="prov-region">Region</label>
                    <select
                      id="prov-region"
                      className="select"
                      value={selectedRegion}
                      onChange={(e) => setSelectedRegion(e.target.value)}
                    >
                      {selected.sku.regions.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field" style={{ maxWidth: 100 }}>
                    <label htmlFor="prov-ttl">TTL (hrs)</label>
                    <input
                      id="prov-ttl"
                      className="input"
                      type="number"
                      min={1}
                      max={24}
                      value={ttlHours}
                      onChange={(e) => setTtlHours(Number(e.target.value))}
                    />
                  </div>
                  <button
                    id="btn-vm-provision"
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={handleProvision}
                  >
                    Provision Ephemeral VM
                  </button>
                </div>

                <pre className="code-block">{selected.terraform_snippet}</pre>

                {provisioned && (
                  <div className="badge badge-ok" style={{ padding: 10, display: "block" }}>
                    Provisioned on {selected.sku.cloud.toUpperCase()} · Env ID:{" "}
                    {String((provisioned.environment as Record<string, unknown>)?.id ?? "")} · Job:{" "}
                    {String(provisioned.job_id ?? "")} (Now visible in Quick Destruction &amp; FinOps)
                  </div>
                )}
              </div>
            ) : (
              <div className="kpi-sub">Adjust filters to select a VM SKU.</div>
            )}
          </div>
        </section>
      )}
    </div>
  );
};
