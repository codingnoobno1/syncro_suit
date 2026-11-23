import { api, mcpCall } from '../api/client.js';
import { cloudTag, esc, exportOrCopy, prettyJson, statusTag } from '../utils/format.js';

let selectedProvider = 'az';
let transportMode = 'mcp'; // 'mcp' or 'rest'
let lastResult = null;

function parseArgString(raw) {
  const tokens = [];
  const regex = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let match;
  while ((match = regex.exec(raw)) !== null) {
    tokens.push(match[1] ?? match[2] ?? match[3]);
  }
  return tokens;
}

export async function renderCloudCli(container, ctx) {
  const [status, presets, history] = await Promise.all([
    api.cliStatus(),
    api.cliPresets(),
    api.cliHistory(),
  ]);

  const filteredPresets = presets.filter((p) => p.provider === selectedProvider);
  const provMeta = status.cloud_clis?.[selectedProvider] || {};

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>Cloud CLI Studio</h1>
        <p class="view-subtitle">
          Execute guardrailed Azure (<code>az</code>), GCP (<code>gcloud</code>), and AWS (<code>aws</code>) commands through REST or MCP JSON-RPC wrappers.
        </p>
      </div>
      <div class="header-actions">
        <div class="tab-bar" role="tablist" aria-label="Cloud CLI provider">
          <button type="button" class="tab-btn ${selectedProvider === 'az' ? 'active' : ''}" id="cli-tab-az" data-provider="az">Azure · az</button>
          <button type="button" class="tab-btn ${selectedProvider === 'gcloud' ? 'active' : ''}" id="cli-tab-gcloud" data-provider="gcloud">GCP · gcloud</button>
          <button type="button" class="tab-btn ${selectedProvider === 'aws' ? 'active' : ''}" id="cli-tab-aws" data-provider="aws">AWS · aws</button>
        </div>
        <div class="tab-bar" role="group" aria-label="Invocation transport">
          <button type="button" class="tab-btn ${transportMode === 'mcp' ? 'active' : ''}" id="cli-via-mcp" data-transport="mcp">Via MCP</button>
          <button type="button" class="tab-btn ${transportMode === 'rest' ? 'active' : ''}" id="cli-via-rest" data-transport="rest">Via REST</button>
        </div>
      </div>
    </div>

    <div class="split-wide">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Curated Recipes</h2>
          <span class="panel-meta">${esc(provMeta.mcp_tool || '')}</span>
        </div>
        <div class="preset-list" id="cli-preset-list">
          ${filteredPresets
            .map(
              (p) => `
                <button type="button" class="preset-item" data-preset-args="${esc(p.args.join(' '))}">
                  <div class="preset-item-top">
                    <span class="preset-title">${esc(p.title)}</span>
                    ${statusTag(p.risk_tier)}
                  </div>
                  <div class="preset-cmd">${esc(p.provider)} ${esc(p.args.join(' '))}</div>
                  <div class="preset-desc">${esc(p.description)}</div>
                </button>
              `
            )
            .join('')}
        </div>

        <div style="margin-top:14px; padding-top:12px; border-top:1px solid var(--border-subtle)">
          <div class="panel-meta" style="margin-bottom:6px">GUARDRAIL TESTS (TRY BLOCKED OPS)</div>
          <div style="display:flex; flex-direction:column; gap:6px">
            <button type="button" class="btn btn-danger btn-xs" id="btn-test-injection">
              Test Shell Injection Block
            </button>
            <button type="button" class="btn btn-danger btn-xs" id="btn-test-prod-delete">
              Test Production Delete Block
            </button>
          </div>
        </div>
      </section>

      <div style="display:flex; flex-direction:column; gap:16px">
        <section class="panel">
          <div class="panel-head">
            <h2 class="panel-title">Command Runner (${esc(selectedProvider)})</h2>
            <div style="display:flex; gap:8px; align-items:center">
              ${statusTag(provMeta.execution_mode || 'simulation')}
              <span class="panel-meta">${provMeta.installed ? 'Binary on PATH' : 'Simulation fallback'}</span>
            </div>
          </div>

          <div class="field-grid">
            <div class="field" style="grid-column: span 2">
              <label for="cli-args-input">Subcommand Arguments (zero shell interpolation)</label>
              <input
                id="cli-args-input"
                class="input"
                type="text"
                value="${esc(filteredPresets[0]?.args.join(' ') || 'version')}"
                placeholder="e.g. vm list  |  compute instances list  |  ec2 describe-instances"
              />
            </div>
            <div class="field">
              <label for="cli-scope-input">${selectedProvider === 'az' ? 'Subscription' : selectedProvider === 'gcloud' ? 'GCP Project' : 'AWS Profile / Region'}</label>
              <input id="cli-scope-input" class="input" type="text" placeholder="Optional override" />
            </div>
          </div>

          <div class="check-row">
            <label class="check-item">
              <input type="checkbox" id="cli-dry-run" />
              <span>Dry-Run Preview</span>
            </label>
            <label class="check-item">
              <input type="checkbox" id="cli-allow-destructive" />
              <span>Allow Ephemeral Destructive</span>
            </label>
            <button type="button" class="btn btn-primary" id="btn-cli-run" style="margin-left:auto">
              Execute ${esc(selectedProvider)} (${transportMode.toUpperCase()})
            </button>
          </div>

          <div class="terminal-box">
            <div class="terminal-bar">
              <span id="cli-output-cmd">${esc(lastResult?.command_preview || `${selectedProvider} ready`)}</span>
              <div style="display:flex; gap:8px; align-items:center">
                <span id="cli-output-status">${lastResult ? statusTag(lastResult.mode) : ''}</span>
                <button type="button" class="btn-ghost btn-xs" id="btn-cli-export">Export JSON</button>
              </div>
            </div>
            <pre class="terminal-pre" id="cli-output-pre">${esc(
              lastResult ? prettyJson(lastResult) : 'Select a curated recipe or type arguments and press Execute.'
            )}</pre>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2 class="panel-title">Audited CLI Execution History</h2>
            <span class="panel-meta">${history.length} recent calls</span>
          </div>
          <table class="data-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Command</th>
                <th>Risk</th>
                <th>Mode</th>
                <th>Exit</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              ${
                history.length === 0
                  ? '<tr><td colspan="6" class="panel-meta">No CLI executions recorded in this session yet.</td></tr>'
                  : history
                      .slice(0, 10)
                      .map(
                        (h) => `
                          <tr>
                            <td>${cloudTag(h.provider)}</td>
                            <td class="mono">${esc(h.command_preview)}</td>
                            <td>${statusTag(h.risk_tier)}</td>
                            <td>${statusTag(h.mode)}</td>
                            <td class="mono">${esc(h.exit_code)}</td>
                            <td class="mono">${esc(h.duration_ms)} ms</td>
                          </tr>
                        `
                      )
                      .join('')
              }
            </tbody>
          </table>
        </section>
      </div>
    </div>
  `;

  async function runArgs(rawArgStr, overrides = {}) {
    const args = parseArgString(rawArgStr);
    if (args.length === 0) {
      ctx.toast('Enter at least one CLI argument.');
      return;
    }
    const dryRun = overrides.dry_run ?? container.querySelector('#cli-dry-run').checked;
    const allowDestructive = overrides.allow_destructive ?? container.querySelector('#cli-allow-destructive').checked;
    const scope = container.querySelector('#cli-scope-input').value.trim() || null;

    const btn = container.querySelector('#btn-cli-run');
    btn.disabled = true;
    try {
      let result;
      if (transportMode === 'mcp') {
        const toolName =
          selectedProvider === 'az'
            ? 'aegis_az_cli'
            : selectedProvider === 'gcloud'
              ? 'aegis_gcp_cli'
              : 'aegis_aws_cli';
        const toolArgs = {
          args,
          dry_run: dryRun,
          allow_destructive: allowDestructive,
        };
        if (scope) {
          if (selectedProvider === 'az') toolArgs.subscription = scope;
          else if (selectedProvider === 'gcloud') toolArgs.project = scope;
          else toolArgs.region = scope;
        }
        const mcpRes = await mcpCall('tools/call', { name: toolName, arguments: toolArgs });
        result = JSON.parse(mcpRes.content[0].text);
      } else {
        result = await api.cliExec({
          provider: selectedProvider,
          args,
          dry_run: dryRun,
          allow_destructive: allowDestructive,
          subscription_or_project: selectedProvider !== 'aws' ? scope : null,
          region: selectedProvider === 'aws' ? scope : null,
          actor: 'electron-desktop',
        });
      }
      lastResult = result;
      ctx.pushLocalEvent(
        result.guardrail?.allowed ? 'cli.executed' : 'cli.blocked',
        `${result.command_preview} -> exit ${result.exit_code} (${result.mode})`
      );
      if (!result.guardrail?.allowed && window.syncroDesktop?.notify) {
        window.syncroDesktop.notify('Syncro Guardrail Blocked CLI', result.stderr || result.command_preview);
      }
      await renderCloudCli(container, ctx);
    } catch (err) {
      ctx.toast(`CLI Error: ${err.message}`);
    } finally {
      btn.disabled = false;
    }
  }

  container.querySelectorAll('[data-provider]').forEach((el) => {
    el.addEventListener('click', () => {
      selectedProvider = el.dataset.provider;
      renderCloudCli(container, ctx);
    });
  });

  container.querySelectorAll('[data-transport]').forEach((el) => {
    el.addEventListener('click', () => {
      transportMode = el.dataset.transport;
      renderCloudCli(container, ctx);
    });
  });

  container.querySelectorAll('[data-preset-args]').forEach((el) => {
    el.addEventListener('click', () => {
      const argStr = el.dataset.presetArgs;
      const input = container.querySelector('#cli-args-input');
      if (input) input.value = argStr;
      runArgs(argStr);
    });
  });

  container.querySelector('#btn-cli-run')?.addEventListener('click', () => {
    const val = container.querySelector('#cli-args-input').value;
    runArgs(val);
  });

  container.querySelector('#btn-test-injection')?.addEventListener('click', () => {
    runArgs('account show; rm -rf /');
  });

  container.querySelector('#btn-test-prod-delete')?.addEventListener('click', () => {
    const cmd =
      selectedProvider === 'az'
        ? 'group delete --name rg-aegis-payments-prod'
        : selectedProvider === 'gcloud'
          ? 'compute instances delete gce-prod-core-01'
          : 'ec2 terminate-instances --instance-ids prod-01';
    runArgs(cmd, { allow_destructive: true, dry_run: false });
  });

  container.querySelector('#btn-cli-export')?.addEventListener('click', () => {
    if (!lastResult) return;
    exportOrCopy(`syncro-cli-${lastResult.execution_id}.json`, prettyJson(lastResult), ctx.toast);
  });
}
