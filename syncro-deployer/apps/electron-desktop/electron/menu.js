'use strict';

const { app, Menu, shell } = require('electron');

/**
 * Installs a full OS-native application menu bar (File, Edit, View, Cloud CLI,
 * Window, Help) with platform accelerators routing straight into the workbench
 * and detached pop-out windows.
 */
function installApplicationMenu({ windowManager }) {
  const isMac = process.platform === 'darwin';
  const send = (command, payload = {}) => windowManager.broadcastCommand(command, payload);

  const template = [
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' },
              { type: 'separator' },
              { role: 'services' },
              { type: 'separator' },
              { role: 'hide' },
              { role: 'hideOthers' },
              { role: 'unhide' },
              { type: 'separator' },
              { role: 'quit' },
            ],
          },
        ]
      : []),
    {
      label: 'File',
      submenu: [
        {
          label: 'New Cloud CLI Window',
          accelerator: 'CmdOrCtrl+N',
          click: () => windowManager.openPopoutWindow('cloud-cli'),
        },
        {
          label: 'New MCP Tool Console Window',
          accelerator: 'CmdOrCtrl+Shift+M',
          click: () => windowManager.openPopoutWindow('mcp'),
        },
        {
          label: 'New Live Telemetry Window',
          accelerator: 'CmdOrCtrl+Shift+T',
          click: () => windowManager.openPopoutWindow('telemetry', { width: 920, height: 520, alwaysOnTop: true }),
        },
        { type: 'separator' },
        {
          label: 'Command Palette...',
          accelerator: 'CmdOrCtrl+K',
          click: () => send('open-palette'),
        },
        { type: 'separator' },
        isMac ? { role: 'close' } : { role: 'quit' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { label: 'Command Overview', accelerator: 'CmdOrCtrl+1', click: () => send('navigate', { view: 'overview' }) },
        { label: 'Cloud CLI Studio', accelerator: 'CmdOrCtrl+2', click: () => send('navigate', { view: 'cloud-cli' }) },
        { label: 'MCP Tool Console', accelerator: 'CmdOrCtrl+3', click: () => send('navigate', { view: 'mcp' }) },
        { label: 'Syncro Deployer', accelerator: 'CmdOrCtrl+4', click: () => send('navigate', { view: 'deployer' }) },
        { label: 'VM & FinOps Matrix', accelerator: 'CmdOrCtrl+5', click: () => send('navigate', { view: 'vm-finops' }) },
        { label: 'DevSecOps & Destroy', accelerator: 'CmdOrCtrl+6', click: () => send('navigate', { view: 'security' }) },
        { label: 'Guardrailed Ops Bot', accelerator: 'CmdOrCtrl+7', click: () => send('navigate', { view: 'bot' }) },
        { label: 'IaC Studio & Security MCP', accelerator: 'CmdOrCtrl+8', click: () => send('navigate', { view: 'iac-studio' }) },
        { type: 'separator' },
        { label: 'Toggle Explorer Sidebar', accelerator: 'CmdOrCtrl+B', click: () => send('toggle-explorer') },
        { label: 'Toggle Right Inspector', accelerator: 'CmdOrCtrl+Shift+I', click: () => send('toggle-inspector') },
        { label: 'Toggle Bottom Telemetry Dock', accelerator: 'CmdOrCtrl+J', click: () => send('toggle-drawer') },
        { type: 'separator' },
        { role: 'reload' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Cloud',
      submenu: [
        { label: 'Switch to Agentic Mode', accelerator: 'CmdOrCtrl+Shift+A', click: () => send('set-mode', { mode: 'agentic' }) },
        { label: 'Switch to Manual DevOps Mode', accelerator: 'CmdOrCtrl+Shift+D', click: () => send('set-mode', { mode: 'manual' }) },
        { type: 'separator' },
        { label: 'Azure CLI (az) Studio', click: () => send('open-cli-provider', { provider: 'az' }) },
        { label: 'GCP CLI (gcloud) Studio', click: () => send('open-cli-provider', { provider: 'gcloud' }) },
        { label: 'AWS CLI (aws) Studio', click: () => send('open-cli-provider', { provider: 'aws' }) },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        {
          label: 'Toggle Always On Top',
          accelerator: 'Alt+Shift+P',
          click: () => send('toggle-pin'),
        },
        ...(isMac ? [{ type: 'separator' }, { role: 'front' }] : [{ role: 'close' }]),
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Syncro Suite Repository (GitHub)',
          click: () => shell.openExternal('https://github.com/codingnoobno1/syncro_suit'),
        },
        {
          label: 'Syncro Suite Architecture Reference',
          click: () => shell.openExternal('https://project-syncroo.netlify.app'),
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

module.exports = { installApplicationMenu };
