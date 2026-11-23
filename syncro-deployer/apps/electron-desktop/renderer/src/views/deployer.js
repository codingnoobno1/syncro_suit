import { api } from '../api/client.js';
import { cloudTag, esc, statusTag } from '../utils/format.js';

export async function renderDeployer(container, ctx) {
  const [deployments, resilience] = await Promise.all([
    api.syncroDeployments(),
    api.syncroResilience(),
  ]);

  const activeMode = ctx.state.mode || 'agentic';
  const defaultKey = `electron-${Date.now().toString(36).slice(-5)}`;
  const latest = deployments[0] || null;
  const breakers = Object.entries(resilience.circuit_breakers || {});

  const stageRank = {
    preflight: 1,
    canary_5: 2,
    canary_25: 3,
    promoted_100: 4,
    rolled_back: 0,
  };
  const rank = stageRank[latest?.stage] ?? 0;

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>Syncro Deployer</h1>
        <p class="view-subtitle">
          Idempotent, lock-safe multi-cloud canary releases with circuit breakers, SQLite WAL journaling, and automatic SLO rollback.
        </p>
      </div>
      <div class="header-actions">
        <span class="tag tag-accent">Mode: ${esc(activeMode.toUpperCase())}</span>
        <span class="tag tag-ok">WAL Journal: ${esc(resilience.journal?.deployments_persisted ?? deployments.length)} persisted</span>
        <button type="button" class="btn" id="btn-dep-popout">Pop Out Window</button>
      </div>
    </div>

    ${
      latest
        ? `
          <div class="stepper">
            <div class="step-cell ${rank >= 1 ? 'done' : ''}">01 PREFLIGHT SCAN</div>
            <div class="step-cell ${rank > 2 ? 'done' : rank === 2 ? 'active' : ''}">02 CANARY 5%</div>
            <div class="step-cell ${rank > 3 ? 'done' : rank === 3 ? 'active' : ''}">03 CANARY 25%</div>
            <div class="step-cell ${rank === 4 ? 'done' : latest.stage === 'rolled_back' ? 'tag-danger' : ''}">
              ${latest.stage === 'rolled_back' ? '04 AUTO ROLLED BACK' : '04 PROMOTED 100%'}
            </div>
          </div>
        `
        : ''
    }

    <div class="split-2">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Launch Release Pipeline</h2>
          <span class="panel-meta">${activeMode === 'agentic' ? 'Autonomous progression' : 'Operator stage-gate'}</span>
        </div>

        <div class="field-grid">
          <div class="field">
            <label for="dep-project">Project</label>
            <input id="dep-project" class="input" value="edge-gateway" />
          </div>
          <div class="field">
            <label for="dep-env">Environment</label>
            <input id="dep-env" class="input" value="electron-prod-canary" />
          </div>
          <div class="field">
            <label for="dep-cloud">Target Cloud</label>
            <select id="dep-cloud" class="select">
              <option value="gcp">GCP (GKE / Shielded GCE)</option>
              <option value="aws">AWS (EKS / EC2 Nitro)</option>
              <option value="azure">Azure (AKS / Confidential VM)</option>
            </select>
          </div>
          <div class="field">
            <label for="dep-target">Runtime Target</label>
            <select id="dep-target" class="select">
              <option value="kubernetes">Kubernetes</option>
              <option value="vm">Cloud VM (IaC)</option>
              <option value="docker">Hardened Docker</option>
            </select>
          </div>
          <div class="field">
            <label for="dep-strategy">Rollout Strategy</label>
            <select id="dep-strategy" class="select">
              <option value="canary">Canary (5% / 25% / 100%)</option>
              <option value="blue-green">Blue-Green</option>
              <option value="rolling">Rolling</option>
            </select>
          </div>
          <div class="field">
            <label for="dep-idem">Idempotency-Key</label>
            <input id="dep-idem" class="input" value="${esc(defaultKey)}" />
          </div>
        </div>

        <div class="check-row">
          <label class="check-item">
            <input type="checkbox" id="dep-sim-fault" />
            <span>Simulate Canary SLO Fault (auto-rollback)</span>
          </label>
          <button type="button" class="btn btn-primary" id="btn-dep-launch" style="margin-left:auto">
            Deploy (${esc(activeMode)})
          </button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Resilience &amp; Circuit Breakers</h2>
          <span class="panel-meta">Online desktop agents: ${esc(resilience.online_desktop_agents ?? 1)}</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Sub-System Breaker</th>
              <th>State</th>
              <th>Failures</th>
            </tr>
          </thead>
          <tbody>
            ${breakers
              .map(
                ([name, br]) => `
                  <tr>
                    <td class="mono">${esc(name)}</td>
                    <td>${statusTag(br.state === 'closed' ? 'healthy' : br.state)}</td>
                    <td class="mono">${esc(br.failures ?? 0)}</td>
                  </tr>
                `
              )
              .join('')}
          </tbody>
        </table>
      </section>
    </div>

    <section class="panel">
      <div class="panel-head">
        <h2 class="panel-title">Deployment Ledger (${deployments.length})</h2>
        <span class="panel-meta">Click any row to inspect revision snapshot &amp; events</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Deployment</th>
            <th>Cloud · Target</th>
            <th>Mode</th>
            <th>Stage</th>
            <th>Traffic Split</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${deployments
            .map(
              (d) => `
                <tr data-dep-id="${esc(d.id)}">
                  <td>
                    <div class="mono"><strong>${esc(d.environment_name)}</strong></div>
                    <div class="panel-meta">${esc(d.id)} · ${esc(d.project_id)}</div>
                  </td>
                  <td>${cloudTag(d.cloud)} <span class="panel-meta">${esc(d.target_type)}</span></td>
                  <td class="mono">${esc(d.mode)}</td>
                  <td>${statusTag(d.stage)}</td>
                  <td class="mono">${esc(d.stable_pct)}% stable / ${esc(d.canary_pct)}% canary</td>
                  <td>
                    <div style="display:flex; gap:6px">
                      ${
                        ['canary_5', 'canary_25'].includes(d.stage)
                          ? `<button type="button" class="btn btn-primary btn-xs" data-promote-id="${esc(d.id)}">Promote</button>`
                          : ''
                      }
                      ${
                        d.stage !== 'rolled_back'
                          ? `<button type="button" class="btn btn-danger btn-xs" data-rollback-id="${esc(d.id)}">Rollback</button>`
                          : '<span class="panel-meta">Reverted</span>'
                      }
                    </div>
                  </td>
                </tr>
              `
            )
            .join('')}
        </tbody>
      </table>
    </section>
  `;

  container.querySelector('#btn-dep-popout')?.addEventListener('click', () => ctx.openPopout('deployer'));

  container.querySelectorAll('[data-dep-id]').forEach((row) => {
    const dep = deployments.find((d) => d.id === row.dataset.depId);
    if (!dep) return;
    row.addEventListener('click', (ev) => {
      if (ev.target.closest('button')) return;
      ctx.inspectEntity('Deployment', dep.environment_name, dep);
    });
  });

  container.querySelector('#btn-dep-launch')?.addEventListener('click', async () => {
    try {
      const dep = await api.syncroDeploy({
        project_id: container.querySelector('#dep-project').value.trim(),
        environment_name: container.querySelector('#dep-env').value.trim(),
        cloud: container.querySelector('#dep-cloud').value,
        target_type: container.querySelector('#dep-target').value,
        strategy: container.querySelector('#dep-strategy').value,
        mode: activeMode,
        idempotency_key: container.querySelector('#dep-idem').value.trim(),
        simulate_canary_fault: container.querySelector('#dep-sim-fault').checked,
        requested_by: 'electron-desktop',
      });
      ctx.toast(`Deployment ${dep.id}: ${dep.stage}`);
      ctx.inspectEntity('Deployment', dep.environment_name, dep);
      ctx.pushLocalEvent('syncro.deploy', `${dep.environment_name} (${dep.cloud}) -> ${dep.stage}`);
      if (dep.auto_rolled_back && window.syncroDesktop?.notify) {
        window.syncroDesktop.notify('Syncro Auto-Rollback Executed', `${dep.environment_name} reverted to stable revision.`);
      }
      await renderDeployer(container, ctx);
    } catch (err) {
      ctx.toast(`Deploy failed: ${err.message}`);
    }
  });

  container.querySelectorAll('[data-promote-id]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await api.syncroPromote(btn.dataset.promoteId);
        ctx.toast(`Promoted ${res.id} -> ${res.stage}`);
        ctx.inspectEntity('Deployment', res.environment_name, res);
        await renderDeployer(container, ctx);
      } catch (err) {
        ctx.toast(err.message);
      }
    });
  });

  container.querySelectorAll('[data-rollback-id]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await api.syncroRollback(btn.dataset.rollbackId, 'Operator rollback from Electron desktop');
        ctx.toast(`Rolled back ${res.id}`);
        ctx.inspectEntity('Deployment', res.environment_name, res);
        await renderDeployer(container, ctx);
      } catch (err) {
        ctx.toast(err.message);
      }
    });
  });
}
