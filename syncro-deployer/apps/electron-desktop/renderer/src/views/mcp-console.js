import { mcpCall } from '../api/client.js';
import { esc, exportOrCopy, prettyJson } from '../utils/format.js';

let selectedToolName = 'aegis_az_cli';
let selectedCategory = 'all';
let lastMcpResponse = null;
let lastLatencyMs = null;

function classifyTool(name) {
  if (name.includes('_cli')) return 'cli';
  if (name.includes('_syncro_')) return 'syncro';
  if (name.includes('_bot_')) return 'bot';
  if (name.includes('_vm_') || name.includes('finops')) return 'vm';
  return 'ops';
}

function sampleArgsForTool(tool) {
  const presets = {
    aegis_az_cli: { args: ['vm', 'list'] },
    aegis_gcp_cli: { args: ['compute', 'instances', 'list'] },
    aegis_aws_cli: { args: ['ec2', 'describe-instances'], region: 'us-east-1' },
    aegis_cloud_cli_status: {},
    aegis_cloud_cli_history: { limit: 15 },
    aegis_security_scan: { project_id: 'payments-core' },
    aegis_vm_compare_clouds: { min_vcpu: 4, min_memory_gib: 16, require_confidential_compute: true },
    aegis_syncro_deploy: { project_id: 'edge-gateway', environment_name: 'electron-mcp-01', cloud: 'gcp', target_type: 'kubernetes' },
    aegis_bot_prompt: { prompt: 'Summarize live multi-cloud billing and savings' },
  };
  return presets[tool?.name] || {};
}

export async function renderMcpConsole(container, ctx) {
  const [toolsRes, resourcesRes, promptsRes] = await Promise.all([
    mcpCall('tools/list'),
    mcpCall('resources/list'),
    mcpCall('prompts/list'),
  ]);

  const allTools = toolsRes.tools || [];
  const tools =
    selectedCategory === 'all' ? allTools : allTools.filter((t) => classifyTool(t.name) === selectedCategory);
  const resources = resourcesRes.resources || [];
  const prompts = promptsRes.prompts || [];
  const currentTool = allTools.find((t) => t.name === selectedToolName) || tools[0] || allTools[0];
  const schemaProps = Object.entries(currentTool?.inputSchema?.properties || {});
  const requiredSet = new Set(currentTool?.inputSchema?.required || []);

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1>MCP Tool Console</h1>
        <p class="view-subtitle">
          Live JSON-RPC 2.0 Model Context Protocol workbench — <strong>${allTools.length} tools</strong>, <strong>${resources.length} resources</strong>, <strong>${prompts.length} prompts</strong>.
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn" id="btn-mcp-copy-config">Export Host Config</button>
        <button type="button" class="btn" id="btn-mcp-popout">Pop Out Window</button>
      </div>
    </div>

    <div class="split-wide">
      <section class="panel">
        <div class="panel-head">
          <h2 class="panel-title">MCP Tools (${tools.length}/${allTools.length})</h2>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px">
          ${[
            ['all', 'All'],
            ['cli', 'Cloud CLI'],
            ['syncro', 'Deployer'],
            ['bot', 'Ops Bot'],
            ['vm', 'VM/FinOps'],
            ['ops', 'SecOps'],
          ]
            .map(
              ([cat, lbl]) => `
                <button type="button" class="btn btn-xs ${selectedCategory === cat ? 'btn-primary' : ''}" data-cat="${cat}">${lbl}</button>
              `
            )
            .join('')}
        </div>
        <div class="field" style="margin-bottom:8px">
          <input id="mcp-filter-input" class="input" type="text" placeholder="Search tools..." />
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

      <div style="display:flex; flex-direction:column; gap:14px">
        <section class="panel">
          <div class="panel-head">
            <h2 class="panel-title">${esc(currentTool?.name || 'Select tool')}</h2>
            <div style="display:flex; gap:6px; align-items:center">
              ${lastLatencyMs != null ? `<span class="tag tag-ok">${esc(lastLatencyMs)} ms</span>` : ''}
              <span class="tag tag-accent">JSON-RPC 2.0</span>
            </div>
          </div>
          <p class="view-subtitle" style="margin-bottom:10px">${esc(currentTool?.description || '')}</p>

          ${
            schemaProps.length > 0
              ? `
                <div style="margin-bottom:10px; display:flex; flex-wrap:wrap; gap:5px">
                  ${schemaProps
                    .map(
                      ([k, def]) =>
                        `<span class="tag ${requiredSet.has(k) ? 'tag-warn' : ''}">${esc(k)}${requiredSet.has(k) ? '*' : ''}: ${esc(def.type || 'any')}</span>`
                    )
                    .join('')}
                </div>
              `
              : ''
          }

          <div class="field" style="margin-bottom:10px">
            <label for="mcp-args-textarea">Arguments JSON Payload</label>
            <textarea id="mcp-args-textarea" class="textarea" rows="5">${esc(
              prettyJson(sampleArgsForTool(currentTool))
            )}</textarea>
          </div>

          <div style="display:flex; gap:7px; flex-wrap:wrap; margin-bottom:12px">
            <button type="button" class="btn btn-primary" id="btn-mcp-invoke">Invoke tools/call</button>
            <button type="button" class="btn" id="btn-mcp-inspect-schema">Inspect Schema</button>
            <button type="button" class="btn" id="btn-mcp-get-diag-prompt">Run CLI Diagnostics Prompt</button>
          </div>

          <div class="terminal-box">
            <div class="terminal-bar">
              <span>MCP Response Payload</span>
              <button type="button" class="btn-ghost btn-xs" id="btn-mcp-export">Save / Copy</button>
            </div>
            <pre class="terminal-pre" id="mcp-response-pre">${esc(
              lastMcpResponse ? prettyJson(lastMcpResponse) : 'Invoke any MCP tool, resource, or prompt to inspect live responses.'
            )}</pre>
          </div>
        </section>

        <div class="split-2">
          <section class="panel">
            <div class="panel-head">
              <h2 class="panel-title">MCP Resources (${resources.length})</h2>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:5px">
              ${resources
                .map((r) => `<button type="button" class="btn btn-xs mono" data-res-uri="${esc(r.uri)}">${esc(r.uri)}</button>`)
                .join('')}
            </div>
          </section>

          <section class="panel">
            <div class="panel-head">
              <h2 class="panel-title">MCP Prompt Templates (${prompts.length})</h2>
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:5px">
              ${prompts
                .map((p) => `<button type="button" class="btn btn-xs mono" data-prompt-name="${esc(p.name)}">${esc(p.name)}</button>`)
                .join('')}
            </div>
          </section>
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll('[data-cat]').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectedCategory = btn.dataset.cat;
      renderMcpConsole(container, ctx);
    });
  });

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

  container.querySelector('#btn-mcp-popout')?.addEventListener('click', () => ctx.openPopout('mcp'));

  container.querySelector('#btn-mcp-inspect-schema')?.addEventListener('click', () => {
    if (currentTool) ctx.inspectEntity('MCP Tool Schema', currentTool.name, currentTool);
  });

  container.querySelector('#btn-mcp-invoke')?.addEventListener('click', async () => {
    const t0 = performance.now();
    try {
      const parsedArgs = JSON.parse(container.querySelector('#mcp-args-textarea').value || '{}');
      const res = await mcpCall('tools/call', { name: currentTool.name, arguments: parsedArgs });
      lastLatencyMs = Math.round(performance.now() - t0);
      const unwrapped = res?.content?.[0]?.text ? JSON.parse(res.content[0].text) : res;
      lastMcpResponse = unwrapped;
      ctx.inspectEntity('MCP Result', currentTool.name, unwrapped);
      ctx.pushLocalEvent('mcp.tools/call', `${currentTool.name} (${lastLatencyMs}ms)`);
      await renderMcpConsole(container, ctx);
    } catch (err) {
      ctx.toast(`MCP invocation failed: ${err.message}`);
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
        ctx.toast(`Read ${btn.dataset.resUri}`);
      } catch (err) {
        ctx.toast(err.message);
      }
    });
  });

  container.querySelectorAll('[data-prompt-name]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        const res = await mcpCall('prompts/get', { name: btn.dataset.promptName, arguments: {} });
        lastMcpResponse = res;
        container.querySelector('#mcp-response-pre').textContent = prettyJson(res);
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
