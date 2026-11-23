import { mcpCall } from '../api/client.js';
import { esc, exportOrCopy, prettyJson } from '../utils/format.js';

let selectedToolName = 'aegis_az_cli';
let lastMcpResponse = null;

function sampleArgsForTool(tool) {
  const presets = {
    aegis_az_cli: { args: ['vm', 'list'] },
    aegis_gcp_cli: { args: ['compute', 'instances', 'list'] },
    aegis_aws_cli: { args: ['ec2', 'describe-instances'], region: 'us-east-1' },
    aegis_cloud_cli_status: {},
    aegis_cloud_cli_history: { limit: 10 },
    aegis_security_scan: { project_id: 'payments-core' },
    aegis_vm_compare_clouds: { min_vcpu: 4, min_memory_gib: 16, require_confidential_compute: true },
    aegis_syncro_deploy: { project_id: 'edge-gateway', environment_name: 'electron-mcp-01', cloud: 'gcp', target_type: 'kubernetes' },
    aegis_bot_prompt: { prompt: 'Summarize live multi-cloud billing and savings' },
  };
  return presets[tool.name] || {};
}

export async function renderMcpConsole(container, ctx) {
  const [toolsRes, resourcesRes, promptsRes] = await Promise.all([
    mcpCall('tools/list'),
    mcpCall('resources/list'),
    mcpCall('prompts/list'),
  ]);

  const tools = toolsRes.tools || [];
  const resources = resourcesRes.resources || [];
  const prompts = promptsRes.prompts || [];
  const currentTool = tools.find((t) => t.name === selectedToolName) || tools[0];

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>MCP Tool Console</h1>
        <p class="view-subtitle">
          Direct JSON-RPC 2.0 Model Context Protocol inspector — <strong>${tools.length} tools</strong>, <strong>${resources.length} resources</strong>, and <strong>${prompts.length} prompts</strong>.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn" id="btn-mcp-copy-config">Copy MCP Host Config</button>
      </div>
    </div>

    <div class="split-wide">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">Registered MCP Tools</h2>
          <span class="panel-meta">${tools.length}</span>
        </div>
        <div class="field" style="margin-bottom:10px">
          <input id="mcp-filter-input" class="input" type="text" placeholder="Filter tools (cli, syncro, bot, vm...)" />
        </div>
        <div class="preset-list" id="mcp-tool-list">
          ${tools
            .map(
              (t) => `
                <button type="button" class="preset-item ${t.name === currentTool?.name ? 'active' : ''}" data-tool-name="${esc(t.name)}">
                  <div class="preset-cmd">${esc(t.name)}</div>
                  <div class="preset-desc">${esc(t.description)}</div>
                </button>
              `
            )
            .join('')}
        </div>
      </section>

      <div style="display:flex; flex-direction:column; gap:16px">
        <section class="panel">
          <div class="panel-head">
            <h2 class="panel-title">${esc(currentTool?.name || 'Select tool')}</h2>
            <span class="tag tag-accent">JSON-RPC 2.0 · POST /mcp</span>
          </div>
          <p class="view-subtitle" style="margin-bottom:12px">${esc(currentTool?.description || '')}</p>

          <div class="field" style="margin-bottom:12px">
            <label for="mcp-args-textarea">Tool Arguments (JSON)</label>
            <textarea id="mcp-args-textarea" class="textarea" rows="5">${esc(
              prettyJson(sampleArgsForTool(currentTool || { name: '' }))
            )}</textarea>
          </div>

          <div style="display:flex; gap:8px; margin-bottom:14px">
            <button type="button" class="btn btn-primary" id="btn-mcp-invoke">Invoke tools/call</button>
            <button type="button" class="btn" id="btn-mcp-read-cli-res">Read aegis://cli/status</button>
            <button type="button" class="btn" id="btn-mcp-get-diag-prompt">Get CLI Diagnostics Prompt</button>
          </div>

          <div class="terminal-box">
            <div class="terminal-bar">
              <span>MCP Response Payload</span>
              <button type="button" class="btn-ghost btn-xs" id="btn-mcp-export">Export</button>
            </div>
            <pre class="terminal-pre" id="mcp-response-pre">${esc(
              lastMcpResponse ? prettyJson(lastMcpResponse) : 'Invoke any MCP tool or resource to inspect live JSON-RPC responses.'
            )}</pre>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2 class="panel-title">MCP Resources (${resources.length})</h2>
            <span class="panel-meta">Click any URI to read</span>
          </div>
          <div style="display:flex; flex-wrap:wrap; gap:6px">
            ${resources
              .map(
                (r) => `
                  <button type="button" class="btn btn-xs mono" data-res-uri="${esc(r.uri)}">
                    ${esc(r.uri)}
                  </button>
                `
              )
              .join('')}
          </div>
        </section>
      </div>
    </div>
  `;

  container.querySelector('#mcp-filter-input')?.addEventListener('input', (ev) => {
    const q = ev.target.value.toLowerCase();
    container.querySelectorAll('[data-tool-name]').forEach((btn) => {
      const match =
        btn.dataset.toolName.toLowerCase().includes(q) || btn.textContent.toLowerCase().includes(q);
      btn.classList.toggle('hidden', !match);
    });
  });

  container.querySelectorAll('[data-tool-name]').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectedToolName = btn.dataset.toolName;
      renderMcpConsole(container, ctx);
    });
  });

  container.querySelector('#btn-mcp-invoke')?.addEventListener('click', async () => {
    try {
      const parsedArgs = JSON.parse(container.querySelector('#mcp-args-textarea').value || '{}');
      const res = await mcpCall('tools/call', { name: currentTool.name, arguments: parsedArgs });
      const unwrapped = res?.content?.[0]?.text ? JSON.parse(res.content[0].text) : res;
      lastMcpResponse = unwrapped;
      container.querySelector('#mcp-response-pre').textContent = prettyJson(unwrapped);
      ctx.pushLocalEvent('mcp.tools/call', `${currentTool.name} succeeded`);
    } catch (err) {
      ctx.toast(`MCP invocation failed: ${err.message}`);
    }
  });

  container.querySelector('#btn-mcp-read-cli-res')?.addEventListener('click', async () => {
    try {
      const res = await mcpCall('resources/read', { uri: 'aegis://cli/status' });
      lastMcpResponse = JSON.parse(res.contents[0].text);
      container.querySelector('#mcp-response-pre').textContent = prettyJson(lastMcpResponse);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelector('#btn-mcp-get-diag-prompt')?.addEventListener('click', async () => {
    try {
      const res = await mcpCall('prompts/get', {
        name: 'multicloud_cli_diagnostics',
        arguments: { focus: 'compute, locks, and billing' },
      });
      lastMcpResponse = res;
      container.querySelector('#mcp-response-pre').textContent = prettyJson(res);
    } catch (err) {
      ctx.toast(err.message);
    }
  });

  container.querySelectorAll('[data-res-uri]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await mcpCall('resources/read', { uri: btn.dataset.resUri });
        lastMcpResponse = JSON.parse(res.contents[0].text);
        container.querySelector('#mcp-response-pre').textContent = prettyJson(lastMcpResponse);
        ctx.toast(`Loaded ${btn.dataset.resUri}`);
      } catch (err) {
        ctx.toast(err.message);
      }
    });
  });

  container.querySelector('#btn-mcp-copy-config')?.addEventListener('click', () => {
    const cfg = prettyJson({
      mcpServers: {
        syncro_deployer: {
          command: 'syncro',
          args: ['mcp', 'serve', '--transport', 'stdio'],
          httpFallback: 'http://127.0.0.1:8080/mcp',
        },
      },
    });
    exportOrCopy('mcp-host-config.json', cfg, ctx.toast);
  });

  container.querySelector('#btn-mcp-export')?.addEventListener('click', () => {
    if (!lastMcpResponse) return;
    exportOrCopy(`mcp-${selectedToolName}.json`, prettyJson(lastMcpResponse), ctx.toast);
  });
}
