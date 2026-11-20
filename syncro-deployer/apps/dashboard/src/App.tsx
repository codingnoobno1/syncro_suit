import React, { useCallback, useEffect, useState } from "react";
import {
  api,
  type CloudEvent,
  type Environment,
  type ExtensionPlugin,
  type FinOpsSummary,
  type Project,
  type ScanReport,
} from "./api/client";
import { OverviewPanel } from "./components/OverviewPanel";
import { VmSelectorPanel } from "./components/VmSelectorPanel";
import { McpBotStudioPanel } from "./components/McpBotStudioPanel";
import { SecurityPipelinePanel } from "./components/SecurityPipelinePanel";
import { QuickDestroyPanel } from "./components/QuickDestroyPanel";
import { InfraK8sPanel } from "./components/InfraK8sPanel";
import { RbacPowerShellPanel } from "./components/RbacPowerShellPanel";
import { McpExtensionsPanel } from "./components/McpExtensionsPanel";

type TabKey = "overview" | "bot" | "vms" | "security" | "destroy" | "infra" | "rbac" | "mcp";

const NAV_ITEMS: Array<{ key: TabKey; label: string; code: string }> = [
  { key: "overview", label: "Command & FinOps", code: "01" },
  { key: "bot", label: "MCP Bot & Guardrails", code: "02" },
  { key: "vms", label: "Multi-Cloud VM Selector", code: "03" },
  { key: "security", label: "DevSecOps Pipeline", code: "04" },
  { key: "destroy", label: "Quick Destruction", code: "05" },
  { key: "infra", label: "Terraform · Ansible · K8s", code: "06" },
  { key: "rbac", label: "Multi-Cloud IAM / PS", code: "07" },
  { key: "mcp", label: "MCP Host & Extensions", code: "08" },
];

export const App: React.FC = () => {
  const [tab, setTab] = useState<TabKey>("overview");
  const [overview, setOverview] = useState<Record<string, unknown> | null>(null);
  const [finops, setFinops] = useState<FinOpsSummary | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [scans, setScans] = useState<ScanReport[]>([]);
  const [policies, setPolicies] = useState<Array<{ name: string; path: string; content: string }>>([]);
  const [extensions, setExtensions] = useState<ExtensionPlugin[]>([]);
  const [events, setEvents] = useState<CloudEvent[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [ov, fo, pr, en, sc, pol, ex, ev] = await Promise.all([
        api.overview(),
        api.finops(),
        api.projects(),
        api.environments(),
        api.scans(),
        api.opaPolicies(),
        api.extensions(),
        api.kafkaEvents(),
      ]);
      setOverview(ov);
      setFinops(fo);
      setProjects(pr);
      setEnvironments(en);
      setScans(sc);
      setPolicies(pol);
      setExtensions(ex);
      setEvents(ev);
    } catch {
      // Backend may be starting up
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/events`);
    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onmessage = () => {
      void loadAll();
    };
    return () => ws.close();
  }, [loadAll]);

  const activeNav = NAV_ITEMS.find((n) => n.key === tab) ?? NAV_ITEMS[0];

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-header">
          <div className="brand-mark">
            <div className="brand-emblem">AO</div>
            <div>
              <p className="brand-title">AegisOps</p>
              <p className="brand-subtitle">AWS · GCP · AZURE DEVSECOPS</p>
            </div>
          </div>
        </div>

        <div>
          <div className="nav-section-label">Control Plane</div>
          <nav className="nav-list">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.key}
                id={`nav-${item.key}`}
                type="button"
                className={`nav-btn ${tab === item.key ? "active" : ""}`}
                onClick={() => setTab(item.key)}
              >
                <span>{item.label}</span>
                <span className="nav-code">{item.code}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-footer">
          <div>CLOUDS: AWS · GCP · AZURE</div>
          <div>WS STREAM: {wsConnected ? "LIVE (REDIS PUB/SUB)" : "STANDBY"}</div>
          <div>FABRIC: KAFKA · RMQ · REDIS</div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <h1 className="page-title">{activeNav.label}</h1>
            <span className="page-meta">Multi-Cloud OIDC · VM Selector · OPA Guardrails</span>
          </div>
          <div className="topbar-right">
            <span className="badge badge-steel">AWS · GCP · AZURE</span>
            <span className="badge badge-ok">Tri-Broker Healthy</span>
            <button className="btn" onClick={() => void loadAll()}>
              Refresh Telemetry
            </button>
          </div>
        </header>

        <main className="workspace">
          {tab === "overview" && (
            <OverviewPanel
              overview={overview}
              finops={finops}
              projects={projects}
              environments={environments}
              onRefresh={loadAll}
            />
          )}
          {tab === "bot" && <McpBotStudioPanel onMutation={loadAll} />}
          {tab === "vms" && <VmSelectorPanel onProvisioned={loadAll} />}
          {tab === "security" && (
            <SecurityPipelinePanel scans={scans} policies={policies} onScanComplete={loadAll} />
          )}
          {tab === "destroy" && (
            <QuickDestroyPanel environments={environments} onDestroyed={loadAll} />
          )}
          {tab === "infra" && <InfraK8sPanel onAction={loadAll} />}
          {tab === "rbac" && <RbacPowerShellPanel onAction={loadAll} />}
          {tab === "mcp" && <McpExtensionsPanel extensions={extensions} onAction={loadAll} />}
        </main>

        <section className="event-stream" aria-label="Kafka CloudEvents live audit stream">
          <div className="panel-header" style={{ marginBottom: 8 }}>
            <h2 className="panel-title">Apache Kafka · Immutable CloudEvents Audit Tail</h2>
            <span className="badge">{events.length} recent events</span>
          </div>
          {events.length === 0 ? (
            <div className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
              No events published yet — select &amp; provision a VM, run a Security Scan, or trigger Quick Destroy above.
            </div>
          ) : (
            events.slice(0, 6).map((evt) => (
              <div key={evt.id} className="event-row">
                <span style={{ color: "var(--accent-steel)" }}>{evt.topic}</span>
                <span style={{ color: "var(--text-primary)" }}>{evt.type}</span>
                <span style={{ color: "var(--text-muted)" }}>
                  {evt.subject} · {evt.id}
                </span>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
};
