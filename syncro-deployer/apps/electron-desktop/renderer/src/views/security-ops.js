import { api } from '../api/client.js';
import { cloudTag, esc, exportOrCopy, prettyJson, statusTag } from '../utils/format.js';

let lastScan = null;
let lastRbac = null;
let lastDestroyPreview = null;

export async function renderSecurityOps(container, ctx) {
  const [scans, envs] = await Promise.all([api.listScans(), api.environments()]);
  if (!lastScan && scans.length > 0) {
    lastScan = scans[0];
  }

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>DevSecOps &amp; Quick Destroy</h1>
        <p class="view-subtitle">
          Run Checkov/Trivy/Bandit/tfsec/OPA gates, generate least-privilege IAM/PowerShell ABAC plans, and execute HMAC-confirmed teardowns.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn btn-primary" id="btn-sec-scan">Run Full DevSecOps Scan</button>
        <button type="button" class="btn" id="btn-sec-sarif">Export SARIF</button>
      </div>
    </div>

    <div class="split-2">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Security Pipeline &amp; OPA Gate</h2>
          ${lastScan ? statusTag(lastScan.opa_gate?.allowed ? 'ok' : 'blocked') : '<span class="panel-meta">Not run yet</span>'}
        </div>
        <div class="terminal-box">
          <div class="terminal-bar">
            <span>Scanners: Checkov · Trivy · Bandit · tfsec · OPA</span>
            <span class="mono">${esc(lastScan?.id || 'idle')}</span>
          </div>
          <pre class="terminal-pre">${esc(
            lastScan
              ? prettyJson({
                  scan_id: lastScan.id,
                  project_id: lastScan.project_id,
                  opa_allowed: lastScan.opa_gate?.allowed,
                  severity_counts: lastScan.severity_counts,
                  findings_sample: (lastScan.findings || []).slice(0, 6),
                })
              : 'Click "Run Full DevSecOps Scan" to evaluate multi-cloud IaC, K8s manifests, and OPA Rego gates.'
          )}</pre>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Least-Privilege IAM / PowerShell ABAC Planner</h2>
          <button type="button" class="btn btn-xs" id="btn-sec-rbac">Generate Plan</button>
        </div>
        <div class="field-grid">
          <div class="field">
            <label for="rbac-cloud">Cloud</label>
            <select id="rbac-cloud" class="select">
              <option value="azure">Azure (PowerShell ABAC)</option>
              <option value="aws">AWS (IAM Least-Privilege)</option>
              <option value="gcp">GCP (gcloud IAM CEL)</option>
            </select>
          </div>
          <div class="field">
            <label for="rbac-scope">Scope / Resource Group</label>
            <input id="rbac-scope" class="input" value="rg-aegis-payments-pr-412" />
          </div>
        </div>
        <div class="terminal-box">
          <div class="terminal-bar">
            <span>Generated Least-Privilege Script</span>
            <button type="button" class="btn-ghost btn-xs" id="btn-rbac-export">Export</button>
          </div>
          <pre class="terminal-pre">${esc(
            lastRbac ? lastRbac.powershell_script || prettyJson(lastRbac) : 'Generate an OPA-verified least-privilege IAM/ABAC plan with zero Owner/Admin roles.'
          )}</pre>
        </div>
      </section>
    </div>

    <section class="panel" style="margin-top:16px">
      <div class="panel-head">
        <h2 class="panel-title">Two-Phase Multi-Cloud Quick Destruction (HMAC Token + Lock Guard)</h2>
        <span class="panel-meta">Production scopes are lock-protected</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Environment</th>
            <th>Cloud · Tier</th>
            <th>Delete Lock / Lien</th>
            <th>Hourly Cost</th>
            <th>Status</th>
            <th>Teardown</th>
          </tr>
        </thead>
        <tbody>
          ${envs
            .map(
              (e) => `
                <tr>
                  <td class="mono"><strong>${esc(e.id)}</strong> <span class="panel-meta">${esc(e.name)}</span></td>
                  <td>${cloudTag(e.cloud)} ${statusTag(e.tier)}</td>
                  <td>${e.has_delete_lock ? '<span class="tag tag-warn">LOCKED</span>' : '<span class="panel-meta">None</span>'}</td>
                  <td class="mono">$${Number(e.hourly_cost_usd || 0).toFixed(2)}/hr</td>
                  <td>${statusTag(e.status)}</td>
                  <td>
                    <button type="button" class="btn btn-xs btn-danger" data-destroy-preview="${esc(e.id)}">
                      Phase 1: Preview
                    </button>
                  </td>
                </tr>
              `
            )
            .join('')}
        </tbody>
      </table>

      ${
        lastDestroyPreview
          ? `
            <div style="margin-top:14px; padding-top:14px; border-top:1px solid var(--border-subtle)">
              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px">
                <span class="mono">Blast-Radius Preview: <strong>${esc(lastDestroyPreview.environment_id)}</strong> · Token: <code>${esc(lastDestroyPreview.confirmation_token || 'BLOCKED')}</code></span>
                ${
                  lastDestroyPreview.allowed_to_destroy
                    ? `<button type="button" class="btn btn-danger btn-xs" id="btn-destroy-exec">Phase 2: Execute Confirmed Kill-Switch</button>`
                    : `<span class="tag tag-danger">Protected by OPA / Delete Lock</span>`
                }
              </div>
              <div class="terminal-box">
                <pre class="terminal-pre">${esc(prettyJson(lastDestroyPreview))}</pre>
              </div>
            </div>
          `
          : ''
      }
    </section>
  `;

  container.querySelector('#btn-sec-scan')?.addEventListener('click', async () => {
    try {
      lastScan = await api.triggerScan({ project_id: 'payments-core' });
      ctx.toast(`Scan ${lastScan.id}: OPA ${lastScan.opa_gate?.allowed ? 'PASSED' : 'BLOCKED'}`);
      await renderSecurityOps(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelector('#btn-sec-sarif')?.addEventListener('click', async () => {
    if (!lastScan) {
      ctx.toast('Run a security scan first.');
      return;
    }
    try {
      const sarif = await api.scanSarif(lastScan.id);
      exportOrCopy(`syncro-scan-${lastScan.id}.sarif`, prettyJson(sarif), ctx.toast);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelector('#btn-sec-rbac')?.addEventListener('click', async () => {
    try {
      lastRbac = await api.rbacPlan({
        cloud: container.querySelector('#rbac-cloud').value,
        resource_group: container.querySelector('#rbac-scope').value.trim(),
      });
      ctx.toast(`Generated ${lastRbac.cloud?.toUpperCase() || 'IAM'} least-privilege plan`);
      await renderSecurityOps(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelector('#btn-rbac-export')?.addEventListener('click', () => {
    if (!lastRbac) return;
    exportOrCopy('syncro-rbac-plan.ps1', lastRbac.powershell_script || prettyJson(lastRbac), ctx.toast);
  });

  container.querySelectorAll('[data-destroy-preview]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        lastDestroyPreview = await api.destroyPreview(btn.dataset.destroyPreview);
        await renderSecurityOps(container, ctx);
      } catch (err) {
        ctx.toast(err.message);
      }
    });
  });

  container.querySelector('#btn-destroy-exec')?.addEventListener('click', async () => {
    if (!lastDestroyPreview?.confirmation_token) return;
    try {
      const res = await api.destroyExecute(lastDestroyPreview.environment_id, {
        confirmation_token: lastDestroyPreview.confirmation_token,
        kill_switch: true,
        actor: 'electron-desktop',
      });
      ctx.toast(`Destroyed ${res.environment_id} (${res.status})`);
      lastDestroyPreview = null;
      await renderSecurityOps(container, ctx);
    } catch (err) {
      ctx.toast(`Destroy blocked: ${err.message}`);
    }
  });
}
