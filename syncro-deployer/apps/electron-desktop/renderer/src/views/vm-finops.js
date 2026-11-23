import { api } from '../api/client.js';
import { cloudTag, esc, exportOrCopy, fmtUsd } from '../utils/format.js';

let lastCompare = null;
let criteria = {
  min_vcpu: 4,
  min_memory_gib: 16,
  require_confidential_compute: true,
  prefer_spot: true,
};

export async function renderVmFinops(container, ctx) {
  if (!lastCompare) {
    lastCompare = await api.vmCompare(criteria);
  }
  const best = lastCompare.best_overall;
  const perCloud = [lastCompare.best_by_cloud?.aws, lastCompare.best_by_cloud?.gcp, lastCompare.best_by_cloud?.azure].filter(Boolean);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>Multi-Cloud VM &amp; FinOps Matrix</h1>
        <p class="view-subtitle">
          Score optimal compute SKUs across AWS EC2, GCP Shielded GCE, and Azure Confidential VMs with live CIS Terraform HCL.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn" id="btn-vm-export-hcl">Export Winner Terraform HCL</button>
      </div>
    </div>

    <section class="panel">
      <div class="panel-head">
        <h2 class="panel-title">Workload Sizing &amp; Hardware Security Criteria</h2>
        <span class="panel-meta">19-SKU Real Multi-Cloud Catalog</span>
      </div>
      <div class="field-grid">
        <div class="field">
          <label for="vm-vcpu">Min vCPU</label>
          <input id="vm-vcpu" class="input" type="number" min="1" max="128" value="${esc(criteria.min_vcpu)}" />
        </div>
        <div class="field">
          <label for="vm-ram">Min Memory (GiB)</label>
          <input id="vm-ram" class="input" type="number" min="2" max="512" value="${esc(criteria.min_memory_gib)}" />
        </div>
        <div class="field" style="justify-content:flex-end">
          <label class="check-item" style="margin-top:20px">
            <input type="checkbox" id="vm-conf" ${criteria.require_confidential_compute ? 'checked' : ''} />
            <span>Confidential Compute (SEV-SNP / TDX / Nitro)</span>
          </label>
        </div>
        <div class="field" style="justify-content:flex-end">
          <label class="check-item" style="margin-top:20px">
            <input type="checkbox" id="vm-spot" ${criteria.prefer_spot ? 'checked' : ''} />
            <span>Prefer Spot / Preemptible</span>
          </label>
        </div>
      </div>
      <button type="button" class="btn btn-primary" id="btn-vm-compare">Compare Across AWS · GCP · Azure</button>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2 class="panel-title">3-Cloud Side-by-Side Parity</h2>
        <span class="tag tag-ok">Winner: ${esc(best?.sku?.cloud?.toUpperCase() || '')} ${esc(best?.sku?.sku || 'N/A')}</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Cloud</th>
            <th>SKU</th>
            <th>Spec</th>
            <th>Hardware Security</th>
            <th>Effective Cost</th>
            <th>Fit / Sec</th>
            <th>Provision</th>
          </tr>
        </thead>
        <tbody>
          ${perCloud
            .map(
              (rec) => `
                <tr>
                  <td>${cloudTag(rec.sku.cloud)}</td>
                  <td class="mono"><strong>${esc(rec.sku.sku)}</strong></td>
                  <td class="mono">${esc(rec.sku.vcpu)} vCPU · ${esc(rec.sku.memory_gib)} GiB · ${esc(rec.sku.architecture)}</td>
                  <td>${esc(rec.sku.security?.confidential_tech || 'Trusted Launch / IMDSv2')}</td>
                  <td class="mono">${fmtUsd(rec.effective_hourly_usd)}/hr <span class="panel-meta">(${fmtUsd(rec.effective_monthly_usd)}/mo)</span></td>
                  <td class="mono">${esc(rec.fit_score)} / ${esc(rec.security_score)}</td>
                  <td>
                    <button type="button" class="btn btn-xs btn-primary" data-prov-cloud="${esc(rec.sku.cloud)}" data-prov-sku="${esc(rec.sku.sku)}" data-prov-region="${esc(rec.sku.regions?.[0] || 'us-east-1')}">
                      Provision 4h
                    </button>
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
        <h2 class="panel-title">Generated CIS-Hardened Terraform HCL (${esc(best?.sku?.sku || 'Winner')})</h2>
        <span class="panel-meta">Ready for Terraform Plan &amp; OPA Gate</span>
      </div>
      <div class="terminal-box">
        <div class="terminal-bar">
          <span>main.tf · ${esc(best?.sku?.cloud || '')}</span>
          <span>TTL Ephemeral Lease</span>
        </div>
        <pre class="terminal-pre">${esc(best?.terraform_snippet || 'No matching SKU found for current filters.')}</pre>
      </div>
    </section>
  `;

  container.querySelector('#btn-vm-compare')?.addEventListener('click', async () => {
    criteria = {
      min_vcpu: Number(container.querySelector('#vm-vcpu').value || 4),
      min_memory_gib: Number(container.querySelector('#vm-ram').value || 16),
      require_confidential_compute: container.querySelector('#vm-conf').checked,
      prefer_spot: container.querySelector('#vm-spot').checked,
    };
    try {
      lastCompare = await api.vmCompare(criteria);
      await renderVmFinops(container, ctx);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelectorAll('[data-prov-sku]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await api.vmProvision({
          project_id: 'edge-gateway',
          environment_name: `electron-vm-${btn.dataset.provCloud}`,
          cloud: btn.dataset.provCloud,
          sku: btn.dataset.provSku,
          region: btn.dataset.provRegion,
          use_spot: criteria.prefer_spot,
          ttl_hours: 4,
        });
        ctx.toast(`Provisioned ${res.sku} on ${res.cloud.toUpperCase()} (${res.environment_id})`);
        ctx.pushLocalEvent('vm.provisioned', `${res.cloud} ${res.sku} in ${res.region}`);
      } catch (err) {
        ctx.toast(`Provision failed: ${err.message}`);
      }
    });
  });

  container.querySelector('#btn-vm-export-hcl')?.addEventListener('click', () => {
    if (!best?.terraform_snippet) return;
    exportOrCopy(`syncro-${best.sku.cloud}-${best.sku.sku}.tf`, best.terraform_snippet, ctx.toast);
  });
}
