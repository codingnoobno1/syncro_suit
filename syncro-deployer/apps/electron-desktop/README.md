# Syncro Deployer — Native Multi-Window Electron.js Desktop App

Standalone native desktop application for **Syncro Deployer / AegisOps** (Windows, Linux, macOS) — built as a 5-zone desktop IDE/workbench with separate pop-out OS windows, Windows 11 Mica / macOS Vibrancy chrome, persistent window bounds, native OS menus & right-click context menus, automatic Python Control Plane sidecar lifecycle, and a compiled C99 native library (`.so` / `.dll` / `.dylib`).

## Native Desktop Capabilities

- **True Multi-Window Architecture (`electron/window-manager.js`)**: Detach **Cloud CLI Studio**, **MCP Tool Console**, **Live Telemetry Monitor**, **Syncro Deployer**, **VM Matrix**, **DevSecOps**, or **Ops Bot** into independent OS windows (`Ctrl+N`, `Ctrl+Shift+M`, `Ctrl+Shift+T`, tray menu, or tab right-click), each with its own Always-on-Top pin (`Alt+Shift+P`).
- **Native OS Integration**: Platform-native Application Menu (`File · Edit · View · Cloud · Window · Help`), native right-click `Menu.popup()`, native directory picker for local IaC scanning, native Save dialogs for SARIF/Terraform/PowerShell exports, system tray quick-launchers, native boot splash screen, and persistent multi-monitor window bounds.
- **5-Zone Desktop IDE Ergonomics**:
  1. Integrated Titlebar + Menu Bar + Command Palette (`Ctrl/Cmd+K`) + Layout Controls
  2. 46px Activity Bar (`Ctrl+1..7`)
  3. Resizable Explorer Tree (Projects, Multi-Cloud AWS/GCP/Azure Fleet, Cloud CLI Wrappers, Detached Windows)
  4. Multi-Tab Workbench + Resizable Right Property Inspector (`Ctrl+Shift+I`)
  5. 4-Tab Bottom Dock (`Live Stream` · `Quick Cloud CLI` · `Tri-Broker Fabric` · `Native Runtime`) + 24px Native Status Bar

## Launch Directly as a Native Desktop Window (No Browser)

### Windows (PowerShell)
```powershell
cd syncro-deployer\apps\electron-desktop
.\scripts\launch-desktop.ps1
```

### Linux / macOS
```bash
cd syncro-deployer/apps/electron-desktop
bash scripts/launch-desktop.sh
```

## Platform Packaging (`.exe`, `.so`, `.AppImage`, `.deb`, `.rpm`, `.tar.gz`, `.dmg`)

| Platform | Script | Output Artifacts |
| :--- | :--- | :--- |
| **Windows (`x64`)** | `pwsh -File scripts/package-platform.ps1` | NSIS `.exe`, Portable `.exe`, `.zip`, `syncro_native.dll`, `SHA256SUMS.txt` |
| **Linux (`x64`)** | `bash scripts/package-platform.sh` | `.AppImage`, `.deb`, `.rpm`, `.tar.gz`, `libsyncro_native.so`, `SHA256SUMS.txt` |
| **macOS (`x64` / `arm64`)** | `bash scripts/package-platform.sh` | `.dmg`, `.zip`, `.tar.gz`, `libsyncro_native.dylib`, `SHA256SUMS.txt` |
