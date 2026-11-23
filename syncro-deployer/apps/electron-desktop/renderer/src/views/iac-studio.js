import { api } from '../api/client.js';
import { cloudTag, esc, exportOrCopy, prettyJson, statusTag } from '../utils/format.js';

let activeTab = 'terraform'; // terraform | scripts | graph | security-mcp
let lastTfBundle = null;
let lastTfBuild = null;
let lastTfRun = null;
let selectedTfFileIdx = 0;

let lastScriptBundle = null;
let selectedScriptFileIdx = 0;

let lastGraph = null;
let graphFormat = 'svg'; // svg | mermaid | dot | ascii

let lastAssessment = null;
let secTargetPath = '';
let secTargetUrl = 'http://127.0.0.1:8080/api/v1/health';

const RISK_COLORS = {
  ok: { fill: '#0f2922', stroke: '#22c55e', text: '#86efac' },
  low: { fill: '#17253a', stroke: '#38bdf8', text: '#bae6fd' },
  medium: { fill: '#33260f', stroke: '#f59e0b', text: '#fde68a' },
  high: { fill: '#3b1818', stroke: '#f97316', text: '#fed7aa' },
  critical: { fill: '#450a0a', stroke: '#ef4444', text: '#fecaca' },
};

function renderInteractiveSvgGraph(graph) {
  if (!graph || !Array.isArray(graph.nodes) || graph.nodes.length === 0) {
    return '<div class="panel-meta">Generate or run Terraform to render the interactive DevSecOps dependency &amp; security graph.</div>';
  }
  const layers = graph.layers && graph.layers.length > 0 ? graph.layers : ['cicd', 'security', 'network', 'compute', 'data'];
  const colW = 215;
  const rowH = 74;
  const padX = 20;
  const padY = 44;

  const grouped = new Map();
  for (const l of layers) grouped.set(l, []);
  for (const n of graph.nodes) {
    if (!grouped.has(n.layer)) grouped.set(n.layer, []);
    grouped.get(n.layer).push(n);
  }

  const activeLayers = Array.from(grouped.entries()).filter(([, arr]) => arr.length > 0);
  const maxRows = Math.max(1, ...activeLayers.map(([, arr]) => arr.length));
  const width = Math.max(820, padX * 2 + activeLayers.length * colW);
  const height = Math.max(260, padY + maxRows * rowH + 30);

  const pos = new Map();
  let layerBoxes = '';
  let nodeShapes = '';

  activeLayers.forEach(([layerName, nodes], colIdx) => {
    const x = padX + colIdx * colW;
    layerBoxes += `
      <rect x="${x - 8}" y="12" width="${colW - 18}" height="${height - 22}" rx="8" fill="rgba(148,163,184,0.05)" stroke="rgba(148,163,184,0.16)" stroke-dasharray="4 3" />
      <text x="${x + 4}" y="29" fill="#94a3b8" font-size="10" font-family="IBM Plex Mono, monospace" font-weight="600">${esc(layerName.toUpperCase())}</text>
    `;
    nodes.forEach((n, rowIdx) => {
      const nx = x;
      const ny = padY + rowIdx * rowH;
      const nw = colW - 34;
      const nh = 54;
      pos.set(n.id, { cx: nx + nw / 2, cy: ny + nh / 2, left: nx, right: nx + nw, top: ny, bottom: ny + nh });
      const palette = RISK_COLORS[n.risk_level] || RISK_COLORS.ok;
      const shortTitle = (n.label || n.id).split('\n')[0].slice(0, 22);
      const subTitle = ((n.label || '').split('\n')[1] || n.kind || '').slice(0, 24);
      nodeShapes += `
        <g class="graph-node" data-graph-node="${esc(n.id)}" style="cursor:pointer">
          <rect x="${nx}" y="${ny}" width="${nw}" height="${nh}" rx="6" fill="${palette.fill}" stroke="${palette.stroke}" stroke-width="${n.risk_level === 'critical' ? 2.2 : 1.4}" />
          <text x="${nx + 8}" y="${ny + 20}" fill="#f8fafc" font-size="11" font-family="IBM Plex Mono, monospace" font-weight="600">${esc(shortTitle)}</text>
          <text x="${nx + 8}" y="${ny + 36}" fill="${palette.text}" font-size="9.5" font-family="IBM Plex Sans, sans-serif">${esc(subTitle)}${n.findings_count > 0 ? ` · ${n.findings_count}f` : ''}</text>
          <text x="${nx + nw - 8}" y="${ny + 48}" text-anchor="end" fill="${palette.stroke}" font-size="8.5" font-family="IBM Plex Mono, monospace">${esc((n.risk_level || 'ok').toUpperCase())}</text>
        </g>
      `;
    });
  });

  let edgePaths = '';
  for (const e of graph.edges || []) {
    const a = pos.get(e.source);
    const b = pos.get(e.target);
    if (!a || !b) continue;
    const x1 = a.right;
    const y1 = a.cy;
    const x2 = b.left;
    const y2 = b.cy;
    const midX = (x1 + x2) / 2;
    edgePaths += `<path d="M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}" fill="none" stroke="rgba(56,189,248,0.45)" stroke-width="1.35" marker-end="url(#syncro-arrow)" />`;
  }

  return `
    <div style="overflow:auto; border:1px solid var(--border-subtle); border-radius:8px; background:#090d14; padding:6px">
      <svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="DevSecOps Architecture Graph">
        <defs>
          <marker id="syncro-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#38bdf8" />
          </marker>
        </defs>
        ${layerBoxes}
        ${edgePaths}
        ${nodeShapes}
      </svg>
    </div>
  `;
}

export async function renderIacStudio(container, ctx) {
  const [workspaces, bundles, secStatus] = await Promise.all([
    api.iacWorkspaces().catch(() => []),
    api.scriptBundles().catch(() => []),
    api.securityMcpStatus().catch(() => ({ scanners: {} })),
  ]);

  if (!lastTfBundle && workspaces.length > 0) lastTfBundle = workspaces[workspaces.length - 1];
  if (!lastScriptBundle && bundles.length > 0) lastScriptBundle = bundles[bundles.length - 1];

  const activeTfFile = lastTfBundle?.files?.[selectedTfFileIdx] || lastTfBundle?.files?.[0] || null;
  const activeScriptFile = lastScriptBundle?.files?.[selectedScriptFileIdx] || lastScriptBundle?.files?.[0] || null;

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>IaC Terraform Studio, Script Writers &amp; Security MCP</h1>
        <p class="view-subtitle">
          Generate, build &amp; run hardened Terraform HCL, render DevSecOps architecture graphs, author Ansible / Helm / CI-CD / Dockerfiles, and run Trivy · Bandit · SAST · DAST MCP assessments.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn ${activeTab === 'terraform' ? 'btn-primary' : ''}" data-iac-tab="terraform">Terraform Studio</button>
        <button type="button" class="btn ${activeTab === 'scripts' ? 'btn-primary' : ''}" data-iac-tab="scripts">Script Writers</button>
        <button type="button" class="btn ${activeTab === 'graph' ? 'btn-primary' : ''}" data-iac-tab="graph">DevSecOps Graph</button>
        <button type="button" class="btn ${activeTab === 'security-mcp' ? 'btn-primary' : ''}" data-iac-tab="security-mcp">Security MCP</button>
        <button type="button" class="btn" id="btn-iac-popout">Pop Out</button>
      </div>
    </div>

    ${
      activeTab === 'terraform'
        ? `
          <div class="split-2">
            <section class="panel">
              <div class="panel-head">
                <h2 class="panel-title">1. Generate Multi-Cloud Terraform HCL</h2>
                <span class="panel-meta">${workspaces.length} workspace(s)</span>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label for="tf-name">Project / Stack Name</label>
                  <input id="tf-name" class="input" value="${esc(lastTfBundle?.project_name || 'syncro-edge-prod')}" />
                </div>
                <div class="field">
                  <label for="tf-cloud">Cloud Provider</label>
                  <select id="tf-cloud" class="select">
                    <option value="aws" ${lastTfBundle?.cloud === 'aws' ? 'selected' : ''}>AWS (VPC + EKS/EC2 + KMS + WAF)</option>
                    <option value="gcp" ${lastTfBundle?.cloud === 'gcp' ? 'selected' : ''}>GCP (VPC + Shielded SEV-SNP + CMEK)</option>
                    <option value="azure" ${lastTfBundle?.cloud === 'azure' ? 'selected' : ''}>Azure (VNet + Private AKS + Key Vault)</option>
                  </select>
                </div>
                <div class="field">
                  <label for="tf-blueprint">Blueprint</label>
                  <select id="tf-blueprint" class="select">
                    <option value="vpc-k8s">VPC + Hardened Kubernetes</option>
                    <option value="hardened-vm">Hardened Confidential VM</option>
                    <option value="zero-trust-mesh">Zero-Trust Service Mesh</option>
                    <option value="data-platform">Encrypted Data Platform</option>
                  </select>
                </div>
                <div class="field">
                  <label for="tf-env">Environment</label>
                  <select id="tf-env" class="select">
                    <option value="staging">staging</option>
                    <option value="ephemeral">ephemeral</option>
                    <option value="production">production (destroy-locked)</option>
                  </select>
                </div>
              </div>
              <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px">
                <button type="button" class="btn btn-primary" id="btn-tf-gen">Generate HCL</button>
                <button type="button" class="btn" id="btn-tf-build">Build &amp; Validate</button>
                <button type="button" class="btn" id="btn-tf-plan">Run Plan (Dry-Run)</button>
                <button type="button" class="btn" id="btn-tf-apply">Run Apply (Guardrailed)</button>
                <button type="button" class="btn" id="btn-tf-graph">Open Graph</button>
              </div>
              ${
                lastTfBundle
                  ? `
                    <div style="margin-top:12px; display:flex; gap:6px; flex-wrap:wrap; align-items:center">
                      ${cloudTag(lastTfBundle.cloud)}
                      <span class="tag">${esc(lastTfBundle.workspace_id)}</span>
                      <span class="tag">${lastTfBundle.resources?.length || 0} resources</span>
                      <span class="tag">~$${Number(lastTfBundle.estimated_monthly_usd || 0).toFixed(0)}/mo</span>
                    </div>
                  `
                  : ''
              }
            </section>

            <section class="panel">
              <div class="panel-head">
                <h2 class="panel-title">2. Build &amp; Run Output</h2>
                ${
                  lastTfRun
                    ? statusTag(lastTfRun.guardrail_allowed ? 'ok' : 'blocked')
                    : lastTfBuild
                      ? statusTag(lastTfBuild.validate_ok ? 'ok' : 'failed')
                      : '<span class="panel-meta">Idle</span>'
                }
              </div>
              <div class="terminal-box">
                <div class="terminal-bar">
                  <span>Engine: ${esc(lastTfRun?.engine || lastTfBuild?.engine || 'terraform-studio')}</span>
                  <span class="mono">${esc(lastTfRun?.status || (lastTfBuild?.validate_ok ? 'validated' : 'ready'))}</span>
                </div>
                <pre class="terminal-pre">${esc(
                  lastTfRun
                    ? prettyJson({
                        action: lastTfRun.action,
                        status: lastTfRun.status,
                        guardrail_allowed: lastTfRun.guardrail_allowed,
                        applied_resources: lastTfRun.applied_resources,
                        outputs: lastTfRun.outputs,
                        graph_security_score: lastTfRun.devsecops_graph?.security_score,
                        stdout: lastTfRun.stdout,
                      })
                    : lastTfBuild
                      ? prettyJson(lastTfBuild)
                      : 'Click "Generate HCL", then "Build & Validate" and "Run Plan / Apply".'
                )}</pre>
              </div>
            </section>
          </div>

          <section class="panel">
            <div class="panel-head">
              <h2 class="panel-title">Generated Terraform Workspace Files</h2>
              <div style="display:flex; gap:6px; flex-wrap:wrap">
                ${(lastTfBundle?.files || [])
                  .map(
                    (f, idx) =>
                      `<button type="button" class="btn btn-xs ${idx === selectedTfFileIdx ? 'btn-primary' : ''}" data-tf-file="${idx}">${esc(f.path)}</button>`
                  )
                  .join('')}
                ${activeTfFile ? `<button type="button" class="btn btn-xs" id="btn-tf-export">Save / Copy File</button>` : ''}
              </div>
            </div>
            <div class="terminal-box">
              <pre class="terminal-pre" style="max-height:360px">${esc(
                activeTfFile ? activeTfFile.content : '# Generate a Terraform workspace above to inspect providers.tf, security.tf, main.tf, variables.tf, and outputs.tf'
              )}</pre>
            </div>
          </section>
        `
        : ''
    }

    ${
      activeTab === 'scripts'
        ? `
          <div class="split-2">
            <section class="panel">
              <div class="panel-head">
                <h2 class="panel-title">DevOps Script &amp; Pipeline Writers</h2>
                <span class="panel-meta">${bundles.length} bundle(s)</span>
              </div>
              <div class="field-grid">
                <div class="field">
                  <label for="sw-name">Service / Chart / Project Name</label>
                  <input id="sw-name" class="input" value="${esc(lastScriptBundle?.name || 'syncro-payments')}" />
                </div>
                <div class="field">
                  <label for="sw-cloud">Target Cloud</label>
                  <select id="sw-cloud" class="select">
                    <option value="aws">AWS</option>
                    <option value="gcp">GCP</option>
                    <option value="azure">Azure</option>
                  </select>
                </div>
                <div class="field">
                  <label for="sw-cicd">CI/CD Platform</label>
                  <select id="sw-cicd" class="select">
                    <option value="github-actions">GitHub Actions (Syncro CLI + SARIF)</option>
                    <option value="gitlab-ci">GitLab CI</option>
                    <option value="azure-devops">Azure DevOps Pipelines</option>
                    <option value="jenkins">Jenkinsfile</option>
                  </select>
                </div>
                <div class="field">
                  <label for="sw-lang">Runtime / Hardening Language</label>
                  <select id="sw-lang" class="select">
                    <option value="python">Python 3.12</option>
                    <option value="node">Node.js 22</option>
                    <option value="go">Go 1.23 (Distroless)</option>
                    <option value="java">Java 21</option>
                  </select>
                </div>
              </div>
              <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px">
                <button type="button" class="btn btn-primary" id="btn-sw-ansible">Write Ansible Playbook</button>
                <button type="button" class="btn btn-primary" id="btn-sw-helm">Write Helm v3 Chart</button>
                <button type="button" class="btn btn-primary" id="btn-sw-cicd">Write CI/CD Pipeline</button>
                <button type="button" class="btn" id="btn-sw-container">Write Hardened Dockerfile</button>
              </div>
              ${
                lastScriptBundle
                  ? `
                    <div style="margin-top:12px">
                      <div class="panel-meta" style="margin-bottom:6px">Security Controls Enforced:</div>
                      <div style="display:flex; gap:5px; flex-wrap:wrap">
                        ${(lastScriptBundle.security_controls || []).map((c) => `<span class="tag">${esc(c)}</span>`).join('')}
                      </div>
                    </div>
                  `
                  : ''
              }
            </section>

            <section class="panel">
              <div class="panel-head">
                <h2 class="panel-title">Generated Files (${esc(lastScriptBundle?.kind || 'none')})</h2>
                ${activeScriptFile ? `<button type="button" class="btn btn-xs" id="btn-sw-export">Save / Copy</button>` : ''}
              </div>
              <div style="display:flex; gap:5px; flex-wrap:wrap; margin-bottom:8px">
                ${(lastScriptBundle?.files || [])
                  .map(
                    (f, idx) =>
                      `<button type="button" class="btn btn-xs ${idx === selectedScriptFileIdx ? 'btn-primary' : ''}" data-sw-file="${idx}">${esc(f.path)}</button>`
                  )
                  .join('')}
              </div>
              <div class="terminal-box">
                <pre class="terminal-pre" style="max-height:420px">${esc(
                  activeScriptFile ? activeScriptFile.content : '# Choose Ansible, Helm Chart, CI/CD Pipeline, or Hardened Container to generate validated DevOps artifacts.'
                )}</pre>
              </div>
            </section>
          </div>
        `
        : ''
    }

    ${
      activeTab === 'graph'
        ? `
          <section class="panel">
            <div class="panel-head">
              <div>
                <h2 class="panel-title">DevSecOps Architecture &amp; Security Dependency Graph</h2>
                <span class="panel-meta">
                  ${
                    lastGraph
                      ? `${lastGraph.nodes?.length || 0} nodes · ${lastGraph.edges?.length || 0} edges · Security Score: ${lastGraph.security_score}/100 (click any node to inspect)`
                      : 'Build graph from active Terraform workspace or repository infra/terraform'
                  }
                </span>
              </div>
              <div style="display:flex; gap:6px; flex-wrap:wrap">
                <button type="button" class="btn btn-xs btn-primary" id="btn-graph-refresh">Build / Refresh Graph</button>
                <button type="button" class="btn btn-xs ${graphFormat === 'svg' ? 'btn-primary' : ''}" data-gfmt="svg">Interactive SVG</button>
                <button type="button" class="btn btn-xs ${graphFormat === 'mermaid' ? 'btn-primary' : ''}" data-gfmt="mermaid">Mermaid</button>
                <button type="button" class="btn btn-xs ${graphFormat === 'dot' ? 'btn-primary' : ''}" data-gfmt="dot">Graphviz DOT</button>
                <button type="button" class="btn btn-xs ${graphFormat === 'ascii' ? 'btn-primary' : ''}" data-gfmt="ascii">ASCII</button>
                ${lastGraph ? `<button type="button" class="btn btn-xs" id="btn-graph-export">Export Graph</button>` : ''}
              </div>
            </div>
            ${
              graphFormat === 'svg'
                ? renderInteractiveSvgGraph(lastGraph)
                : `<div class="terminal-box"><pre class="terminal-pre" style="max-height:440px">${esc(
                    !lastGraph
                      ? 'Click "Build / Refresh Graph" to parse Terraform HCL and DevSecOps gates.'
                      : graphFormat === 'mermaid'
                        ? lastGraph.mermaid
                        : graphFormat === 'dot'
                          ? lastGraph.dot
                          : lastGraph.ascii_summary
                  )}</pre></div>`
            }
          </section>
        `
        : ''
    }

    ${
      activeTab === 'security-mcp'
        ? `
          <div class="split-2">
            <section class="panel">
              <div class="panel-head">
                <h2 class="panel-title">Security Assessment MCP (Trivy · Bandit · SAST · DAST)</h2>
                ${
                  lastAssessment
                    ? `<span class="tag">${esc(`Grade ${lastAssessment.grade} · ${lastAssessment.compliance_score}/100`)}</span>`
                    : '<span class="panel-meta">Ready</span>'
                }
              </div>
              <div class="field-grid">
                <div class="field">
                  <label for="smcp-path">Target Local Path (optional, defaults to repo)</label>
                  <input id="smcp-path" class="input" value="${esc(secTargetPath)}" placeholder="Leave blank for Syncro Deployer repo" />
                </div>
                <div class="field">
                  <label for="smcp-url">DAST Target URL (Non-Destructive OWASP Check)</label>
                  <input id="smcp-url" class="input" value="${esc(secTargetUrl)}" />
                </div>
              </div>
              <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:10px">
                <button type="button" class="btn btn-primary" id="btn-smcp-full">Run Full Assessment</button>
                <button type="button" class="btn" id="btn-smcp-trivy">Trivy</button>
                <button type="button" class="btn" id="btn-smcp-bandit">Bandit</button>
                <button type="button" class="btn" id="btn-smcp-sast">SAST</button>
                <button type="button" class="btn" id="btn-smcp-dast">DAST</button>
                <button type="button" class="btn" id="btn-smcp-pick">Browse Folder</button>
                ${lastAssessment?.sarif ? `<button type="button" class="btn" id="btn-smcp-sarif">Save SARIF</button>` : ''}
              </div>
              <div style="margin-top:10px; display:flex; gap:5px; flex-wrap:wrap">
                ${Object.entries(secStatus.scanners || {})
                  .map(([k, v]) => `<span class="tag">${esc(k)}: ${v.installed ? 'CLI' : 'builtin'}</span>`)
                  .join('')}
              </div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <h2 class="panel-title">Assessment Summary &amp; Findings</h2>
                ${lastAssessment ? statusTag(lastAssessment.opa_gate?.allowed ? 'ok' : 'blocked') : ''}
              </div>
              <div class="terminal-box">
                <pre class="terminal-pre" style="max-height:420px">${esc(
                  lastAssessment
                    ? prettyJson({
                        assessment_id: lastAssessment.assessment_id,
                        type: lastAssessment.assessment_type,
                        grade: lastAssessment.grade,
                        compliance_score: lastAssessment.compliance_score,
                        opa_allowed: lastAssessment.opa_gate?.allowed,
                        summary: lastAssessment.summary,
                        owasp_breakdown: lastAssessment.owasp_breakdown,
                        dast_probes: lastAssessment.dast_probes,
                        findings_sample: (lastAssessment.findings || []).slice(0, 10),
                      })
                    : 'Run Trivy, Bandit, SAST, DAST, or Full Assessment to inspect findings, OWASP breakdown, SARIF 2.1.0, and DevSecOps security graph.'
                )}</pre>
              </div>
            </section>
          </div>
        `
        : ''
    }
  `;

  // Tab switching
  container.querySelectorAll('[data-iac-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      activeTab = btn.dataset.iacTab;
      renderIacStudio(container, ctx);
    });
  });

  container.querySelector('#btn-iac-popout')?.addEventListener('click', () => ctx.openPopout('iac-studio'));

  // Terraform handlers
  container.querySelector('#btn-tf-gen')?.addEventListener('click', async () => {
    try {
      lastTfBundle = await api.iacTerraformGenerate({
        project_name: container.querySelector('#tf-name').value.trim() || 'syncro-workload',
        cloud: container.querySelector('#tf-cloud').value,
        blueprint: container.querySelector('#tf-blueprint').value,
        environment: container.querySelector('#tf-env').value,
        write_to_disk: true,
      });
      selectedTfFileIdx = 0;
      lastTfBuild = null;
      lastTfRun = null;
      ctx.inspectEntity('Terraform Workspace', lastTfBundle.workspace_id, lastTfBundle);
      ctx.toast(`Generated ${lastTfBundle.files.length} Terraform files (${lastTfBundle.resources.length} resources)`);
      await renderIacStudio(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelector('#btn-tf-build')?.addEventListener('click', async () => {
    try {
      lastTfBuild = await api.iacTerraformBuild({
        workspace_id: lastTfBundle?.workspace_id || null,
      });
      ctx.inspectEntity('Terraform Build', lastTfBuild.workspace_id, lastTfBuild);
      ctx.toast(`Build ${lastTfBuild.validate_ok ? 'PASSED' : 'FAILED'} (${lastTfBuild.resources_discovered.length} resources)`);
      await renderIacStudio(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  const runTf = async (action, dryRun) => {
    try {
      lastTfRun = await api.iacTerraformRun({
        workspace_id: lastTfBundle?.workspace_id || null,
        action,
        dry_run: dryRun,
        auto_approve: !dryRun,
        environment: container.querySelector('#tf-env')?.value || 'staging',
      });
      if (lastTfRun.devsecops_graph) lastGraph = lastTfRun.devsecops_graph;
      ctx.inspectEntity(`Terraform ${action.toUpperCase()}`, lastTfRun.workspace_id, lastTfRun);
      ctx.toast(`Terraform ${action}: ${lastTfRun.status} (Graph Score ${lastGraph?.security_score ?? 100}/100)`);
      await renderIacStudio(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  };

  container.querySelector('#btn-tf-plan')?.addEventListener('click', () => runTf('plan', true));
  container.querySelector('#btn-tf-apply')?.addEventListener('click', () => runTf('apply', false));
  container.querySelector('#btn-tf-graph')?.addEventListener('click', async () => {
    lastGraph = await api.iacDevSecOpsGraph({ workspace_id: lastTfBundle?.workspace_id || null });
    activeTab = 'graph';
    await renderIacStudio(container, ctx);
  });

  container.querySelectorAll('[data-tf-file]').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectedTfFileIdx = Number(btn.dataset.tfFile);
      renderIacStudio(container, ctx);
    });
  });

  container.querySelector('#btn-tf-export')?.addEventListener('click', () => {
    if (activeTfFile) exportOrCopy(activeTfFile.path.replace(/\//g, '-'), activeTfFile.content, ctx.toast);
  });

  // Script writer handlers
  const runWriter = async (fn, label) => {
    try {
      lastScriptBundle = await fn();
      selectedScriptFileIdx = 0;
      ctx.inspectEntity(`${label} Bundle`, lastScriptBundle.name, lastScriptBundle);
      ctx.toast(`Generated ${label}: ${lastScriptBundle.files.length} file(s)`);
      await renderIacStudio(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  };

  container.querySelector('#btn-sw-ansible')?.addEventListener('click', () =>
    runWriter(
      () =>
        api.scriptWriteAnsible({
          service_name: container.querySelector('#sw-name').value.trim() || 'syncro-edge',
          cloud: container.querySelector('#sw-cloud').value,
        }),
      'Ansible'
    )
  );
  container.querySelector('#btn-sw-helm')?.addEventListener('click', () =>
    runWriter(
      () =>
        api.scriptWriteHelm({
          chart_name: container.querySelector('#sw-name').value.trim() || 'syncro-service',
          cloud: container.querySelector('#sw-cloud').value,
        }),
      'Helm Chart'
    )
  );
  container.querySelector('#btn-sw-cicd')?.addEventListener('click', () =>
    runWriter(
      () =>
        api.scriptWriteCicd({
          project_name: container.querySelector('#sw-name').value.trim() || 'syncro-service',
          platform: container.querySelector('#sw-cicd').value,
          language: container.querySelector('#sw-lang').value,
          cloud: container.querySelector('#sw-cloud').value,
        }),
      'CI/CD Pipeline'
    )
  );
  container.querySelector('#btn-sw-container')?.addEventListener('click', () =>
    runWriter(
      () =>
        api.scriptWriteContainer({
          service_name: container.querySelector('#sw-name').value.trim() || 'syncro-api',
          language: container.querySelector('#sw-lang').value,
        }),
      'Container'
    )
  );

  container.querySelectorAll('[data-sw-file]').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectedScriptFileIdx = Number(btn.dataset.swFile);
      renderIacStudio(container, ctx);
    });
  });

  container.querySelector('#btn-sw-export')?.addEventListener('click', () => {
    if (activeScriptFile) exportOrCopy(activeScriptFile.path.replace(/\//g, '-'), activeScriptFile.content, ctx.toast);
  });

  // Graph handlers
  container.querySelector('#btn-graph-refresh')?.addEventListener('click', async () => {
    try {
      lastGraph = await api.iacDevSecOpsGraph({ workspace_id: lastTfBundle?.workspace_id || null });
      ctx.toast(`Graph built: ${lastGraph.nodes.length} nodes, score ${lastGraph.security_score}/100`);
      await renderIacStudio(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelectorAll('[data-gfmt]').forEach((btn) => {
    btn.addEventListener('click', () => {
      graphFormat = btn.dataset.gfmt;
      renderIacStudio(container, ctx);
    });
  });

  container.querySelectorAll('[data-graph-node]').forEach((el) => {
    el.addEventListener('click', () => {
      const node = lastGraph?.nodes?.find((n) => n.id === el.dataset.graphNode);
      if (node) ctx.inspectEntity('DevSecOps Graph Node', node.label, node);
    });
  });

  container.querySelector('#btn-graph-export')?.addEventListener('click', () => {
    if (!lastGraph) return;
    if (graphFormat === 'dot') exportOrCopy('syncro-devsecops.dot', lastGraph.dot, ctx.toast);
    else exportOrCopy('syncro-devsecops.mmd', lastGraph.mermaid, ctx.toast);
  });

  // Security MCP handlers
  const syncInputs = () => {
    secTargetPath = container.querySelector('#smcp-path')?.value.trim() || '';
    secTargetUrl = container.querySelector('#smcp-url')?.value.trim() || 'http://127.0.0.1:8080/api/v1/health';
  };

  container.querySelector('#btn-smcp-pick')?.addEventListener('click', async () => {
    if (window.syncroDesktop?.selectFolder) {
      const res = await window.syncroDesktop.selectFolder();
      if (res?.selected && res.path) {
        secTargetPath = res.path;
        await renderIacStudio(container, ctx);
      }
    }
  });

  const runSec = async (fn, label) => {
    syncInputs();
    try {
      lastAssessment = await fn();
      if (lastAssessment.devsecops_graph) lastGraph = lastAssessment.devsecops_graph;
      ctx.inspectEntity(`${label} Assessment`, `Grade ${lastAssessment.grade}`, lastAssessment);
      ctx.toast(`${label}: Grade ${lastAssessment.grade} (${lastAssessment.compliance_score}/100, ${lastAssessment.findings.length} findings)`);
      await renderIacStudio(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  };

  container.querySelector('#btn-smcp-full')?.addEventListener('click', () =>
    runSec(
      () =>
        api.securityAssessFull({
          project_id: 'payments-core',
          target_path: secTargetPath || null,
          target_url: secTargetUrl || null,
          include_dast: Boolean(secTargetUrl),
          include_graph: true,
        }),
      'Full DevSecOps'
    )
  );
  container.querySelector('#btn-smcp-trivy')?.addEventListener('click', () =>
    runSec(() => api.securityAssessTrivy({ target_path: secTargetPath || null }), 'Trivy')
  );
  container.querySelector('#btn-smcp-bandit')?.addEventListener('click', () =>
    runSec(() => api.securityAssessBandit({ target_path: secTargetPath || null }), 'Bandit')
  );
  container.querySelector('#btn-smcp-sast')?.addEventListener('click', () =>
    runSec(() => api.securityAssessSast({ target_path: secTargetPath || null }), 'SAST')
  );
  container.querySelector('#btn-smcp-dast')?.addEventListener('click', () =>
    runSec(() => api.securityAssessDast({ target_url: secTargetUrl, live_probe: true }), 'DAST')
  );
  container.querySelector('#btn-smcp-sarif')?.addEventListener('click', () => {
    if (lastAssessment?.sarif) {
      exportOrCopy(`syncro-${lastAssessment.assessment_id}.sarif`, prettyJson(lastAssessment.sarif), ctx.toast);
    }
  });
}
