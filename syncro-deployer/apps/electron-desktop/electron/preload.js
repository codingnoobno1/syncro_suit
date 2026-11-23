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
  openPopout: (viewId, opts = {}) =>
    ipcRenderer.invoke('syncro:open-popout', { viewId, ...opts }),
  listWindows: () => ipcRenderer.invoke('syncro:list-windows'),
  selectFolder: () => ipcRenderer.invoke('syncro:select-folder'),
  exportFile: (defaultName, content) =>
    ipcRenderer.invoke('syncro:export-file', { defaultName, content }),
  showContextMenu: (items) => ipcRenderer.invoke('syncro:context-menu', items),
  notify: (title, body) => ipcRenderer.invoke('syncro:notify', { title, body }),
  openExternal: (url) => ipcRenderer.invoke('syncro:open-external', url),
  onMenuCommand: (callback) => {
    const listener = (_, data) => callback(data);
    ipcRenderer.on('syncro:menu-command', listener);
    return () => ipcRenderer.removeListener('syncro:menu-command', listener);
  },
  onWindowState: (callback) => {
    const listener = (_, data) => callback(data);
    ipcRenderer.on('syncro:window-state', listener);
    return () => ipcRenderer.removeListener('syncro:window-state', listener);
  },
  onPopoutsChanged: (callback) => {
    const listener = (_, data) => callback(data);
    ipcRenderer.on('syncro:popouts-changed', listener);
    return () => ipcRenderer.removeListener('syncro:popouts-changed', listener);
  },
});
