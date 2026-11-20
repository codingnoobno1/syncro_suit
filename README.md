# Syncro Suite (`syncro_suit`)

Unified multi-cloud developer & DevSecOps suite referencing **[project-syncroo.netlify.app](https://project-syncroo.netlify.app)**.

## Suite Modules

| Module | Location / Integration | Status |
| :--- | :--- | :--- |
| **Syncro Deployer** | [`syncro-deployer/`](syncro-deployer/) — Multi-Cloud (AWS · GCP · Azure) Control Plane, Guardrailed MCP Ops Bot, SQLite WAL + Circuit Breakers + Auto-Rollback | Active |
| **Syncro Desktop** | [`syncro-deployer/apps/syncro-desktop/`](syncro-deployer/apps/syncro-desktop/) — Cross-Platform Flutter Desktop Agent (**Agentic Mode** & **Manual DevOps Mode**) | Active |
| **Syncro CLI** | [`syncro-deployer/services/control-plane/`](syncro-deployer/services/control-plane/) — `syncro` & `aegis` CLI entrypoints | Active |
| **Syncro IDE** | MCP JSON-RPC 2.0 Server (**29 tools**, **13 resources**) over `stdio` & HTTP `/mcp` | Connected |
| **Syncro DB** | SQLite WAL State Journal, Redis distributed locks & Kafka CloudEvents audit backbone | Active |
| **Syncro Git** | [`syncro-deployer/extensions/ts-policy-webhook/`](syncro-deployer/extensions/ts-policy-webhook/) — GitOps PR admission webhook & ephemeral PR environments | Active |
| **Syncro Tester** | Automated canary load, chaos & E2E verification gate (`pre_promote_test_gate` contract) | Planned |

## Quick Start on Windows (`D:\syncro_suit`)

```powershell
git clone https://github.com/codingnoobno1/syncro_suit.git D:\syncro_suit

# 1. Start the Syncro Deployer Control Plane (Python 3.11+)
cd D:\syncro_suit\syncro-deployer\services\control-plane
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\syncro.exe server --host 127.0.0.1 --port 8080

# 2. Launch the Flutter Desktop Agent (in a second terminal)
cd D:\syncro_suit\syncro-deployer\apps\syncro-desktop
flutter create . --platforms=windows,macos,linux
flutter pub get
flutter run -d windows --dart-define=SYNCRO_API_URL=http://127.0.0.1:8080
```
