import { api } from '../api/client.js';
import { cloudTag, esc, fmtUsd, statusTag } from '../utils/format.js';

export async function renderOverview(container, ctx) {
  const [overview, clouds, finops, cliStatus, envs, extensions, brokers] = await Promise.all([
    api.overview(),
    api.cloudsStatus(),
    api.finops(),
    api.cliStatus(),
    api.environments(),
    api.extensions(),
    api.brokersHealth(),
  ]);

  const accounts = clouds.accounts || {};
  const cloudTotals = finops.by_cloud || [];
  const maxMonthly = Math.max(...cloudTotals.map((c) => Number(c.projected_monthly_usd || 0)), 1);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>Command Overview</h1>
        <p class="view-subtitle">
          Multi-Cloud AWS · GCP · Azure Fleet, Polyglot Extensions, Tri-Broker Fabric, and Guardrailed Cloud CLI MCP Host.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn" id="btn-ov-refresh">Refresh</button>
        <button type="button" class="btn" id="btn-ov-popout-cli">Pop Out Cloud CLI</button>
        <button type="button" class="btn btn-primary" id="btn-ov-cli">Open Cloud CLI Studio</button>
      </div>
    </div>

    <div class="kpi-strip">
      <div class="kpi-tile">
        <div class="kpi-label">Active Cloud Environments</div>
        <div class="kpi-value">${esc(overview.environments_count ?? envs.length)}</div>
        <div class="kpi-foot">${esc(overview.projects_count ?? 0)} projects · ${envs.filter((e) => e.has_delete_lock).length} lock-protected</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-label">Projected Monthly Spend</div>
        <div class="kpi-value">${fmtUsd(finops.projected_monthly_usd)}</div>
        <div class="kpi-foot">${fmtUsd(finops.reclaimable_ephemeral_monthly_usd)} reclaimable ephemeral</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-label">MCP Tools &amp; CLI Wrappers</div>
        <div class="kpi-value">${esc(ctx.state.health?.mcp_tools_count ?? 34)}</div>
        <div class="kpi-foot">az · gcloud · aws · ${esc(cliStatus.total_executions_recorded ?? 0)} audited runs</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-label">Tri-Broker Throughput</div>
        <div class="kpi-value">${esc(brokers.kafka?.total_published ?? 0)}</div>
        <div class="kpi-foot">Kafka events · ${esc(brokers.rabbitmq?.total_jobs ?? 0)} RMQ jobs · ${esc(brokers.redis?.pubsub_messages_published ?? 0)} Redis fans</div>
      </div>
    </div>

    <div class="split-2">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Cloud Providers &amp; CLI Wrapper Posture</h2>
          <span class="panel-meta">Mode: ${esc(cliStatus.control_plane_mode)}</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Cloud</th>
              <th>CLI Wrapper / MCP Tool</th>
              <th>Identity &amp; Hardening</th>
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
                  <tr data-cloud-jump="${esc(cliKey)}">
                    <td>${cloudTag(c)}</td>
                    <td class="mono">${esc(cliKey)} <span class="panel-meta">${esc(cliMeta.mcp_tool || '')}</span></td>
                    <td>${esc(acc.auth_method || 'OIDC-Federated')}</td>
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
          <h2 class="panel-title">Multi-Cloud FinOps Allocation</h2>
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
                <div class="bar-track"><div class="bar-fill" style="width:${pct}%; background:${color}"></div></div>
                <div class="mono" style="text-align:right">${fmtUsd(row.projected_monthly_usd)}</div>
              </div>
            `;
          })
          .join('')}
        <div style="display:flex; gap:8px; margin-top:12px; flex-wrap:wrap">
          <span class="tag tag-ok">Kafka: ${esc(brokers.kafka?.status || 'healthy')}</span>
          <span class="tag tag-ok">RabbitMQ: ${esc(brokers.rabbitmq?.status || 'healthy')}</span>
          <span class="tag tag-ok">Redis: ${esc(brokers.redis?.status || 'healthy')}</span>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-head">
        <h2 class="panel-title">Live Multi-Cloud Environment Fleet</h2>
        <span class="panel-meta">Click any row to inspect resources &amp; locks · Right-click for desktop actions</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Environment</th>
            <th>Cloud · Region</th>
            <th>Tier &amp; Lock</th>
            <th>VM SKU / Nodes</th>
            <th>Compliance</th>
            <th>Burn Rate</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${envs
            .map(
              (e) => `
                <tr data-env-id="${esc(e.id)}">
                  <td>
                    <div class="mono"><strong>${esc(e.name)}</strong></div>
                    <div class="panel-meta">${esc(e.id)} · ${esc(e.resource_group)}</div>
                  </td>
                  <td>${cloudTag(e.cloud)} <span class="mono panel-meta">${esc(e.location)}</span></td>
                  <td>
                    ${statusTag(e.tier)}
                    ${e.has_delete_lock ? '<span class="tag tag-warn">LOCKED</span>' : ''}
                  </td>
                  <td class="mono">${esc(e.vm_sku || 'k8s-managed')} · ${(e.resources || []).length} nodes</td>
                  <td class="mono">${esc(e.compliance_score ?? 98)}%</td>
                  <td class="mono">${fmtUsd(e.hourly_cost_usd)}/hr</td>
                  <td>
                    <button type="button" class="btn btn-xs" data-drift-env="${esc(e.id)}">Drift Check</button>
                  </td>
                </tr>
              `
            )
            .join('')}
        </tbody>
      </table>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2 class="panel-title">Polyglot Extension Mesh (Go · TypeScript · Java 17)</h2>
        <span class="panel-meta">${extensions.length} registered hooks</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Extension</th>
            <th>Language</th>
            <th>Endpoint</th>
            <th>Capabilities</th>
            <th>Invoke</th>
          </tr>
        </thead>
        <tbody>
          ${extensions
            .map(
              (ext) => `
                <tr>
                  <td class="mono"><strong>${esc(ext.id)}</strong></td>
                  <td><span class="tag tag-accent">${esc(ext.language)}</span></td>
                  <td class="mono panel-meta">${esc(ext.endpoint)}</td>
                  <td class="mono panel-meta">${esc((ext.capabilities || []).join(', '))}</td>
                  <td>
                    <button type="button" class="btn btn-xs" data-ext-invoke="${esc(ext.id)}">Test Hook</button>
                  </td>
                </tr>
              `
            )
            .join('')}
        </tbody>
      </table>
    </section>
  `;

  container.querySelector('#btn-ov-refresh')?.addEventListener('click', () => ctx.reloadCurrentView());
  container.querySelector('#btn-ov-cli')?.addEventListener('click', () => ctx.navigate('cloud-cli'));
  container.querySelector('#btn-ov-popout-cli')?.addEventListener('click', () => ctx.openPopout('cloud-cli'));

  container.querySelectorAll('[data-cloud-jump]').forEach((row) => {
    row.addEventListener('click', () => ctx.openCliProvider(row.dataset.cloudJump));
  });

  container.querySelectorAll('[data-env-id]').forEach((row) => {
    const env = envs.find((e) => e.id === row.dataset.envId);
    if (!env) return;
    row.addEventListener('click', (ev) => {
      if (ev.target.closest('button')) return;
      ctx.inspectEntity('Environment', env.name, env, [
        {
          label: 'Run Go Drift Check',
          primary: true,
          run: async () => {
            const rep = await api.driftCheck(env.id);
            ctx.inspectEntity('Drift Report', `${env.name} (${rep.status})`, rep);
            ctx.toast(`Drift scan completed for ${env.id}`);
          },
        },
        {
          label: 'Open in Quick Destroy',
          run: () => ctx.navigate('security'),
        },
      ]);
    });
    row.addEventListener('contextmenu', (ev) => {
      ev.preventDefault();
      ctx.showContextMenu(ev, [
        { id: 'inspect', label: `Inspect ${env.name}` },
        { id: 'drift', label: 'Run Go Concurrent Drift Check' },
        { type: 'separator' },
        { id: 'popout-cli', label: `Pop Out ${env.cloud.toUpperCase()} CLI Window` },
      ]).then(async (picked) => {
        if (picked === 'inspect') ctx.inspectEntity('Environment', env.name, env);
        else if (picked === 'drift') {
          const rep = await api.driftCheck(env.id);
          ctx.inspectEntity('Drift Report', `${env.name}`, rep);
          ctx.toast(`Drift scan complete: ${rep.drifted_resources_count ?? 0} drifted`);
        } else if (picked === 'popout-cli') {
          ctx.openPopout('cloud-cli');
        }
      });
    });
  });

  container.querySelectorAll('[data-drift-env]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const rep = await api.driftCheck(btn.dataset.driftEnv);
        ctx.inspectEntity('Drift Check Report', btn.dataset.driftEnv, rep);
        ctx.toast(`Drift check ${btn.dataset.driftEnv}: ${rep.status || 'completed'}`);
      } catch (err) {
        ctx.toast(err.message);
      }
    });
  });

  container.querySelectorAll('[data-ext-invoke]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await api.invokeExtension(btn.dataset.extInvoke, 'drift_check', { env: 'env-pr-412' });
        ctx.inspectEntity('Extension Hook Result', btn.dataset.extInvoke, res);
        ctx.toast(`Extension ${btn.dataset.extInvoke} responded (${res.language})`);
      } catch (err) {
        ctx.toast(err.message);
      }
    });
  });
}
