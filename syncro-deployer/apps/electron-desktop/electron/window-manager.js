'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { app, BrowserWindow, screen } = require('electron');

const POPOUT_TITLES = {
  'cloud-cli': 'Syncro Cloud CLI Studio (az · gcloud · aws)',
  mcp: 'Syncro MCP Tool Console (34 Tools)',
  deployer: 'Syncro Deployer Pipeline',
  'vm-finops': 'Syncro Multi-Cloud VM & FinOps Matrix',
  security: 'Syncro DevSecOps & Quick Destroy',
  bot: 'Syncro Guardrailed Ops Bot',
  telemetry: 'Syncro Live Telemetry & Audit Stream',
};

/**
 * Manages the primary desktop workbench window, persistent OS window bounds,
 * native platform materials (Windows Mica / macOS Vibrancy), boot splash screen,
 * and independent detached OS pop-out windows.
 */
class WindowManager {
  constructor({ devUrl, iconPath }) {
    this.devUrl = devUrl;
    this.iconPath = iconPath;
    this.mainWindow = null;
    this.splashWindow = null;
    this.popouts = new Map();
    this._stateFile = path.join(app.getPath('userData'), 'syncro-window-state.json');
  }

  _loadBounds() {
    const fallback = { width: 1500, height: 940, isMaximized: false };
    try {
      if (!fs.existsSync(this._stateFile)) return fallback;
      const saved = JSON.parse(fs.readFileSync(this._stateFile, 'utf8'));
      const displays = screen.getAllDisplays();
      const visible = displays.some((d) => {
        const b = d.workArea;
        return (
          typeof saved.x === 'number' &&
          typeof saved.y === 'number' &&
          saved.x >= b.x - 100 &&
          saved.x < b.x + b.width &&
          saved.y >= b.y - 50 &&
          saved.y < b.y + b.height
        );
      });
      return {
        x: visible ? saved.x : undefined,
        y: visible ? saved.y : undefined,
        width: Math.max(1080, Number(saved.width) || fallback.width),
        height: Math.max(700, Number(saved.height) || fallback.height),
        isMaximized: Boolean(saved.isMaximized),
      };
    } catch {
      return fallback;
    }
  }

  _saveBounds(win) {
    if (!win || win.isDestroyed()) return;
    try {
      const isMaximized = win.isMaximized();
      const bounds = isMaximized ? win.getNormalBounds() : win.getBounds();
      fs.writeFileSync(
        this._stateFile,
        JSON.stringify({ ...bounds, isMaximized }, null, 2),
        'utf8'
      );
    } catch {
      // Ignore userData write failure
    }
  }

  _platformChromeOptions() {
    if (process.platform === 'darwin') {
      return {
        frame: true,
        titleBarStyle: 'hiddenInset',
        trafficLightPosition: { x: 14, y: 12 },
        vibrancy: 'under-window',
        visualEffectState: 'active',
      };
    }
    if (process.platform === 'win32') {
      return {
        frame: false,
        titleBarStyle: 'hidden',
        backgroundMaterial: 'mica',
      };
    }
    return {
      frame: false,
      titleBarStyle: 'hidden',
    };
  }

  _loadRendererTarget(win, queryParams = {}) {
    const distIndex = path.resolve(__dirname, '..', 'dist', 'index.html');
    const useDev = (!app.isPackaged && process.env.SYNCRO_DEV === '1') || !fs.existsSync(distIndex);
    if (useDev) {
      const url = new URL(this.devUrl);
      for (const [k, v] of Object.entries(queryParams)) {
        url.searchParams.set(k, String(v));
      }
      win.loadURL(url.toString());
    } else {
      win.loadFile(distIndex, { query: queryParams });
    }
  }

  createSplashWindow() {
    this.splashWindow = new BrowserWindow({
      width: 360,
      height: 230,
      frame: false,
      transparent: false,
      resizable: false,
      center: true,
      alwaysOnTop: true,
      skipTaskbar: true,
      backgroundColor: '#0d1117',
      icon: this.iconPath,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });
    this.splashWindow.loadFile(path.join(__dirname, 'splash.html'));
    return this.splashWindow;
  }

  closeSplash() {
    if (this.splashWindow && !this.splashWindow.isDestroyed()) {
      this.splashWindow.close();
      this.splashWindow = null;
    }
  }

  createMainWindow() {
    const saved = this._loadBounds();
    const win = new BrowserWindow({
      x: saved.x,
      y: saved.y,
      width: saved.width,
      height: saved.height,
      minWidth: 1060,
      minHeight: 680,
      show: false,
      backgroundColor: '#0E1217',
      title: 'Syncro Deployer — Multi-Cloud DevSecOps & Cloud CLI MCP',
      icon: this.iconPath,
      autoHideMenuBar: process.platform !== 'darwin',
      ...this._platformChromeOptions(),
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        spellcheck: false,
      },
    });

    this.mainWindow = win;
    this._loadRendererTarget(win);

    win.once('ready-to-show', () => {
      this.closeSplash();
      if (saved.isMaximized) win.maximize();
      win.show();
      win.focus();
    });

    const persist = () => this._saveBounds(win);
    win.on('resize', persist);
    win.on('move', persist);
    win.on('maximize', () => {
      persist();
      win.webContents.send('syncro:window-state', { maximized: true, alwaysOnTop: win.isAlwaysOnTop() });
    });
    win.on('unmaximize', () => {
      persist();
      win.webContents.send('syncro:window-state', { maximized: false, alwaysOnTop: win.isAlwaysOnTop() });
    });

    win.on('closed', () => {
      this.mainWindow = null;
    });

    return win;
  }

  openPopoutWindow(viewId, { width = 1120, height = 760, alwaysOnTop = false } = {}) {
    const normalized = POPOUT_TITLES[viewId] ? viewId : 'cloud-cli';
    const existing = this.popouts.get(normalized);
    if (existing && !existing.isDestroyed()) {
      existing.show();
      existing.focus();
      return { opened: true, reused: true, viewId: normalized, count: this.popouts.size };
    }

    const title = POPOUT_TITLES[normalized];
    const pop = new BrowserWindow({
      width,
      height,
      minWidth: 760,
      minHeight: 500,
      show: false,
      alwaysOnTop: Boolean(alwaysOnTop),
      backgroundColor: '#0E1217',
      title,
      icon: this.iconPath,
      autoHideMenuBar: true,
      ...this._platformChromeOptions(),
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        spellcheck: false,
      },
    });

    this.popouts.set(normalized, pop);
    this._loadRendererTarget(pop, { popout: normalized });

    pop.once('ready-to-show', () => {
      pop.show();
      pop.focus();
    });

    pop.on('closed', () => {
      this.popouts.delete(normalized);
      this.broadcastPopoutCount();
    });

    this.broadcastPopoutCount();
    return { opened: true, reused: false, viewId: normalized, count: this.popouts.size };
  }

  broadcastPopoutCount() {
    const openPopouts = Array.from(this.popouts.keys());
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send('syncro:popouts-changed', { openPopouts });
    }
  }

  broadcastCommand(command, payload = {}) {
    const target = BrowserWindow.getFocusedWindow() || this.mainWindow;
    if (target && !target.isDestroyed()) {
      target.webContents.send('syncro:menu-command', { command, payload });
    }
  }

  listOpenWindows() {
    return {
      mainOpen: Boolean(this.mainWindow && !this.mainWindow.isDestroyed()),
      popouts: Array.from(this.popouts.keys()),
    };
  }
}

module.exports = { WindowManager, POPOUT_TITLES };
