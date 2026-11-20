# AegisOps / Syncro Deployer — Multi-Cloud DevSecOps & Unified Syncro Suite

> **Production-grade, Kubernetes-launchable Multi-Cloud DevSecOps Control Plane & Flutter Desktop Agent** combining **Syncro Deployer** (**Agentic Mode** + **Manual DevOps Mode**), a **7-module Syncro Suite** (`Syncro Desktop`, `Syncro Deployer`, `Syncro CLI`, `Syncro IDE`, `Syncro DB`, `Syncro Git`, `Syncro Tester`), durable **SQLite WAL journaling + Circuit Breakers + Idempotency Keys**, contract-first **Go / TypeScript / Java 17** extensions, **Tri-Broker Event Mesh (Kafka + RabbitMQ + Redis)**, **Guardrailed Autonomous MCP Ops Bot**, and **AWS · GCP · Azure** automation.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Clouds](https://img.shields.io/badge/Clouds-AWS_%7C_GCP_%7C_Azure-0ea5e9.svg)](#)
[![Syncro Suite](https://img.shields.io/badge/Suite-Syncro_Desktop_%7C_Deployer-25A8BA.svg)](https://project-syncroo.netlify.app)
[![Flutter 3.24+](https://img.shields.io/badge/Flutter-Desktop_Agent-02569B.svg)](apps/syncro-desktop/README.md)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](#)
[![Go 1.22+](https://img.shields.io/badge/Go-1.22%2B-00ADD8.svg)](#)
[![TypeScript 5](https://img.shields.io/badge/TypeScript-5.x-3178C6.svg)](#)
[![Java 17](https://img.shields.io/badge/Java-17-ED8B00.svg)](#)

---

## Unified Syncro Suite (`https://project-syncroo.netlify.app`)

| Module | Role | Transport | Status |
| :--- | :--- | :--- | :--- |
| **Syncro Desktop** | Cross-Platform Flutter Desktop Agent (`apps/syncro-desktop/`) with Agentic / Manual toggle & native CLI bridge | `flutter-desktop` | Active |
| **Syncro Deployer** | Dual-mode Multi-Cloud Canary / Blue-Green / Rolling Deployer with SLO Auto-Rollback & Idempotency | `rest+ws` | Active |
| **Syncro CLI** | Unified terminal automation (`syncro` & `aegis` entrypoints) for CI/CD & operators | `cli` | Active |
| **Syncro IDE** | AI editor & coding-agent bridge via Guardrailed MCP Server (**29 tools**, **13 resources**) | `mcp` | Connected |
| **Syncro DB** | Durable SQLite WAL State Journal, Redis distributed locks & Kafka CloudEvents audit backbone | `sqlite-wal+redis` | Active |
| **Syncro Git** | GitOps PR policy admission webhook (`extensions/ts-policy-webhook/`) & ephemeral PR deploys | `gitops-webhook` | Active |
| **Syncro Tester** | Automated canary load, chaos & E2E verification gate (`pre_promote_test_gate` contract) | `contract-ready` | Planned |

---

## Key Capabilities

1. **Syncro Deployer Dual-Mode & Enterprise Resilience (`services/control-plane/src/aegisops/syncro/`)**:
   - **Agentic Mode**: Autonomous Guardrailed MCP Bot executes `Planned -> Preflight -> Canary 5% -> 25% -> 100%` promotion with automatic SLO-breach rollback.
   - **Manual DevOps Mode**: Explicit stage-gated operator control holding at `CANARY_5` (5% canary / 95% stable) until manual `promote` or instant `rollback`.
   - **Hardened Resilience**: SQLite WAL persistence (`SqliteStateJournal`), per-target `CircuitBreaker` + exponential backoff retries, `Idempotency-Key` deduplication, and Redis distributed locks.
2. **Flutter Desktop Agent (`apps/syncro-desktop/`)**: Native Windows / macOS / Linux desktop workbench featuring the 7-module Syncro Suite dock, live **Agentic Mode | Manual DevOps Mode** toggle, `LocalAgentBridge` (`dart:io` CLI probing), client-side `SyncroCircuitBreaker` + `ResilientHttpClient`, WebSocket audit stream, and offline simulation fallback.
3. **All 3 Major Cloud Providers (`aws`, `gcp`, `azure`) & Intelligent 19-SKU VM Selector (`aegis vm compare|provision`)**: Uniform hexagonal [`CloudProviderPort`](services/control-plane/src/aegisops/ports/cloud.py) adapters, multi-cloud Terraform modules, dynamic Ansible inventories, Confidential Compute (AMD SEV-SNP / Intel TDX / AWS Nitro), Spot pricing, and live CIS Terraform HCL generation.
4. **Guardrailed Autonomous MCP Ops Bot (`services/control-plane/src/aegisops/bot/`)**: Launches AWS/GCP/Azure VMs, Kubernetes workloads, and hardened Docker containers; reads unified all-statuses and live multi-cloud bills; enforces `BotGuardrailEngine` + OPA `bot_guardrails.rego` + Prompt-Injection Firewall; generates user-defined Bill-Saving Self-Prompts across billing targets, favorite infra, and 7 traffic techniques.
5. **Polyglot Multi-Project Connectivity (`contracts/` + `extensions/`)**: Protobuf v3 + CloudEvents 1.0 contracts with working **Go** (`go-drift-scanner`), **TypeScript** (`ts-policy-webhook`), and **Java 17** (`java-audit-bridge`) extensions.
6. **Tri-Broker Messaging Fabric (Kafka + RabbitMQ + Redis)**: Apache Kafka (CloudEvents 1.0 audit/security stream), RabbitMQ (priority work lanes + DLQ), and Redis (distributed locks, TTL leases, HMAC destroy tokens, WebSocket Pub/Sub).
7. **Native MCP Server ("Prompt & Host")**: Full JSON-RPC 2.0 MCP server over `stdio` and HTTP `POST /mcp` exposing **29 tools**, **13 resources**, and **4 prompts**.
8. **Multi-Cloud Security, OPA Gates & Least-Privilege IAM**: Checkov, Trivy, Bandit, tfsec, OPA/Rego (SARIF 2.1.0), Azure PowerShell ABAC (`-WhatIf`), AWS IAM Tag ABAC, GCP CEL, and two-phase Quick Destruction kill-switch.

---

## Quick Start & CLI Examples

```bash
make setup
make test
make lint
make build-dashboard
make run-api

# Inspect the 7-module Syncro Suite & resilience health
syncro syncro suite
syncro syncro deploy --mode agentic --cloud gcp --target kubernetes --key rel-101
syncro syncro deploy --mode manual --cloud azure --target docker --key rel-204
syncro syncro deploy --mode agentic --cloud aws --target docker --key rel-fault --simulate-fault

# Launch the Flutter Desktop Agent (Windows / macOS / Linux)
cd apps/syncro-desktop && flutter pub get && flutter run -d linux

# Compare VMs side-by-side across AWS, GCP & Azure (Confidential + Spot)
aegis vm compare --vcpu 4 --ram 16 --confidential --spot

# Guardrailed MCP Ops Bot (All Statuses, Live Bill Reader, Self-Prompting & Docker Launch)
aegis bot status
aegis bot bill
aegis bot generate-prompts --custom "Prioritize ARM64 Spot + KEDA scale-to-zero"
aegis bot self-prompt --autonomy bounded_autonomous
aegis bot docker-launch --name bot-proxy --image nginxinc/nginx-unprivileged:1.27-alpine

# Two-Phase Multi-Cloud Quick Destruction
aegis destroy preview --env env-aws-edge-501
aegis destroy execute --env env-aws-edge-501 --confirm <HMAC_TOKEN> --kill-switch
```

## Architecture Decision Records

- [ADR-001: Structured Tech Stack & Polyglot Extensibility](docs/adr/ADR-001-tech-stack-and-polyglot-extensibility.md)
- [ADR-002: Tri-Broker Messaging Fabric (Kafka, RabbitMQ, Redis)](docs/adr/ADR-002-tri-broker-messaging-kafka-rabbitmq-redis.md)
- [ADR-003: Quick Destruction Safety, Locking & Kill-Switch](docs/adr/ADR-003-quick-destruction-safety-and-locks.md)
- [ADR-004: PowerShell Azure Least-Privilege RBAC & ABAC Plan](docs/adr/ADR-004-powershell-azure-abac-permissions-plan.md)
- [ADR-005: Multi-Cloud Provider Abstraction (AWS · GCP · Azure) & Intelligent VM Selector](docs/adr/ADR-005-multicloud-abstraction-and-vm-selector.md)
- [ADR-006: Guardrailed Autonomous MCP Ops Bot, Billing Reader & Self-Prompting](docs/adr/ADR-006-mcp-ops-bot-guardrails-and-billing-self-prompting.md)
- [ADR-007: Syncro Deployer Resilience Engine, Unified Syncro Suite & Flutter Desktop Agent](docs/adr/ADR-007-syncro-deployer-resilience-and-flutter-desktop-agent.md)
