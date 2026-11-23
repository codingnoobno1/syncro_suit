'use strict';

const path = require('node:path');
const fs = require('node:fs');
const { app, BrowserWindow, Tray, Menu, nativeImage } = require('electron');
const { BackendManager } = require('./backend-manager');
const { registerIpcHandlers } = require('./ipc-handlers');

const DEV_URL = process.env.SYNCRO_RENDERER_URL || 'http://127.0.0.1:5175';
const API_HOST = process.env.SYNCRO_API_HOST || '127.0.0.1';
const API_PORT = Number(process.env.SYNCRO_API_PORT || 8080);

let mainWindow = null;
let tray = null;
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

function createMainWindow() {
  const iconPath = resolveAppIcon();
  mainWindow = new BrowserWindow({
    width: 1460,
    height: 920,
    minWidth: 1040,
    minHeight: 680,
    backgroundColor: '#0E1217',
    title: 'Syncro Deployer — Multi-Cloud DevSecOps & Cloud CLI MCP',
    icon: iconPath,
    frame: process.platform === 'darwin',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'hidden',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  const distIndex = path.resolve(__dirname, '..', 'dist', 'index.html');
  if (!app.isPackaged && process.env.SYNCRO_DEV === '1') {
    mainWindow.loadURL(DEV_URL);
  } else if (fs.existsSync(distIndex)) {
    mainWindow.loadFile(distIndex);
  } else {
    mainWindow.loadURL(DEV_URL);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const iconPath = resolveAppIcon();
  if (!iconPath) return;
  try {
    const img = nativeImage.createFromPath(iconPath).resize({ width: 18, height: 18 });
    tray = new Tray(img);
    tray.setToolTip('Syncro Deployer Control Plane');
    tray.setContextMenu(
      Menu.buildFromTemplate([
        {
          label: 'Open Syncro Deployer',
          click: () => {
            if (!mainWindow) createMainWindow();
            else mainWindow.show();
          },
        },
        { type: 'separator' },
        {
          label: 'Quit Syncro Deployer',
          click: () => app.quit(),
        },
      ])
    );
  } catch {
    // Headless or unsupported desktop environment tray
  }
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    await backendManager.ensureRunning();
    registerIpcHandlers({ getMainWindow: () => mainWindow, backendManager });
    createMainWindow();
    createTray();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createMainWindow();
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
