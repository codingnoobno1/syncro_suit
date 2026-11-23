# Syncro Deployer — Electron.js Desktop Workbench

Cross-platform **Electron.js** desktop frontend for **Syncro Deployer / AegisOps**, engineered with a Swiss-Industrial Slate & Cerulean Titanium Vanilla CSS design system, secure `contextIsolation` preload bridge, automatic Control Plane sidecar lifecycle, and a native C99 shared library (`.so` / `.dll` / `.dylib`).

## Features

- **Cloud CLI Studio (`az` · `gcloud` · `aws`)** — Interactive guardrailed runner invoking the backend's Azure, GCP, and AWS CLI wrappers via **MCP JSON-RPC 2.0** or **REST API**, with curated presets, dry-run preview, shell-injection/production-delete guardrail tests, and audited execution history.
- **MCP Tool Console (34 Tools · 15 Resources · 6 Prompts)** — Live JSON-RPC 2.0 explorer for `POST /mcp`, including `aegis_az_cli`, `aegis_gcp_cli`, `aegis_aws_cli`, `aegis_cloud_cli_status`, and `aegis_cloud_cli_history`.
- **Dual-Mode Syncro Deployer** — Switch seamlessly between **Agentic Mode** and **Manual DevOps Mode**, launch Canary/Blue-Green/Rolling releases, trigger SLO fault auto-rollback, and promote/rollback live.
- **Multi-Cloud VM & FinOps Matrix** — Compare AWS EC2, GCP Shielded GCE, and Azure Confidential VMs side-by-side with live generated CIS Terraform HCL and 1-click provisioning.
- **DevSecOps & Two-Phase Quick Destroy** — Run Checkov/Trivy/Bandit/tfsec/OPA scans, export SARIF via native OS save dialog, generate least-privilege IAM/PowerShell ABAC plans, and execute HMAC-confirmed teardowns.
- **Guardrailed Ops Bot & Live WebSocket Stream** — Real-time Kafka/Redis event drawer, Prompt-Injection Firewall tester, and Bill-Saving Self-Prompt runner.

## Quick Start

```bash
# 1. Start the Python Control Plane + Cloud CLI MCP Host (:8080)
cd ../../services/control-plane
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/syncro server --host 127.0.0.1 --port 8080

# 2. Install & launch Electron Desktop (second terminal)
cd ../../apps/electron-desktop
npm install
npm run build
npm start
```

## Platform Packaging (`.exe`, `.so`, `.AppImage`, `.deb`, `.rpm`, `.tar.gz`, `.dmg`)

| Platform | Script | Output Artifacts |
| :--- | :--- | :--- |
| **Linux (x64)** | `bash scripts/package-platform.sh` | `.AppImage`, `.deb`, `.rpm`, `.tar.gz`, `libsyncro_native.so`, `SHA256SUMS.txt` |
| **Windows (x64)** | `pwsh -File scripts/package-platform.ps1` | NSIS `.exe`, Portable `.exe`, `.zip`, `syncro_native.dll`, `SHA256SUMS.txt` |
| **macOS (x64 / arm64)** | `bash scripts/package-platform.sh` | `.dmg`, `.zip`, `libsyncro_native.dylib`, `SHA256SUMS.txt` |
