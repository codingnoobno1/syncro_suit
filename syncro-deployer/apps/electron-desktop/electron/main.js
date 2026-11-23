'use strict';

const path = require('node:path');
const fs = require('node:fs');
const { app, Tray, Menu, nativeImage } = require('electron');
const { BackendManager } = require('./backend-manager');
const { WindowManager } = require('./window-manager');
const { installApplicationMenu } = require('./menu');
const { registerIpcHandlers } = require('./ipc-handlers');

const DEV_URL = process.env.SYNCRO_RENDERER_URL || 'http://127.0.0.1:5175';
const API_HOST = process.env.SYNCRO_API_HOST || '127.0.0.1';
const API_PORT = Number(process.env.SYNCRO_API_PORT || 8080);

let tray = null;
let windowManager = null;
const backendManager = new BackendManager({ host: API_HOST, port: API_PORT });

function resolveAppIcon() {
  const candidates = [
    path.join(__dirname, '..', 'build-assets', 'icon.png'),
    process.resourcesPath ? path.join(process.resourcesPath, 'icon.png') : null,
  ].filter(Boolean);
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return undefined;
}

function createTray() {
  const iconPath = resolveAppIcon();
  if (!iconPath || !windowManager) return;
  try {
    const img = nativeImage.createFromPath(iconPath).resize({ width: 18, height: 18 });
    tray = new Tray(img);
    tray.setToolTip('Syncro Deployer — Multi-Cloud DevSecOps & Cloud CLI MCP');
    tray.setContextMenu(
      Menu.buildFromTemplate([
        {
          label: 'Open Syncro Workbench',
          click: () => {
            if (!windowManager.mainWindow) windowManager.createMainWindow();
            else {
              windowManager.mainWindow.show();
              windowManager.mainWindow.focus();
            }
          },
        },
        { type: 'separator' },
        {
          label: 'Pop Out Cloud CLI Terminal (az · gcloud · aws)',
          click: () => windowManager.openPopoutWindow('cloud-cli'),
        },
        {
          label: 'Pop Out MCP Tool Console (34 Tools)',
          click: () => windowManager.openPopoutWindow('mcp'),
        },
        {
          label: 'Pop Out Live Telemetry Monitor',
          click: () => windowManager.openPopoutWindow('telemetry', { width: 920, height: 520, alwaysOnTop: true }),
        },
        { type: 'separator' },
        {
          label: 'Quit Syncro Deployer',
          click: () => app.quit(),
        },
      ])
    );
  } catch {
    // Headless or unsupported desktop tray
  }
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (windowManager?.mainWindow) {
      if (windowManager.mainWindow.isMinimized()) windowManager.mainWindow.restore();
      windowManager.mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    windowManager = new WindowManager({ devUrl: DEV_URL, iconPath: resolveAppIcon() });
    windowManager.createSplashWindow();

    await backendManager.ensureRunning();
    registerIpcHandlers({ windowManager, backendManager });
    installApplicationMenu({ windowManager });
    windowManager.createMainWindow();
    createTray();

    app.on('activate', () => {
      if (!windowManager.mainWindow) {
        windowManager.createMainWindow();
      }
    });
  });

  app.on('before-quit', () => {
    backendManager.stop();
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      app.quit();
    }
  });
}
