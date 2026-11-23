import { api, connectLiveWebSocket, setApiBaseUrl } from './api/client.js';
import { esc } from './utils/format.js';
import { renderBotStudio } from './views/bot-studio.js';
import { renderCloudCli } from './views/cloud-cli.js';
import { renderDeployer } from './views/deployer.js';
import { renderMcpConsole } from './views/mcp-console.js';
import { renderOverview } from './views/overview.js';
import { renderSecurityOps } from './views/security-ops.js';
import { renderVmFinops } from './views/vm-finops.js';

const VIEWS = {
  overview: { title: 'Command Overview', render: renderOverview },
  'cloud-cli': { title: 'Cloud CLI Studio (az / gcloud / aws)', render: renderCloudCli },
  mcp: { title: 'MCP Tool Console (34 Tools)', render: renderMcpConsole },
  deployer: { title: 'Syncro Deployer', render: renderDeployer },
  'vm-finops': { title: 'VM & FinOps Matrix', render: renderVmFinops },
  security: { title: 'DevSecOps & Quick Destroy', render: renderSecurityOps },
  bot: { title: 'Guardrailed Ops Bot', render: renderBotStudio },
};

const state = {
  currentView: 'overview',
  mode: 'agentic',
  health: null,
  systemInfo: null,
  events: [],
};

const viewStage = document.querySelector('#view-stage');
const streamList = document.querySelector('#drawer-stream-list');
const eventCountEl = document.querySelector('#drawer-event-count');
const wsStatusEl = document.querySelector('#drawer-ws-status');
const connDot = document.querySelector('#conn-dot');
const connLabel = document.querySelector('#conn-label');
const paletteBackdrop = document.querySelector('#palette-backdrop');
const paletteInput = document.querySelector('#palette-input');
const paletteResults = document.querySelector('#palette-results');

function toast(message) {
  const stack = document.querySelector('#toast-stack');
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 3400);
}

function pushLocalEvent(type, detail) {
  const ts = new Date().toTimeString().slice(0, 8);
  state.events.unshift({ ts, type, detail });
  if (state.events.length > 80) state.events.pop();
  renderStream();
}

function renderStream() {
  eventCountEl.textContent = `${state.events.length} events`;
  streamList.innerHTML =
    state.events
      .map(
        (e) => `
          <div class="stream-line">
            <span class="stream-time">${esc(e.ts)}</span>
            <span class="stream-type">${esc(e.type)}</span>
            <span>${esc(e.detail)}</span>
          </div>
        `
      )
      .join('') || '<div class="stream-line"><span class="stream-time">--:--:--</span><span class="stream-type">system</span><span>Awaiting live Kafka/Redis telemetry...</span></div>';
}

const ctx = {
  state,
  toast,
  pushLocalEvent,
  navigate,
  reloadCurrentView: () => navigate(state.currentView),
};

async function navigate(viewId) {
  if (!VIEWS[viewId]) return;
  state.currentView = viewId;

  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.view === viewId);
  });

  viewStage.innerHTML = '<div class="panel"><span class="panel-meta">Loading live telemetry...</span></div>';
  try {
    await VIEWS[viewId].render(viewStage, ctx);
  } catch (err) {
    viewStage.innerHTML = `
      <div class="panel">
        <div class="panel-head"><h2 class="panel-title">Control Plane Unreachable</h2></div>
        <p class="view-subtitle">${esc(err.message)}</p>
        <button type="button" class="btn btn-primary" id="btn-retry-view" style="margin-top:12px">Retry Connection</button>
      </div>
    `;
    viewStage.querySelector('#btn-retry-view')?.addEventListener('click', () => navigate(viewId));
  }
}

async function refreshHealth() {
  try {
    const h = await api.health();
    state.health = h;
    connDot.className = 'conn-dot online';
    connLabel.textContent = `Online · ${h.mode}`;
    const mcpCount = document.querySelector('#nav-mcp-count');
    if (mcpCount && h.mcp_tools_count) mcpCount.textContent = String(h.mcp_tools_count);

    document.querySelectorAll('#rail-cli-badges .cli-badge').forEach((badge) => {
      const cli = badge.dataset.cli;
      const meta = h.cloud_clis?.[cli];
      badge.classList.remove('live', 'sim');
      if (meta?.installed && meta?.execution_mode === 'live') {
        badge.classList.add('live');
        badge.title = `${cli}: installed (live)`;
      } else {
        badge.classList.add('sim');
        badge.title = `${cli}: guardrailed simulation ready`;
      }
    });
  } catch {
    connDot.className = 'conn-dot offline';
    connLabel.textContent = 'Offline';
  }
}

async function syncMode(mode) {
  try {
    await api.syncroSetMode(mode);
    state.mode = mode;
    document.querySelectorAll('.mode-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.mode === mode);
    });
    pushLocalEvent('syncro.mode', `Switched execution mode to ${mode.toUpperCase()}`);
    toast(`Execution mode set to ${mode.toUpperCase()}`);
    if (state.currentView === 'deployer' || state.currentView === 'overview') {
      navigate(state.currentView);
    }
  } catch (err) {
    toast(err.message);
  }
}

function buildPaletteItems() {
  return [
    ...Object.entries(VIEWS).map(([id, v]) => ({
      label: v.title,
      category: 'View',
      run: () => navigate(id),
    })),
    { label: 'Switch to Agentic Mode', category: 'Mode', run: () => syncMode('agentic') },
    { label: 'Switch to Manual DevOps Mode', category: 'Mode', run: () => syncMode('manual') },
    {
      label: 'Run Azure CLI: az vm list',
      category: 'Cloud CLI',
      run: async () => {
        await navigate('cloud-cli');
        document.querySelector('#cli-tab-az')?.click();
      },
    },
    {
      label: 'Run GCP CLI: gcloud compute instances list',
      category: 'Cloud CLI',
      run: async () => {
        await navigate('cloud-cli');
        document.querySelector('#cli-tab-gcloud')?.click();
      },
    },
    {
      label: 'Run AWS CLI: aws ec2 describe-instances',
      category: 'Cloud CLI',
      run: async () => {
        await navigate('cloud-cli');
        document.querySelector('#cli-tab-aws')?.click();
      },
    },
  ];
}

function openPalette() {
  paletteBackdrop.classList.remove('hidden');
  paletteInput.value = '';
  renderPaletteRows('');
  paletteInput.focus();
}

function closePalette() {
  paletteBackdrop.classList.add('hidden');
}

function renderPaletteRows(query) {
  const q = query.trim().toLowerCase();
  const items = buildPaletteItems().filter(
    (it) => !q || it.label.toLowerCase().includes(q) || it.category.toLowerCase().includes(q)
  );
  paletteResults.innerHTML = items
    .map(
      (it, idx) => `
        <button type="button" class="palette-row" data-pal-idx="${idx}">
          <span>${esc(it.label)}</span>
          <span class="tag">${esc(it.category)}</span>
        </button>
      `
    )
    .join('');

  paletteResults.querySelectorAll('[data-pal-idx]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.dataset.palIdx);
      closePalette();
      items[idx]?.run();
    });
  });
}

async function bootstrap() {
  // Wire native Electron IPC if running inside Electron Desktop
  if (window.syncroDesktop?.isElectron) {
    const info = await window.syncroDesktop.getSystemInfo();
    state.systemInfo = info;
    if (info.apiBaseUrl) setApiBaseUrl(info.apiBaseUrl);
    document.querySelector('#runtime-badge').textContent = `Electron ${info.electronVersion} · ${info.platform}/${info.arch}`;
    const libState = info.nativeLib?.found ? `${info.nativeLib.fileName} loaded` : 'pure-js fallback';
    document.querySelector('#rail-native-meta').textContent = `${info.hostname} · ${libState}`;

    document.querySelector('#win-min')?.addEventListener('click', () => window.syncroDesktop.windowAction('minimize'));
    document.querySelector('#win-max')?.addEventListener('click', () => window.syncroDesktop.windowAction('maximize'));
    document.querySelector('#win-close')?.addEventListener('click', () => window.syncroDesktop.windowAction('close'));
  } else {
    document.querySelector('#win-controls')?.classList.add('hidden');
    document.querySelector('#runtime-badge').textContent = 'Electron Renderer · Preview';
  }

  // Navigation rail
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => navigate(btn.dataset.view));
  });

  // Mode toggle
  document.querySelectorAll('.mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => syncMode(btn.dataset.mode));
  });

  // Telemetry drawer toggle & clear
  const drawer = document.querySelector('#telemetry-drawer');
  document.querySelector('#drawer-toggle')?.addEventListener('click', (ev) => {
    if (ev.target.closest('#btn-clear-stream')) return;
    drawer.classList.toggle('collapsed');
  });
  document.querySelector('#btn-clear-stream')?.addEventListener('click', () => {
    state.events = [];
    renderStream();
  });

  // Command palette shortcuts
  document.querySelector('#btn-open-palette')?.addEventListener('click', openPalette);
  paletteBackdrop.addEventListener('click', (ev) => {
    if (ev.target === paletteBackdrop) closePalette();
  });
  paletteInput.addEventListener('input', () => renderPaletteRows(paletteInput.value));
  window.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
      ev.preventDefault();
      openPalette();
    } else if (ev.key === 'Escape' && !paletteBackdrop.classList.contains('hidden')) {
      closePalette();
    }
  });

  renderStream();
  await refreshHealth();
  setInterval(refreshHealth, 15000);

  connectLiveWebSocket({
    onStatus: (st) => {
      wsStatusEl.textContent = `WS ${st}`;
    },
    onMessage: (msg) => {
      const type = msg.type || 'event';
      const detail = msg.command || msg.message || msg.environment_id || JSON.stringify(msg).slice(0, 110);
      pushLocalEvent(type, detail);
    },
  });

  pushLocalEvent('desktop.boot', 'Syncro Deployer Electron workbench initialized');
  await navigate('overview');
}

bootstrap();
