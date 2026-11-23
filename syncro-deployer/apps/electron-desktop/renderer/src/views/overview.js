import { api } from '../api/client.js';
import { cloudTag, esc, fmtUsd, statusTag } from '../utils/format.js';

export async function renderOverview(container, ctx) {
  const [overview, clouds, finops, cliStatus, suite, kafkaEvents] = await Promise.all([
    api.overview(),
    api.cloudsStatus(),
    api.finops(),
    api.cliStatus(),
    api.syncroSuite(),
    api.kafkaEvents(),
  ]);

  const accounts = clouds.accounts || {};
  const cloudTotals = finops.by_cloud || [];
  const maxMonthly = Math.max(...cloudTotals.map((c) => Number(c.projected_monthly_usd || 0)), 1);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>Command Overview</h1>
        <p class="view-subtitle">
          Unified AWS · GCP · Azure DevSecOps Control Plane, Guardrailed Cloud CLI MCP Host, and Tri-Broker Event Fabric.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn" id="btn-ov-refresh">Refresh Telemetry</button>
        <button type="button" class="btn btn-primary" id="btn-ov-cli">Open Cloud CLI Studio</button>
      </div>
    </div>

    <div class="kpi-strip">
      <div class="kpi-tile">
        <div class="kpi-label">Active Environments</div>
        <div class="kpi-value">${esc(overview.environments_count ?? 0)}</div>
        <div class="kpi-foot">${esc(overview.projects_count ?? 0)} polyglot projects registered</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-label">Projected Monthly Burn</div>
        <div class="kpi-value">${fmtUsd(finops.projected_monthly_usd)}</div>
        <div class="kpi-foot">${fmtUsd(finops.reclaimable_ephemeral_monthly_usd)} reclaimable ephemeral</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-label">MCP Tools Active</div>
        <div class="kpi-value">${esc(ctx.state.health?.mcp_tools_count ?? 34)}</div>
        <div class="kpi-foot">az · gcloud · aws wrappers enabled</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-label">CLI Executions Audited</div>
        <div class="kpi-value">${esc(cliStatus.total_executions_recorded ?? 0)}</div>
        <div class="kpi-foot">Zero-shell argv guardrail enforced</div>
      </div>
    </div>

    <div class="split-2">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Multi-Cloud Accounts &amp; CLI Posture</h2>
          <span class="panel-meta">Mode: ${esc(cliStatus.control_plane_mode)}</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Cloud</th>
              <th>CLI Wrapper</th>
              <th>Auth / Security</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            ${['aws', 'gcp', 'azure']
              .map((c) => {
                const acc = accounts[c] || {};
                const cliKey = c === 'gcp' ? 'gcloud' : c === 'azure' ? 'az' : 'aws';
                const cliMeta = cliStatus.cloud_clis?.[cliKey] || {};
                return `
                  <tr>
                    <td>${cloudTag(c)}</td>
                    <td class="mono">${esc(cliKey)} · <span class="panel-meta">${esc(cliMeta.mcp_tool || '')}</span></td>
                    <td>${esc(acc.auth_method || 'OIDC')}</td>
                    <td>${statusTag(cliMeta.execution_mode || 'simulation')}</td>
                  </tr>
                `;
              })
              .join('')}
          </tbody>
        </table>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">FinOps Spend by Cloud</h2>
          <span class="panel-meta">${fmtUsd(finops.total_hourly_usd)}/hr live</span>
        </div>
        ${cloudTotals
          .map((row) => {
            const pct = Math.min(100, Math.round((Number(row.projected_monthly_usd || 0) / maxMonthly) * 100));
            const color =
              row.cloud === 'aws'
                ? 'var(--cloud-aws)'
                : row.cloud === 'gcp'
                  ? 'var(--cloud-gcp)'
                  : 'var(--cloud-azure)';
            return `
              <div class="bar-row">
                <div>${cloudTag(row.cloud)}</div>
                <div class="bar-track">
                  <div class="bar-fill" style="width:${pct}%; background:${color}"></div>
                </div>
                <div class="mono" style="text-align:right">${fmtUsd(row.projected_monthly_usd)}</div>
              </div>
            `;
          })
          .join('')}
        <div class="panel-meta" style="margin-top:14px">
          Active Syncro Suite modules: ${(suite.modules || []).filter((m) => m.status === 'active').length}/${(suite.modules || []).length}
          · Mode: <span class="mono">${esc(suite.active_mode)}</span>
        </div>
      </section>
    </div>

    <div class="split-2">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Syncro Suite &amp; Native Desktop Runtime</h2>
          <span class="panel-meta">${esc(ctx.state.systemInfo?.platform || 'browser')} · ${esc(ctx.state.systemInfo?.arch || 'web')}</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Module</th>
              <th>Transport</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${(suite.modules || [])
              .map(
                (m) => `
                  <tr>
                    <td><strong>${esc(m.name)}</strong></td>
                    <td class="mono">${esc(m.transport || 'rest')}</td>
                    <td>${statusTag(m.status)}</td>
                  </tr>
                `
              )
              .join('')}
          </tbody>
        </table>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Recent Kafka CloudEvents Audit Tail</h2>
          <span class="panel-meta">${kafkaEvents.length} latest</span>
        </div>
        <div class="terminal-box">
          <div class="terminal-bar">
            <span>topic: aegis.audit.events</span>
            <span>CloudEvents 1.0</span>
          </div>
          <pre class="terminal-pre">${esc(
            kafkaEvents
              .slice(0, 12)
              .map((e) => `[${String(e.time || '').slice(11, 19)}] ${e.type} (${e.subject || e.source})`)
              .join('\n') || 'No CloudEvents emitted yet.'
          )}</pre>
        </div>
      </section>
    </div>
  `;

  container.querySelector('#btn-ov-refresh')?.addEventListener('click', () => ctx.reloadCurrentView());
  container.querySelector('#btn-ov-cli')?.addEventListener('click', () => ctx.navigate('cloud-cli'));
}
