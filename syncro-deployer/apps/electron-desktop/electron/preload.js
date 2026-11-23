'use strict';

const { contextBridge, ipcRenderer } = require('electron');

/**
 * Strictly scoped preload bridge exposed at window.syncroDesktop.
 * Keeps nodeIntegration disabled and isolates renderer context completely.
 */
contextBridge.exposeInMainWorld('syncroDesktop', {
  isElectron: true,
  platform: process.platform,
  arch: process.arch,
  getSystemInfo: () => ipcRenderer.invoke('syncro:system-info'),
  windowAction: (action) => ipcRenderer.invoke('syncro:window-action', action),
  exportFile: (defaultName, content) =>
    ipcRenderer.invoke('syncro:export-file', { defaultName, content }),
  notify: (title, body) => ipcRenderer.invoke('syncro:notify', { title, body }),
  openExternal: (url) => ipcRenderer.invoke('syncro:open-external', url),
});
