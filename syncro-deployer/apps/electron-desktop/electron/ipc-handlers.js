'use strict';

const os = require('node:os');
const fs = require('node:fs');
const { execFile } = require('node:child_process');
const { ipcMain, dialog, Notification, shell } = require('node:electron');
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

function registerIpcHandlers({ getMainWindow, backendManager }) {
  ipcMain.handle('syncro:system-info', async () => {
    const probes = await Promise.all(TRACKED_CLIS.map(probeBinary));
    return {
      runtime: 'electron',
      electronVersion: process.versions.electron,
      nodeVersion: process.versions.node,
      chromeVersion: process.versions.chrome,
      platform: process.platform,
      arch: process.arch,
      hostname: os.hostname(),
      cpus: os.cpus().length,
      totalMemGb: Number((os.totalmem() / 1024 ** 3).toFixed(1)),
      freeMemGb: Number((os.freemem() / 1024 ** 3).toFixed(1)),
      apiBaseUrl: backendManager.baseUrl,
      backendStatus: backendManager.lastStatus,
      nativeLib: resolveNativeLibraryPath(),
      localClis: probes,
    };
  });

  ipcMain.handle('syncro:window-action', (_, action) => {
    const win = getMainWindow();
    if (!win) return { ok: false };
    if (action === 'minimize') win.minimize();
    else if (action === 'maximize') {
      if (win.isMaximized()) win.unmaximize();
      else win.maximize();
    } else if (action === 'close') win.close();
    return { ok: true, maximized: win.isMaximized() };
  });

  ipcMain.handle('syncro:export-file', async (_, { defaultName, content }) => {
    const win = getMainWindow();
    const res = await dialog.showSaveDialog(win, {
      title: 'Export Syncro Artifact',
      defaultPath: defaultName || 'syncro-export.json',
      filters: [
        { name: 'JSON / SARIF / Terraform / Text', extensions: ['json', 'sarif', 'tf', 'ps1', 'txt', 'md'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (res.canceled || !res.filePath) {
      return { saved: false };
    }
    fs.writeFileSync(res.filePath, String(content ?? ''), 'utf8');
    return { saved: true, filePath: res.filePath };
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
