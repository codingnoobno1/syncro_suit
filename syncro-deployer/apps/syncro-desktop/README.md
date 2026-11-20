# Syncro Desktop — Flutter Desktop Agent & Deployer Workbench

Part of the **Syncro Suite** ([project-syncroo.netlify.app](https://project-syncroo.netlify.app)):
`Syncro Desktop` · `Syncro Deployer` · `Syncro CLI` · `Syncro IDE` · `Syncro DB` · `Syncro Git` · `Syncro Tester (Roadmap)`

## Key Capabilities

- **Dual-Mode Desktop Switching**:
  - **Agentic Mode**: Autonomous Guardrailed MCP Bot, Live AWS/GCP/Azure Bill Reader, User-Defined Bill-Saving Self-Prompting, Automatic Canary Progression (`5% -> 25% -> 100%`) with SLO Auto-Rollback, and Prompt-Injection Firewall.
  - **Manual DevOps Mode**: Operator-controlled deployments across AWS/GCP/Azure VMs, Kubernetes, and Docker with explicit promotion gates (`Promote 25%`, `Promote 100%`), Instant Rollback, and Two-Phase Quick Destruction.
- **Native Local Desktop Bridge (`LocalAgentBridge`)**: Auto-detects workstation CLIs (`az`, `aws`, `gcloud`, `docker`, `kubectl`, `terraform`, `ansible`, `pwsh`, `git`) and sends heartbeats to the Control Plane.
- **Resilient Transport**: Client-side Circuit Breaker, exponential backoff retries, `Idempotency-Key` headers, WebSocket event streaming, and graceful offline simulation mode.

## Run Locally (Windows · macOS · Linux)

```bash
cd apps/syncro-desktop

# 1. Generate native OS desktop runners (preserves lib/, test/, pubspec.yaml)
flutter create . --platforms=windows,macos,linux

# 2. Fetch packages & run unit/widget tests
flutter pub get
flutter test

# 3. Launch native desktop app (connects to Syncro Deployer Control Plane)
flutter run -d windows   # or -d macos / -d linux
# Custom control-plane endpoint:
flutter run -d windows --dart-define=SYNCRO_API_URL=http://127.0.0.1:8080
```

