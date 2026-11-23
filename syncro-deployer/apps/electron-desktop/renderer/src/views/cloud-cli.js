import { api, mcpCall } from '../api/client.js';
import { cloudTag, esc, exportOrCopy, prettyJson, statusTag } from '../utils/format.js';

let selectedProvider = 'az';
let transportMode = 'mcp';
let outputTab = 'json'; // 'json' | 'raw' | 'guardrail' | 'snippet'
let lastResult = null;

export function setSelectedCliProvider(provider) {
  if (['az', 'gcloud', 'aws'].includes(provider)) {
    selectedProvider = provider;
  }
}

function parseArgString(raw) {
  const tokens = [];
  const regex = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let match;
  while ((match = regex.exec(raw)) !== null) {
    tokens.push(match[1] ?? match[2] ?? match[3]);
  }
  return tokens;
}

function renderOutputContent(result, provider) {
  if (!result) {
    return 'Select a curated recipe or type CLI subcommand arguments and click Execute.';
  }
  if (outputTab === 'raw') {
    const out = result.stdout ? `STDOUT:\n${result.stdout}` : 'STDOUT: (empty)';
    const err = result.stderr ? `\n\nSTDERR:\n${result.stderr}` : '';
    return `${out}${err}`;
  }
  if (outputTab === 'guardrail') {
    return prettyJson({
      execution_id: result.execution_id,
      command_preview: result.command_preview,
      mode: result.mode,
      risk_tier: result.risk_tier,
      exit_code: result.exit_code,
      duration_ms: result.duration_ms,
      binary_installed: result.binary_installed,
      binary_path: result.binary_path,
      guardrail: result.guardrail,
    });
  }
  if (outputTab === 'snippet') {
    const tool = provider === 'az' ? 'aegis_az_cli' : provider === 'gcloud' ? 'aegis_gcp_cli' : 'aegis_aws_cli';
    return prettyJson({
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: {
        name: tool,
        arguments: {
          args: (result.command || []).slice(1).filter((a) => !['--output', 'json', '--format=json'].includes(a)),
          dry_run: result.mode === 'dry_run',
        },
      },
    });
  }
  return prettyJson(result.parsed_json ?? result);
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
          Guardrailed native terminal for Azure (<code>az</code>), GCP (<code>gcloud</code>), and AWS (<code>aws</code>) over MCP JSON-RPC 2.0 or REST.
        </p>
      </div>
      <div class="header-actions">
        <div class="tab-bar" role="tablist" aria-label="Cloud CLI provider">
          <button type="button" class="tab-btn ${selectedProvider === 'az' ? 'active' : ''}" id="cli-tab-az" data-provider="az">Azure · az</button>
          <button type="button" class="tab-btn ${selectedProvider === 'gcloud' ? 'active' : ''}" id="cli-tab-gcloud" data-provider="gcloud">GCP · gcloud</button>
          <button type="button" class="tab-btn ${selectedProvider === 'aws' ? 'active' : ''}" id="cli-tab-aws" data-provider="aws">AWS · aws</button>
        </div>
        <div class="tab-bar" role="group" aria-label="Invocation transport">
          <button type="button" class="tab-btn ${transportMode === 'mcp' ? 'active' : ''}" id="cli-via-mcp" data-transport="mcp">MCP Tool</button>
          <button type="button" class="tab-btn ${transportMode === 'rest' ? 'active' : ''}" id="cli-via-rest" data-transport="rest">REST API</button>
        </div>
        <button type="button" class="btn" id="btn-cli-popout">Pop Out Window</button>
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

        <div style="margin-top:12px; padding-top:10px; border-top:1px solid var(--border-subtle)">
          <div class="panel-meta" style="margin-bottom:6px">ALLOWED SERVICE NAMESPACES</div>
          <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:10px">
            ${(provMeta.allowed_namespaces || [])
              .slice(0, 12)
              .map((ns) => `<span class="tag">${esc(ns)}</span>`)
              .join('')}
          </div>
          <div class="panel-meta" style="margin-bottom:6px">SECURITY GUARDRAIL VERIFICATION</div>
          <div style="display:flex; flex-direction:column; gap:5px">
            <button type="button" class="btn btn-danger btn-xs" id="btn-test-injection">Test Shell Injection Block</button>
            <button type="button" class="btn btn-danger btn-xs" id="btn-test-secret">Test Secret Exfiltration Block</button>
            <button type="button" class="btn btn-danger btn-xs" id="btn-test-prod-delete">Test Production Delete Block</button>
          </div>
        </div>
      </section>

      <div style="display:flex; flex-direction:column; gap:14px">
        <section class="panel">
          <div class="panel-head">
            <h2 class="panel-title">Argv Command Builder (${esc(selectedProvider)})</h2>
            <div style="display:flex; gap:6px; align-items:center">
              ${statusTag(provMeta.execution_mode || 'simulation')}
              <span class="panel-meta">${provMeta.installed ? `PATH: ${esc(provMeta.path)}` : 'Zero-shell simulator active'}</span>
            </div>
          </div>

          <div class="field-grid">
            <div class="field" style="grid-column: span 2">
              <label for="cli-args-input">Command Tokens (strict argv — shell interpolation disabled)</label>
              <input
                id="cli-args-input"
                class="input"
                type="text"
                value="${esc(filteredPresets[0]?.args.join(' ') || 'version')}"
                placeholder="e.g. vm list | compute instances list | ec2 describe-instances"
              />
            </div>
            <div class="field">
              <label for="cli-scope-input">${selectedProvider === 'az' ? 'Subscription ID' : selectedProvider === 'gcloud' ? 'GCP Project ID' : 'AWS Region'}</label>
              <input id="cli-scope-input" class="input" type="text" placeholder="Optional scope override" />
            </div>
          </div>

          <div class="check-row">
            <label class="check-item"><input type="checkbox" id="cli-dry-run" /><span>Dry-Run Preview</span></label>
            <label class="check-item"><input type="checkbox" id="cli-allow-destructive" /><span>Allow Ephemeral Destructive</span></label>
            <button type="button" class="btn btn-primary" id="btn-cli-run" style="margin-left:auto">
              Run ${esc(selectedProvider)} via ${transportMode.toUpperCase()}
            </button>
          </div>

          <div class="terminal-box">
            <div class="terminal-bar">
              <div style="display:flex; gap:4px; align-items:center; flex-wrap:wrap">
                <button type="button" class="btn-ghost btn-xs ${outputTab === 'json' ? 'tag-accent' : ''}" data-out-tab="json">Parsed JSON</button>
                <button type="button" class="btn-ghost btn-xs ${outputTab === 'raw' ? 'tag-accent' : ''}" data-out-tab="raw">Raw stdout/stderr</button>
                <button type="button" class="btn-ghost btn-xs ${outputTab === 'guardrail' ? 'tag-accent' : ''}" data-out-tab="guardrail">Guardrail Policy</button>
                <button type="button" class="btn-ghost btn-xs ${outputTab === 'snippet' ? 'tag-accent' : ''}" data-out-tab="snippet">MCP JSON-RPC</button>
              </div>
              <div style="display:flex; gap:6px; align-items:center">
                <span class="mono">${esc(lastResult?.duration_ms != null ? `${lastResult.duration_ms}ms` : '')}</span>
                ${lastResult ? statusTag(lastResult.mode) : ''}
                <button type="button" class="btn-ghost btn-xs" id="btn-cli-export">Save / Copy</button>
              </div>
            </div>
            <pre class="terminal-pre" id="cli-output-pre">${esc(renderOutputContent(lastResult, selectedProvider))}</pre>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2 class="panel-title">Audited CLI Execution Ledger</h2>
            <span class="panel-meta">Click any row to inspect or replay</span>
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
                  ? '<tr><td colspan="6" class="panel-meta">No CLI executions recorded yet.</td></tr>'
                  : history
                      .slice(0, 12)
                      .map(
                        (h, idx) => `
                          <tr data-hist-idx="${idx}">
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
          selectedProvider === 'az' ? 'aegis_az_cli' : selectedProvider === 'gcloud' ? 'aegis_gcp_cli' : 'aegis_aws_cli';
        const toolArgs = { args, dry_run: dryRun, allow_destructive: allowDestructive };
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
      ctx.inspectEntity('CLI Execution', result.command_preview, result);
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

  container.querySelectorAll('[data-out-tab]').forEach((el) => {
    el.addEventListener('click', () => {
      outputTab = el.dataset.outTab;
      renderCloudCli(container, ctx);
    });
  });

  container.querySelector('#btn-cli-popout')?.addEventListener('click', () => ctx.openPopout('cloud-cli'));

  container.querySelectorAll('[data-preset-args]').forEach((el) => {
    el.addEventListener('click', () => {
      const argStr = el.dataset.presetArgs;
      container.querySelector('#cli-args-input').value = argStr;
      runArgs(argStr);
    });
  });

  container.querySelector('#btn-cli-run')?.addEventListener('click', () => {
    runArgs(container.querySelector('#cli-args-input').value);
  });

  container.querySelector('#cli-args-input')?.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') runArgs(ev.target.value);
  });

  container.querySelector('#btn-test-injection')?.addEventListener('click', () => runArgs('account show; rm -rf /'));

  container.querySelector('#btn-test-secret')?.addEventListener('click', () => {
    const cmd =
      selectedProvider === 'az'
        ? 'keyvault secret show --vault-name prod-kv --name db-pass'
        : selectedProvider === 'gcloud'
          ? 'auth print-access-token'
          : 'secretsmanager get-secret-value --secret-id prod/db';
    runArgs(cmd);
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

  container.querySelectorAll('[data-hist-idx]').forEach((row) => {
    row.addEventListener('click', () => {
      const item = history[Number(row.dataset.histIdx)];
      if (!item) return;
      lastResult = item;
      ctx.inspectEntity('CLI Audit Record', item.command_preview, item);
      renderCloudCli(container, ctx);
    });
  });

  container.querySelector('#btn-cli-export')?.addEventListener('click', () => {
    if (!lastResult) return;
    exportOrCopy(`syncro-cli-${lastResult.execution_id}.json`, prettyJson(lastResult), ctx.toast);
  });
}
