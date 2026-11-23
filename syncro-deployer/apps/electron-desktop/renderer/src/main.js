import { api, connectLiveWebSocket, setApiBaseUrl } from './api/client.js';
import { cloudTag, esc, prettyJson, statusTag } from './utils/format.js';
import { renderBotStudio } from './views/bot-studio.js';
import { renderCloudCli, setSelectedCliProvider } from './views/cloud-cli.js';
import { renderDeployer } from './views/deployer.js';
import { renderMcpConsole } from './views/mcp-console.js';
import { renderOverview } from './views/overview.js';
import { renderSecurityOps } from './views/security-ops.js';
import { renderVmFinops } from './views/vm-finops.js';

const VIEWS = {
  overview: { title: 'Command Overview', short: 'Overview', render: renderOverview },
  'cloud-cli': { title: 'Cloud CLI Studio', short: 'Cloud CLI', render: renderCloudCli },
  mcp: { title: 'MCP Tool Console', short: 'MCP Console', render: renderMcpConsole },
  deployer: { title: 'Syncro Deployer', short: 'Deployer', render: renderDeployer },
  'vm-finops': { title: 'VM & FinOps Matrix', short: 'VM Matrix', render: renderVmFinops },
  security: { title: 'DevSecOps & Destroy', short: 'DevSecOps', render: renderSecurityOps },
  bot: { title: 'Guardrailed Ops Bot', short: 'Ops Bot', render: renderBotStudio },
};

const params = new URLSearchParams(window.location.search);
const popoutView = params.get('popout');

const state = {
  popoutView,
  currentView: popoutView && VIEWS[popoutView] ? popoutView : 'overview',
  openTabs: [popoutView && VIEWS[popoutView] ? popoutView : 'overview'],
  dockTab: 'stream',
  mode: 'agentic',
  health: null,
  systemInfo: null,
  projects: [],
  environments: [],
  events: [],
  openPopouts: [],
  pinned: false,
  explorerHidden: false,
  inspectorHidden: false,
  dockCollapsed: false,
};

const appEl = document.querySelector('#app');
const workbenchBody = document.querySelector('#workbench-body');
const centerColumn = document.querySelector('#center-column');
const tabStrip = document.querySelector('#tab-strip');
const viewStage = document.querySelector('#view-stage');
const dockContent = document.querySelector('#dock-content');
const explorerTree = document.querySelector('#explorer-tree');
const inspectorBody = document.querySelector('#inspector-body');
const menuPopover = document.querySelector('#menu-popover');
const contextMenuEl = document.querySelector('#context-menu');
const paletteBackdrop = document.querySelector('#palette-backdrop');
const paletteInput = document.querySelector('#palette-input');
const paletteResults = document.querySelector('#palette-results');

function toast(message) {
  const stack = document.querySelector('#toast-stack');
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function pushLocalEvent(type, detail) {
  const ts = new Date().toTimeString().slice(0, 8);
  state.events.unshift({ ts, type, detail });
  if (state.events.length > 100) state.events.pop();
  document.querySelector('#drawer-event-count').textContent = String(state.events.length);
  if (state.dockTab === 'stream') renderBottomDock();
  if (state.popoutView === 'telemetry') renderTelemetryPopout();
}

function inspectEntity(kind, title, data, actions = []) {
  if (state.inspectorHidden) {
    state.inspectorHidden = false;
    applyPaneClasses();
  }
  const summaryEntries = Object.entries(data || {})
    .filter(([, v]) => v !== null && typeof v !== 'object')
    .slice(0, 10);

  inspectorBody.innerHTML = `
    <div class="insp-header">
      <div class="panel-meta" style="text-transform:uppercase">${esc(kind)}</div>
      <h3 class="insp-title">${esc(title)}</h3>
    </div>
    ${
      actions.length > 0
        ? `<div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px">
            ${actions
              .map(
                (a, idx) =>
                  `<button type="button" class="btn btn-xs ${a.primary ? 'btn-primary' : ''}" data-insp-act="${idx}">${esc(a.label)}</button>`
              )
              .join('')}
          </div>`
        : ''
    }
    <div class="insp-kv">
      ${summaryEntries
        .map(([k, v]) => `<span class="insp-k">${esc(k)}</span><span class="insp-v">${esc(v)}</span>`)
        .join('')}
    </div>
    <div class="terminal-box">
      <div class="terminal-bar"><span>Raw JSON</span></div>
      <pre class="terminal-pre" style="max-height:360px">${esc(prettyJson(data))}</pre>
    </div>
  `;

  inspectorBody.querySelectorAll('[data-insp-act]').forEach((btn) => {
    btn.addEventListener('click', () => actions[Number(btn.dataset.inspAct)]?.run());
  });
}

async function openPopout(viewId, opts = {}) {
  if (window.syncroDesktop?.openPopout) {
    const res = await window.syncroDesktop.openPopout(viewId, opts);
    if (res?.opened) {
      toast(`Opened separate native window: ${viewId}`);
      return;
    }
  }
  const url = new URL(window.location.href);
  url.searchParams.set('popout', viewId);
  const w = opts.width || 1100;
  const h = opts.height || 740;
  const popup = window.open(url.toString(), `syncro-${viewId}`, `popup=yes,width=${w},height=${h},resizable=yes`);
  if (!popup) {
    toast('Browser blocked popup — allow popups or run in native Electron desktop.');
  } else {
    toast(`Detached separate window: ${viewId}`);
  }
}

async function showContextMenu(mouseEvent, items) {
  if (window.syncroDesktop?.showContextMenu) {
    return window.syncroDesktop.showContextMenu(items);
  }
  return new Promise((resolve) => {
    contextMenuEl.innerHTML = items
      .map((it, idx) =>
        it.type === 'separator'
          ? '<div class="menu-sep"></div>'
          : `<button type="button" class="menu-row" data-ctx-idx="${idx}">${esc(it.label)}</button>`
      )
      .join('');
    contextMenuEl.style.left = `${Math.min(mouseEvent.clientX, window.innerWidth - 230)}px`;
    contextMenuEl.style.top = `${Math.min(mouseEvent.clientY, window.innerHeight - 200)}px`;
    contextMenuEl.classList.remove('hidden');

    const cleanup = (value) => {
      contextMenuEl.classList.add('hidden');
      document.removeEventListener('click', outside);
      resolve(value);
    };
    const outside = () => cleanup(null);
    setTimeout(() => document.addEventListener('click', outside), 0);

    contextMenuEl.querySelectorAll('[data-ctx-idx]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        cleanup(items[Number(btn.dataset.ctxIdx)]?.id || null);
      });
    });
  });
}

function applyPaneClasses() {
  workbenchBody.classList.toggle('explorer-hidden', state.explorerHidden);
  workbenchBody.classList.toggle('inspector-hidden', state.inspectorHidden);
  centerColumn.classList.toggle('dock-collapsed', state.dockCollapsed);
  document.querySelector('#btn-toggle-explorer')?.classList.toggle('active', !state.explorerHidden);
  document.querySelector('#btn-toggle-inspector')?.classList.toggle('active', !state.inspectorHidden);
  document.querySelector('#btn-toggle-drawer')?.classList.toggle('active', !state.dockCollapsed);
}

function renderTabs() {
  tabStrip.innerHTML = state.openTabs
    .map((id) => {
      const v = VIEWS[id];
      if (!v) return '';
      return `
        <div class="editor-tab ${id === state.currentView ? 'active' : ''}" data-tab-id="${esc(id)}" role="tab">
          <span>${esc(v.short)}</span>
          ${
            state.openTabs.length > 1
              ? `<button type="button" class="tab-close" data-close-tab="${esc(id)}" aria-label="Close ${esc(v.short)}">&#10005;</button>`
              : ''
          }
        </div>
      `;
    })
    .join('');

  tabStrip.querySelectorAll('[data-tab-id]').forEach((tab) => {
    tab.addEventListener('click', (ev) => {
      if (ev.target.closest('[data-close-tab]')) return;
      navigate(tab.dataset.tabId);
    });
    tab.addEventListener('contextmenu', (ev) => {
      ev.preventDefault();
      const id = tab.dataset.tabId;
      showContextMenu(ev, [
        { id: 'popout', label: `Pop Out "${VIEWS[id].short}" into Separate Window` },
        { id: 'close', label: 'Close Tab', enabled: state.openTabs.length > 1 },
      ]).then((picked) => {
        if (picked === 'popout') openPopout(id);
        else if (picked === 'close') closeTab(id);
      });
    });
  });

  tabStrip.querySelectorAll('[data-close-tab]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      closeTab(btn.dataset.closeTab);
    });
  });
}

function closeTab(viewId) {
  if (state.openTabs.length <= 1) return;
  state.openTabs = state.openTabs.filter((t) => t !== viewId);
  if (state.currentView === viewId) {
    navigate(state.openTabs[state.openTabs.length - 1]);
  } else {
    renderTabs();
  }
}

async function renderExplorerTree() {
  try {
    const [projects, environments] = await Promise.all([api.projects(), api.environments()]);
    state.projects = projects;
    state.environments = environments;
  } catch {
    return;
  }

  const byCloud = { aws: [], gcp: [], azure: [] };
  for (const e of state.environments) {
    if (byCloud[e.cloud]) byCloud[e.cloud].push(e);
  }

  explorerTree.innerHTML = `
    <div class="tree-section">
      <button type="button" class="tree-section-head"><span>Projects (${state.projects.length})</span><span>&#9662;</span></button>
      <div class="tree-items">
        ${state.projects
          .map(
            (p) => `
              <button type="button" class="tree-row" data-tree-proj="${esc(p.id)}">
                <span class="tree-dot" style="background:var(--accent)"></span>
                <span class="tree-row-name">${esc(p.name)}</span>
                <span class="panel-meta">${esc(p.primary_language)}</span>
              </button>
            `
          )
          .join('')}
      </div>
    </div>

    <div class="tree-section">
      <button type="button" class="tree-section-head"><span>Multi-Cloud Fleet (${state.environments.length})</span><span>&#9662;</span></button>
      <div class="tree-items">
        ${['aws', 'gcp', 'azure']
          .flatMap((c) =>
            byCloud[c].map(
              (e) => `
                <button type="button" class="tree-row" data-tree-env="${esc(e.id)}">
                  <span class="tree-dot" style="background:${c === 'aws' ? 'var(--cloud-aws)' : c === 'gcp' ? 'var(--cloud-gcp)' : 'var(--cloud-azure)'}"></span>
                  <span class="tree-row-name">${esc(e.name)}</span>
                  <span class="panel-meta">${e.has_delete_lock ? 'LOCK' : esc(c)}</span>
                </button>
              `
            )
          )
          .join('')}
      </div>
    </div>

    <div class="tree-section">
      <button type="button" class="tree-section-head"><span>Cloud CLI Wrappers</span><span>&#9662;</span></button>
      <div class="tree-items">
        <button type="button" class="tree-row" data-tree-cli="az"><span class="tree-dot" style="background:var(--cloud-azure)"></span><span class="tree-row-name">Azure CLI (az)</span><span class="panel-meta">MCP</span></button>
        <button type="button" class="tree-row" data-tree-cli="gcloud"><span class="tree-dot" style="background:var(--cloud-gcp)"></span><span class="tree-row-name">GCP CLI (gcloud)</span><span class="panel-meta">MCP</span></button>
        <button type="button" class="tree-row" data-tree-cli="aws"><span class="tree-dot" style="background:var(--cloud-aws)"></span><span class="tree-row-name">AWS CLI (aws)</span><span class="panel-meta">MCP</span></button>
      </div>
    </div>

    <div class="tree-section">
      <button type="button" class="tree-section-head"><span>Detached Windows</span><span>&#9662;</span></button>
      <div class="tree-items">
        <button type="button" class="tree-row" data-tree-pop="cloud-cli"><span class="tree-row-name">Pop Out Cloud CLI Terminal</span><span class="panel-meta">&#8599;</span></button>
        <button type="button" class="tree-row" data-tree-pop="mcp"><span class="tree-row-name">Pop Out MCP Console</span><span class="panel-meta">&#8599;</span></button>
        <button type="button" class="tree-row" data-tree-pop="telemetry"><span class="tree-row-name">Pop Out Live Telemetry</span><span class="panel-meta">&#8599;</span></button>
        <button type="button" class="tree-row" data-tree-pop="deployer"><span class="tree-row-name">Pop Out Deployer</span><span class="panel-meta">&#8599;</span></button>
      </div>
    </div>
  `;

  explorerTree.querySelectorAll('.tree-section-head').forEach((head) => {
    head.addEventListener('click', () => head.parentElement.classList.toggle('collapsed'));
  });

  explorerTree.querySelectorAll('[data-tree-proj]').forEach((btn) => {
    const p = state.projects.find((x) => x.id === btn.dataset.treeProj);
    if (p) btn.addEventListener('click', () => inspectEntity('Project', p.name, p));
  });

  explorerTree.querySelectorAll('[data-tree-env]').forEach((btn) => {
    const e = state.environments.find((x) => x.id === btn.dataset.treeEnv);
    if (!e) return;
    btn.addEventListener('click', () =>
      inspectEntity('Environment', e.name, e, [
        { label: 'Run Drift Check', primary: true, run: async () => inspectEntity('Drift Report', e.name, await api.driftCheck(e.id)) },
        { label: 'Open Cloud CLI', run: () => openCliProvider(e.cloud === 'gcp' ? 'gcloud' : e.cloud === 'azure' ? 'az' : 'aws') },
      ])
    );
  });

  explorerTree.querySelectorAll('[data-tree-cli]').forEach((btn) => {
    btn.addEventListener('click', () => openCliProvider(btn.dataset.treeCli));
  });

  explorerTree.querySelectorAll('[data-tree-pop]').forEach((btn) => {
    btn.addEventListener('click', () => openPopout(btn.dataset.treePop));
  });
}

async function renderBottomDock() {
  if (state.dockCollapsed) return;
  if (state.dockTab === 'stream') {
    dockContent.innerHTML =
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
    return;
  }

  if (state.dockTab === 'quick-cli') {
    dockContent.innerHTML = `
      <div style="display:flex; gap:6px; margin-bottom:8px">
        <select id="qcli-prov" class="select" style="width:110px">
          <option value="az">az</option>
          <option value="gcloud">gcloud</option>
          <option value="aws">aws</option>
        </select>
        <input id="qcli-args" class="input" value="account show" placeholder="Subcommand args (e.g. vm list, sts get-caller-identity)" />
        <button type="button" class="btn btn-primary btn-xs" id="qcli-run">Run</button>
      </div>
      <pre id="qcli-out" style="margin:0; color:var(--text-secondary); white-space:pre-wrap">Type any guardrailed az / gcloud / aws subcommand and press Enter.</pre>
    `;
    const execQuick = async () => {
      const prov = dockContent.querySelector('#qcli-prov').value;
      const args = dockContent.querySelector('#qcli-args').value.trim().split(/\s+/).filter(Boolean);
      const outEl = dockContent.querySelector('#qcli-out');
      try {
        const res = await api.cliExec({ provider: prov, args, actor: 'electron-quick-terminal' });
        outEl.textContent = `${res.command_preview} [exit ${res.exit_code}, ${res.mode}, ${res.duration_ms}ms]\n${res.stdout || res.stderr}`;
      } catch (err) {
        outEl.textContent = `Error: ${err.message}`;
      }
    };
    dockContent.querySelector('#qcli-run')?.addEventListener('click', execQuick);
    dockContent.querySelector('#qcli-args')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') execQuick();
    });
    return;
  }

  if (state.dockTab === 'brokers') {
    try {
      const b = await api.brokersHealth();
      dockContent.innerHTML = `<pre style="margin:0; white-space:pre-wrap">${esc(prettyJson(b))}</pre>`;
    } catch (err) {
      dockContent.textContent = err.message;
    }
    return;
  }

  if (state.dockTab === 'runtime') {
    const info = state.systemInfo || {
      runtime: 'electron-renderer-preview',
      note: 'Launch via Electron desktop (.exe / .AppImage / npm start) for direct OS IPC, native .so/.dll/.dylib, and multi-monitor windows.',
    };
    dockContent.innerHTML = `<pre style="margin:0; white-space:pre-wrap">${esc(prettyJson(info))}</pre>`;
  }
}

function renderTelemetryPopout() {
  viewStage.innerHTML = `
    <div class="view-header">
      <div>
        <h1>Live Telemetry &amp; CloudEvents Monitor</h1>
        <p class="view-subtitle">Detached real-time Kafka, Redis Pub/Sub, Cloud CLI, and Syncro Deployer event stream.</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn btn-xs" id="btn-pop-clear">Clear</button>
      </div>
    </div>
    <div class="terminal-box">
      <div class="terminal-bar"><span>ws://.../ws/events</span><span>${state.events.length} events</span></div>
      <pre class="terminal-pre" style="max-height:70vh">${esc(
        state.events.map((e) => `[${e.ts}] ${e.type.padEnd(20)} ${e.detail}`).join('\n') || 'Waiting for live events...'
      )}</pre>
    </div>
  `;
  viewStage.querySelector('#btn-pop-clear')?.addEventListener('click', () => {
    state.events = [];
    renderTelemetryPopout();
  });
}

async function openCliProvider(provider) {
  setSelectedCliProvider(provider);
  await navigate('cloud-cli');
}

const ctx = {
  state,
  toast,
  pushLocalEvent,
  inspectEntity,
  openPopout,
  showContextMenu,
  openCliProvider,
  navigate,
  reloadCurrentView: () => navigate(state.currentView),
};

async function navigate(viewId) {
  if (state.popoutView === 'telemetry') {
    renderTelemetryPopout();
    return;
  }
  if (!VIEWS[viewId]) return;
  state.currentView = viewId;
  if (!state.openTabs.includes(viewId)) {
    state.openTabs.push(viewId);
  }
  renderTabs();

  document.querySelectorAll('.activity-btn[data-view]').forEach((btn) => {
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
        <button type="button" class="btn btn-primary" id="btn-retry-view" style="margin-top:10px">Retry Connection</button>
      </div>
    `;
    viewStage.querySelector('#btn-retry-view')?.addEventListener('click', () => navigate(viewId));
  }
}

async function refreshHealth() {
  const connDot = document.querySelector('#conn-dot');
  const connLabel = document.querySelector('#conn-label');
  try {
    const h = await api.health();
    state.health = h;
    connDot.className = 'conn-dot online';
    connLabel.textContent = `Control Plane :8080 (${h.mode})`;
    document.querySelector('#sb-mcp').textContent = `MCP: ${h.mcp_tools_count ?? 34} Tools`;
  } catch {
    connDot.className = 'conn-dot offline';
    connLabel.textContent = 'Control Plane Offline';
  }
}

async function syncMode(mode) {
  try {
    await api.syncroSetMode(mode);
    state.mode = mode;
    document.querySelectorAll('.mode-btn').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
    document.querySelector('#sb-mode').textContent = `MODE: ${mode.toUpperCase()}`;
    pushLocalEvent('syncro.mode', `Execution mode -> ${mode.toUpperCase()}`);
    toast(`Switched to ${mode.toUpperCase()} mode`);
    if (state.currentView === 'deployer' || state.currentView === 'overview') navigate(state.currentView);
  } catch (err) {
    toast(err.message);
  }
}

function setupMenubar() {
  const menus = {
    file: [
      { label: 'New Cloud CLI Window', hint: 'Ctrl+N', run: () => openPopout('cloud-cli') },
      { label: 'New MCP Console Window', hint: 'Ctrl+Shift+M', run: () => openPopout('mcp') },
      { label: 'New Live Telemetry Window', hint: 'Ctrl+Shift+T', run: () => openPopout('telemetry', { width: 920, height: 520, alwaysOnTop: true }) },
      { type: 'sep' },
      { label: 'Command Palette...', hint: 'Ctrl+K', run: () => openPalette() },
    ],
    view: [
      { label: 'Toggle Explorer Sidebar', hint: 'Ctrl+B', run: () => { state.explorerHidden = !state.explorerHidden; applyPaneClasses(); } },
      { label: 'Toggle Right Inspector', hint: 'Ctrl+Shift+I', run: () => { state.inspectorHidden = !state.inspectorHidden; applyPaneClasses(); } },
      { label: 'Toggle Bottom Dock', hint: 'Ctrl+J', run: () => { state.dockCollapsed = !state.dockCollapsed; applyPaneClasses(); renderBottomDock(); } },
      { type: 'sep' },
      { label: 'Refresh Active View', hint: 'F5', run: () => navigate(state.currentView) },
    ],
    cloud: [
      { label: 'Azure CLI (az) Studio', run: () => openCliProvider('az') },
      { label: 'GCP CLI (gcloud) Studio', run: () => openCliProvider('gcloud') },
      { label: 'AWS CLI (aws) Studio', run: () => openCliProvider('aws') },
      { type: 'sep' },
      { label: 'Agentic Autopilot Mode', run: () => syncMode('agentic') },
      { label: 'Manual DevOps Gate Mode', run: () => syncMode('manual') },
    ],
    window: [
      { label: 'Pop Out Current View', run: () => openPopout(state.currentView) },
      { label: 'Toggle Always On Top', hint: 'Alt+Shift+P', run: () => togglePin() },
      { label: 'Reset Pane Layout', run: () => { state.explorerHidden = false; state.inspectorHidden = false; state.dockCollapsed = false; applyPaneClasses(); } },
    ],
  };

  let activeMenu = null;
  function closeMenu() {
    menuPopover.classList.add('hidden');
    document.querySelectorAll('.menubar-btn').forEach((b) => b.classList.remove('open'));
    activeMenu = null;
  }

  document.querySelectorAll('.menubar-btn').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const id = btn.dataset.menu;
      if (activeMenu === id) {
        closeMenu();
        return;
      }
      activeMenu = id;
      document.querySelectorAll('.menubar-btn').forEach((b) => b.classList.toggle('open', b.dataset.menu === id));
      const rect = btn.getBoundingClientRect();
      const items = menus[id] || [];
      menuPopover.innerHTML = items
        .map((it, i) =>
          it.type === 'sep'
            ? '<div class="menu-sep"></div>'
            : `<button type="button" class="menu-row" data-m-idx="${i}"><span>${esc(it.label)}</span>${it.hint ? `<span class="panel-meta">${esc(it.hint)}</span>` : ''}</button>`
        )
        .join('');
      menuPopover.style.left = `${rect.left}px`;
      menuPopover.style.top = `${rect.bottom + 2}px`;
      menuPopover.classList.remove('hidden');

      menuPopover.querySelectorAll('[data-m-idx]').forEach((row) => {
        row.addEventListener('click', () => {
          const fn = items[Number(row.dataset.mIdx)]?.run;
          closeMenu();
          fn?.();
        });
      });
    });
  });

  document.addEventListener('click', closeMenu);
}

async function togglePin() {
  if (window.syncroDesktop?.windowAction) {
    const res = await window.syncroDesktop.windowAction('toggle-pin');
    state.pinned = Boolean(res?.alwaysOnTop);
    document.querySelector('#btn-pin-window')?.classList.toggle('active', state.pinned);
    toast(state.pinned ? 'Window pinned Always On Top' : 'Window unpinned');
  } else {
    toast('Always On Top is available in the standalone Electron desktop app.');
  }
}

function setupSplitters() {
  const bindVertical = (el, cssVar, invert = false) => {
    if (!el) return;
    el.addEventListener('mousedown', (ev) => {
      ev.preventDefault();
      el.classList.add('dragging');
      const startX = ev.clientX;
      const startW = parseInt(getComputedStyle(document.documentElement).getPropertyValue(cssVar), 10) || 260;
      const onMove = (m) => {
        const delta = invert ? startX - m.clientX : m.clientX - startX;
        const next = Math.max(180, Math.min(460, startW + delta));
        document.documentElement.style.setProperty(cssVar, `${next}px`);
      };
      const onUp = () => {
        el.classList.remove('dragging');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    });
  };

  bindVertical(document.querySelector('#splitter-left'), '--explorer-width', false);
  bindVertical(document.querySelector('#splitter-right'), '--inspector-width', true);

  const bottomSplitter = document.querySelector('#splitter-bottom');
  bottomSplitter?.addEventListener('mousedown', (ev) => {
    ev.preventDefault();
    bottomSplitter.classList.add('dragging');
    const startY = ev.clientY;
    const startH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--dock-height'), 10) || 176;
    const onMove = (m) => {
      const next = Math.max(90, Math.min(420, startH + (startY - m.clientY)));
      document.documentElement.style.setProperty('--dock-height', `${next}px`);
    };
    const onUp = () => {
      bottomSplitter.classList.remove('dragging');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  });
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
  const items = [
    ...Object.entries(VIEWS).map(([id, v]) => ({ label: `Open ${v.title}`, category: 'View', run: () => navigate(id) })),
    { label: 'Pop Out Cloud CLI Terminal (Separate Window)', category: 'Window', run: () => openPopout('cloud-cli') },
    { label: 'Pop Out MCP Tool Console (Separate Window)', category: 'Window', run: () => openPopout('mcp') },
    { label: 'Pop Out Live Telemetry Monitor (Separate Window)', category: 'Window', run: () => openPopout('telemetry', { width: 920, height: 520, alwaysOnTop: true }) },
    { label: 'Azure CLI (az) Studio', category: 'Cloud CLI', run: () => openCliProvider('az') },
    { label: 'GCP CLI (gcloud) Studio', category: 'Cloud CLI', run: () => openCliProvider('gcloud') },
    { label: 'AWS CLI (aws) Studio', category: 'Cloud CLI', run: () => openCliProvider('aws') },
    { label: 'Switch to Agentic Mode', category: 'Mode', run: () => syncMode('agentic') },
    { label: 'Switch to Manual DevOps Mode', category: 'Mode', run: () => syncMode('manual') },
  ].filter((it) => !q || it.label.toLowerCase().includes(q) || it.category.toLowerCase().includes(q));

  paletteResults.innerHTML = items
    .map((it, idx) => `<button type="button" class="palette-row" data-pal-idx="${idx}"><span>${esc(it.label)}</span><span class="tag">${esc(it.category)}</span></button>`)
    .join('');

  paletteResults.querySelectorAll('[data-pal-idx]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const fn = items[Number(btn.dataset.palIdx)]?.run;
      closePalette();
      fn?.();
    });
  });
}

async function bootstrap() {
  if (state.popoutView) {
    appEl.classList.add('popout-mode');
    state.dockCollapsed = true;
    const titleEl = document.querySelector('#titlebar-app-name');
    if (titleEl) {
      titleEl.textContent = VIEWS[state.popoutView]?.title || 'Live Telemetry Monitor';
    }
  }

  if (window.syncroDesktop?.isElectron) {
    if (window.syncroDesktop.platform === 'darwin') {
      appEl.classList.add('mac-chrome');
      document.querySelector('#win-controls')?.classList.add('hidden');
    }
    const info = await window.syncroDesktop.getSystemInfo();
    state.systemInfo = info;
    if (info.apiBaseUrl) setApiBaseUrl(info.apiBaseUrl);
    document.querySelector('#sb-native').textContent = info.nativeLib?.found ? `Native: ${info.nativeLib.fileName}` : 'Native: JS fallback';
    document.querySelector('#sb-host').textContent = `${info.platform}/${info.arch} · RAM ${info.usedMemPct}%`;

    document.querySelector('#win-min')?.addEventListener('click', () => window.syncroDesktop.windowAction('minimize'));
    document.querySelector('#win-max')?.addEventListener('click', () => window.syncroDesktop.windowAction('maximize'));
    document.querySelector('#win-close')?.addEventListener('click', () => window.syncroDesktop.windowAction('close'));

    window.syncroDesktop.onPopoutsChanged(({ openPopouts }) => {
      state.openPopouts = openPopouts || [];
      document.querySelector('#sb-popouts').textContent = `Windows: ${1 + state.openPopouts.length}`;
    });

    window.syncroDesktop.onMenuCommand(({ command, payload }) => {
      if (command === 'navigate') navigate(payload.view);
      else if (command === 'open-palette') openPalette();
      else if (command === 'toggle-explorer') { state.explorerHidden = !state.explorerHidden; applyPaneClasses(); }
      else if (command === 'toggle-inspector') { state.inspectorHidden = !state.inspectorHidden; applyPaneClasses(); }
      else if (command === 'toggle-drawer') { state.dockCollapsed = !state.dockCollapsed; applyPaneClasses(); renderBottomDock(); }
      else if (command === 'set-mode') syncMode(payload.mode);
      else if (command === 'open-cli-provider') openCliProvider(payload.provider);
      else if (command === 'toggle-pin') togglePin();
    });
  } else {
    document.querySelector('#win-controls')?.classList.add('hidden');
    document.querySelector('#sb-native').textContent = 'Native: libsyncro_native.so ready';
    document.querySelector('#sb-host').textContent = 'Desktop Preview';
  }

  setupMenubar();
  setupSplitters();
  applyPaneClasses();

  // Activity bar & chrome toolbar wiring
  document.querySelectorAll('.activity-btn[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => navigate(btn.dataset.view));
  });
  document.querySelector('#act-popout-cli')?.addEventListener('click', () => openPopout('cloud-cli'));
  document.querySelector('#btn-popout-current')?.addEventListener('click', () => openPopout(state.currentView));
  document.querySelector('#btn-popout-telemetry')?.addEventListener('click', () => openPopout('telemetry', { width: 920, height: 520, alwaysOnTop: true }));
  document.querySelector('#btn-pin-window')?.addEventListener('click', togglePin);

  document.querySelector('#btn-toggle-explorer')?.addEventListener('click', () => {
    state.explorerHidden = !state.explorerHidden;
    applyPaneClasses();
  });
  document.querySelector('#btn-toggle-inspector')?.addEventListener('click', () => {
    state.inspectorHidden = !state.inspectorHidden;
    applyPaneClasses();
  });
  document.querySelector('#btn-close-inspector')?.addEventListener('click', () => {
    state.inspectorHidden = true;
    applyPaneClasses();
  });
  document.querySelector('#btn-toggle-drawer')?.addEventListener('click', () => {
    state.dockCollapsed = !state.dockCollapsed;
    applyPaneClasses();
    renderBottomDock();
  });
  document.querySelector('#btn-dock-collapse')?.addEventListener('click', () => {
    state.dockCollapsed = !state.dockCollapsed;
    applyPaneClasses();
    renderBottomDock();
  });

  document.querySelectorAll('[data-dock-tab]').forEach((tab) => {
    tab.addEventListener('click', () => {
      state.dockTab = tab.dataset.dockTab;
      state.dockCollapsed = false;
      applyPaneClasses();
      document.querySelectorAll('[data-dock-tab]').forEach((t) => t.classList.toggle('active', t.dataset.dockTab === state.dockTab));
      renderBottomDock();
    });
  });

  document.querySelector('#btn-clear-stream')?.addEventListener('click', () => {
    state.events = [];
    document.querySelector('#drawer-event-count').textContent = '0';
    renderBottomDock();
  });

  document.querySelector('#btn-explorer-refresh')?.addEventListener('click', renderExplorerTree);
  document.querySelectorAll('.mode-btn').forEach((btn) => btn.addEventListener('click', () => syncMode(btn.dataset.mode)));

  // Command palette & desktop keyboard shortcuts
  document.querySelector('#btn-open-palette')?.addEventListener('click', openPalette);
  paletteBackdrop.addEventListener('click', (ev) => {
    if (ev.target === paletteBackdrop) closePalette();
  });
  paletteInput.addEventListener('input', () => renderPaletteRows(paletteInput.value));

  window.addEventListener('keydown', (ev) => {
    const mod = ev.ctrlKey || ev.metaKey;
    if (mod && ev.key.toLowerCase() === 'k') {
      ev.preventDefault();
      openPalette();
    } else if (mod && ev.key.toLowerCase() === 'b') {
      ev.preventDefault();
      state.explorerHidden = !state.explorerHidden;
      applyPaneClasses();
    } else if (mod && ev.key.toLowerCase() === 'j') {
      ev.preventDefault();
      state.dockCollapsed = !state.dockCollapsed;
      applyPaneClasses();
      renderBottomDock();
    } else if (mod && ev.shiftKey && ev.key.toLowerCase() === 'i') {
      ev.preventDefault();
      state.inspectorHidden = !state.inspectorHidden;
      applyPaneClasses();
    } else if (mod && ['1', '2', '3', '4', '5', '6', '7'].includes(ev.key)) {
      ev.preventDefault();
      const keys = Object.keys(VIEWS);
      navigate(keys[Number(ev.key) - 1]);
    } else if (ev.key === 'Escape' && !paletteBackdrop.classList.contains('hidden')) {
      closePalette();
    }
  });

  await refreshHealth();
  setInterval(refreshHealth, 15000);
  if (!state.popoutView) {
    await renderExplorerTree();
  }

  connectLiveWebSocket({
    onStatus: (st) => {
      document.querySelector('#sb-ws').textContent = `WS: ${st}`;
    },
    onMessage: (msg) => {
      const type = msg.type || 'event';
      const detail = msg.command || msg.message || msg.environment_id || JSON.stringify(msg).slice(0, 110);
      pushLocalEvent(type, detail);
    },
  });

  renderBottomDock();
  pushLocalEvent('desktop.boot', `Syncro native workbench ready (${state.popoutView || 'main window'})`);
  await navigate(state.currentView);
}

bootstrap();
