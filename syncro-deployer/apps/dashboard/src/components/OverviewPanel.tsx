import React, { useState } from "react";
import { api, type Environment, type FinOpsSummary, type Project } from "../api/client";

interface Props {
  overview: Record<string, unknown> | null;
  finops: FinOpsSummary | null;
  projects: Project[];
  environments: Environment[];
  onRefresh: () => void;
}

export const OverviewPanel: React.FC<Props> = ({ overview, finops, projects, environments, onRefresh }) => {
  const [driftMsg, setDriftMsg] = useState<string | null>(null);
  const brokers = (overview?.brokers as Record<string, Record<string, unknown>> | undefined) ?? {};
  const kafka = brokers.kafka ?? {};
  const rabbitmq = brokers.rabbitmq ?? {};
  const redis = brokers.redis ?? {};

  const runDrift = async (envId: string) => {
    const res = await api.driftCheck(envId);
    setDriftMsg(
      `[Go Drift Scanner] ${envId} (${String(res.cloud).toUpperCase()}): ${String(res.total_resources)} resources verified, ${String(res.drifted_count)} drifted.`
    );
    onRefresh();
  };

  return (
    <>
      <section className="kpi-strip" aria-label="Multi-Cloud platform telemetry summary">
        <div className="panel">
          <div className="kpi-label">Active Environments</div>
          <div className="kpi-value">{String(overview?.active_environments ?? environments.length)}</div>
          <div className="kpi-sub">
            {String(overview?.ephemeral_environments ?? 4)} ephemeral across AWS · GCP · Azure
          </div>
        </div>
        <div className="panel">
          <div className="kpi-label">Multi-Cloud Burn Rate</div>
          <div className="kpi-value">${String(finops?.total_hourly_usd ?? overview?.hourly_multicloud_burn_usd ?? "21.74")}/hr</div>
          <div className="kpi-sub">
            Reclaimable ephemeral: ${finops?.total_ephemeral_reclaimable_monthly_usd.toFixed(0) ?? "5248"}/mo
          </div>
        </div>
        <div className="panel">
          <div className="kpi-label">Avg Compliance Score</div>
          <div className="kpi-value">{String(overview?.avg_compliance_score ?? 97.8)}%</div>
          <div className="kpi-sub">CIS AWS · GCP · Azure + OPA Rego</div>
        </div>
        <div className="panel">
          <div className="kpi-label">VM Catalog &amp; Extensions</div>
          <div className="kpi-value">{String(overview?.vm_catalog_count ?? 19)} SKUs</div>
          <div className="kpi-sub">Go · TypeScript · Java 17 mesh active</div>
        </div>
      </section>

      {/* Multi-Cloud FinOps Breakdown */}
      {finops && (
        <section className="grid-3" aria-label="FinOps breakdown by cloud provider">
          {finops.by_cloud.map((b) => (
            <div key={b.cloud} className="panel">
              <div className="panel-header">
                <h2 className="panel-title">{b.cloud.toUpperCase()} · FinOps &amp; Posture</h2>
                <span className="badge badge-steel">{b.active_environments} active</span>
              </div>
              <div className="kpi-value" style={{ fontSize: 22 }}>
                ${b.hourly_burn_usd.toFixed(2)}/hr
              </div>
              <div className="mono" style={{ fontSize: 12, color: "var(--text-secondary)", display: "grid", gap: 4 }}>
                <div>Projected Monthly: ${b.monthly_projected_usd.toFixed(2)}</div>
                <div style={{ color: "var(--status-ok)" }}>
                  Ephemeral Reclaimable: ${b.ephemeral_reclaimable_monthly_usd.toFixed(2)}/mo
                </div>
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Tri-Broker Fabric */}
      <section className="grid-3" aria-label="Tri-Broker Messaging Fabric">
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Apache Kafka · Audit Stream</h2>
            <span className="badge badge-ok">{String(kafka.status ?? "healthy")}</span>
          </div>
          <div className="mono" style={{ fontSize: 12, display: "grid", gap: 5 }}>
            <div>Mode: {String(kafka.mode ?? "memory")}</div>
            <div>Published Events: {String(kafka.total_published ?? 0)}</div>
            <div>Topics: audit · security · infra · destroy</div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">RabbitMQ · Async Job Lanes</h2>
            <span className="badge badge-ok">{String(rabbitmq.status ?? "healthy")}</span>
          </div>
          <div className="mono" style={{ fontSize: 12, display: "grid", gap: 5 }}>
            <div>Total Jobs: {String(rabbitmq.total_jobs ?? 0)}</div>
            <div>Succeeded: {String(rabbitmq.succeeded_jobs ?? 0)}</div>
            <div>DLQ Depth: {String((rabbitmq.queued_by_lane as Record<string, number> | undefined)?.["jobs.dlq"] ?? 0)}</div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Redis · Locks, TTL &amp; Pub/Sub</h2>
            <span className="badge badge-ok">{String(redis.status ?? "healthy")}</span>
          </div>
          <div className="mono" style={{ fontSize: 12, display: "grid", gap: 5 }}>
            <div>Cached/TTL Keys: {String(redis.cached_keys ?? 0)}</div>
            <div>Pub/Sub Fanouts: {String(redis.pubsub_messages_published ?? 0)}</div>
            <div>Active Locks: {Array.isArray(redis.active_locks) ? redis.active_locks.length : 0}</div>
          </div>
        </div>
      </section>

      <section className="grid-2">
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Multi-Cloud Environments &amp; Go Drift Check</h2>
            <span className="badge">{environments.length} workspaces</span>
          </div>
          {driftMsg && (
            <div className="badge badge-ok" style={{ display: "block", padding: 8, marginBottom: 10 }}>
              {driftMsg}
            </div>
          )}
          <table className="data-table">
            <thead>
              <tr>
                <th>Cloud / Env</th>
                <th>VM SKU</th>
                <th>Tier</th>
                <th>Burn</th>
                <th>Drift</th>
              </tr>
            </thead>
            <tbody>
              {environments.map((env) => (
                <tr key={env.id}>
                  <td>
                    <span className="badge badge-steel" style={{ marginRight: 6 }}>{env.cloud.toUpperCase()}</span>
                    <span className="mono">{env.id}</span>
                  </td>
                  <td className="mono" style={{ fontSize: 11.5 }}>{env.vm_sku ?? "managed-k8s"}</td>
                  <td>
                    <span className={`badge ${env.tier === "production" ? "badge-danger" : "badge-warn"}`}>
                      {env.tier}
                    </span>
                  </td>
                  <td className="mono">${env.hourly_cost_usd.toFixed(2)}/h</td>
                  <td>
                    <button className="btn" style={{ padding: "4px 8px", fontSize: 11 }} onClick={() => void runDrift(env.id)}>
                      Check
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Multi-Project Polyglot Registry</h2>
            <span className="badge badge-steel">{projects.length} repos</span>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Stack</th>
                <th>Clouds</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{p.name}</div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{p.repository}</div>
                  </td>
                  <td><span className="badge">{p.primary_language}</span></td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {(p.target_clouds ?? ["azure"]).map((c) => c.toUpperCase()).join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
};
