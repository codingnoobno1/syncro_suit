'use strict';

const os = require('node:os');
const fs = require('node:fs');
const { execFile } = require('node:child_process');
const { BrowserWindow, Menu, ipcMain, dialog, Notification, shell } = require('electron');
const { resolveNativeLibraryPath } = require('./native-bridge');

const TRACKED_CLIS = [
  'az',
  'gcloud',
  'aws',
  'kubectl',
  'terraform',
  'docker',
  'helm',
  'ansible-playbook',
  'pwsh',
  'git',
];

function probeBinary(binName) {
  return new Promise((resolve) => {
    const locator = process.platform === 'win32' ? 'where' : 'which';
    execFile(locator, [binName], { timeout: 2500 }, (err, stdout) => {
      if (err || !stdout.trim()) {
        resolve({ name: binName, installed: false, path: null });
        return;
      }
      resolve({ name: binName, installed: true, path: stdout.trim().split(/\r?\n/)[0] });
    });
  });
}

function registerIpcHandlers({ windowManager, backendManager }) {
  ipcMain.handle('syncro:system-info', async () => {
    const probes = await Promise.all(TRACKED_CLIS.map(probeBinary));
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    const usedMemPct = totalMem > 0 ? Math.round(((totalMem - freeMem) / totalMem) * 100) : 0;

    return {
      runtime: 'electron',
      electronVersion: process.versions.electron,
      nodeVersion: process.versions.node,
      chromeVersion: process.versions.chrome,
      platform: process.platform,
      osRelease: os.release(),
      arch: process.arch,
      hostname: os.hostname(),
      cpus: os.cpus().length,
      cpuModel: os.cpus()[0]?.model || 'unknown',
      loadAvg1m: Number((os.loadavg()[0] || 0).toFixed(2)),
      totalMemGb: Number((totalMem / 1024 ** 3).toFixed(1)),
      freeMemGb: Number((freeMem / 1024 ** 3).toFixed(1)),
      usedMemPct,
      apiBaseUrl: backendManager.baseUrl,
      backendStatus: backendManager.lastStatus,
      nativeLib: resolveNativeLibraryPath(),
      localClis: probes,
      openWindows: windowManager.listOpenWindows(),
    };
  });

  ipcMain.handle('syncro:window-action', (event, action) => {
    const win = BrowserWindow.fromWebContents(event.sender) || windowManager.mainWindow;
    if (!win || win.isDestroyed()) return { ok: false };
    if (action === 'minimize') {
      win.minimize();
    } else if (action === 'maximize') {
      if (win.isMaximized()) win.unmaximize();
      else win.maximize();
    } else if (action === 'close') {
      win.close();
      return { ok: true, closed: true };
    } else if (action === 'toggle-pin') {
      const next = !win.isAlwaysOnTop();
      win.setAlwaysOnTop(next);
      return { ok: true, alwaysOnTop: next, maximized: win.isMaximized() };
    }
    return { ok: true, maximized: win.isMaximized(), alwaysOnTop: win.isAlwaysOnTop() };
  });

  ipcMain.handle('syncro:open-popout', (_, { viewId, width, height, alwaysOnTop }) => {
    return windowManager.openPopoutWindow(viewId, { width, height, alwaysOnTop });
  });

  ipcMain.handle('syncro:list-windows', () => {
    return windowManager.listOpenWindows();
  });

  ipcMain.handle('syncro:select-folder', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender) || windowManager.mainWindow;
    const res = await dialog.showOpenDialog(win, {
      title: 'Select Local Infrastructure / Project Directory',
      properties: ['openDirectory'],
    });
    if (res.canceled || !res.filePaths?.length) return { selected: false, path: null };
    return { selected: true, path: res.filePaths[0] };
  });

  ipcMain.handle('syncro:export-file', async (event, { defaultName, content }) => {
    const win = BrowserWindow.fromWebContents(event.sender) || windowManager.mainWindow;
    const res = await dialog.showSaveDialog(win, {
      title: 'Export Syncro Artifact',
      defaultPath: defaultName || 'syncro-export.json',
      filters: [
        { name: 'JSON / SARIF / Terraform / Script', extensions: ['json', 'sarif', 'tf', 'ps1', 'txt', 'md'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (res.canceled || !res.filePath) {
      return { saved: false };
    }
    fs.writeFileSync(res.filePath, String(content ?? ''), 'utf8');
    return { saved: true, filePath: res.filePath };
  });

  ipcMain.handle('syncro:context-menu', (event, items) => {
    return new Promise((resolve) => {
      const win = BrowserWindow.fromWebContents(event.sender);
      if (!win || win.isDestroyed() || !Array.isArray(items) || items.length === 0) {
        resolve(null);
        return;
      }
      let picked = null;
      const menu = Menu.buildFromTemplate(
        items.map((it) =>
          it.type === 'separator'
            ? { type: 'separator' }
            : {
                label: String(it.label || ''),
                enabled: it.enabled !== false,
                click: () => {
                  picked = it.id;
                },
              }
        )
      );
      menu.popup({
        window: win,
        callback: () => resolve(picked),
      });
    });
  });

  ipcMain.handle('syncro:notify', (_, { title, body }) => {
    if (Notification.isSupported()) {
      new Notification({ title: String(title || 'Syncro Deployer'), body: String(body || '') }).show();
      return { shown: true };
    }
    return { shown: false };
  });

  ipcMain.handle('syncro:open-external', async (_, url) => {
    const target = String(url || '');
    if (!target.startsWith('https://')) {
      return { opened: false, error: 'Only https:// URLs are permitted.' };
    }
    await shell.openExternal(target);
    return { opened: true };
  });
}

module.exports = { registerIpcHandlers, TRACKED_CLIS };
