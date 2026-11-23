# Syncro Suite (`syncro_suit`)

Unified multi-cloud developer & DevSecOps suite referencing **[project-syncroo.netlify.app](https://project-syncroo.netlify.app)**.

## Suite Modules

| Module | Location / Integration | Status |
| :--- | :--- | :--- |
| **Syncro Electron Desktop** | [`syncro-deployer/apps/electron-desktop/`](syncro-deployer/apps/electron-desktop/) — Cross-Platform Electron.js Desktop Workbench + Native `.so`/`.dll`/`.dylib` + Multi-Platform CI/CD (`.exe`, `.AppImage`, `.deb`, `.rpm`, `.tar.gz`, `.dmg`) | Active |
| **Syncro Deployer** | [`syncro-deployer/`](syncro-deployer/) — Multi-Cloud (AWS · GCP · Azure) Control Plane, Guardrailed `az`/`gcloud`/`aws` CLI Wrapper MCP (**34 tools**, **15 resources**, **6 prompts**), SQLite WAL + Circuit Breakers + Auto-Rollback | Active |
| **Syncro Desktop (Flutter)** | [`syncro-deployer/apps/syncro-desktop/`](syncro-deployer/apps/syncro-desktop/) — Cross-Platform Flutter Desktop Agent (**Agentic Mode** & **Manual DevOps Mode**) | Active |
| **Syncro CLI** | [`syncro-deployer/services/control-plane/`](syncro-deployer/services/control-plane/) — `syncro` & `aegis` CLI entrypoints including `syncro cloud-cli` | Active |
| **Syncro IDE** | MCP JSON-RPC 2.0 Server (**34 tools**, **15 resources**, **6 prompts**) over `stdio` & HTTP `/mcp` | Connected |
| **Syncro DB** | SQLite WAL State Journal, Redis distributed locks & Kafka CloudEvents audit backbone | Active |
| **Syncro Git** | [`syncro-deployer/extensions/ts-policy-webhook/`](syncro-deployer/extensions/ts-policy-webhook/) — GitOps PR admission webhook & ephemeral PR environments | Active |
| **Syncro Tester** | Automated canary load, chaos & E2E verification gate (`pre_promote_test_gate` contract) | Planned |

## Quick Start (Electron Desktop + Control Plane)

```bash
# 1. Start the hardened Syncro Control Plane + az/gcloud/aws CLI MCP Host (:8080)
cd syncro-deployer/services/control-plane
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/syncro server --host 127.0.0.1 --port 8080

# 2. Launch the Electron.js Desktop Frontend (second terminal)
cd syncro-deployer/apps/electron-desktop
npm install
npm run build
npm start
```

## Multi-Platform Packaging & CI/CD

GitHub Actions ([`.github/workflows/electron-release.yml`](.github/workflows/electron-release.yml)) automatically tests the backend + Cloud CLI MCP wrappers and packages platform artifacts on pushes and `v*` tags:
- **Windows (`x64`)**: NSIS `.exe`, Portable `.exe`, `.zip`, `syncro_native.dll`
- **Linux (`x64`)**: `.AppImage`, `.deb`, `.rpm`, `.tar.gz`, `libsyncro_native.so`
- **macOS (`x64` / `arm64`)**: `.dmg`, `.zip`, `.tar.gz`, `libsyncro_native.dylib`
