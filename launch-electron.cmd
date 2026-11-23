@echo off
title Syncro Deployer — Native Electron Desktop Workbench
cd /d "%~dp0syncro-deployer\apps\electron-desktop"
if not exist "dist\index.html" (
  call npm run build
)
start "" "%~dp0syncro-deployer\apps\electron-desktop\node_modules\electron\dist\electron.exe" .
