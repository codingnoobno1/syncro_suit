# ADR-007: Syncro Deployer Resilience & Flutter Desktop Agent (Agentic vs. Manual DevOps Mode)

- **Status**: Accepted
- **Date**: 2026-11-20

## Context

Platform engineers need a native cross-platform desktop workbench (Windows, macOS, Linux) that bridges local DevOps CLIs (`az`, `aws`, `gcloud`, `docker`, `kubectl`, `terraform`, `pwsh`) to the AegisOps Control Plane while switching cleanly between **Agentic Mode** (guardrailed autonomous canary rollouts & bill-saving self-prompting) and **Manual DevOps Mode** (explicit human promotion gates `5% -> 25% -> 100%`, dry-run plans, instant rollback).

## Decision

1. **Dual-Mode Syncro Deployer Engine (`services/control-plane/src/aegisops/syncro/`)**:
   - **Idempotency Keys** (`idempotency_key`) prevent duplicate cloud provisioning on retries.
   - **SQLite WAL Persistence** (`adapters/persistence/journal.py`) preserves deployment timelines, snapshots, and registered desktop agents across restarts.
   - **Circuit Breakers & Exponential Backoff** (`syncro/resilience.py`) protect cloud, Docker, and Kubernetes runtimes.
   - **Automatic SLO-Fault Rollback**: Any canary stage breaching `auto_rollback_error_rate_pct` immediately restores `previous_revision` (100% stable traffic) and publishes `io.aegisops.syncro.auto_rollback` to Kafka.
   - **Mode Separation**:
     - `agentic`: Auto-progresses healthy canaries (`5% -> 25% -> 100%`) within strict guardrails.
     - `manual`: Pauses at `canary_5` until an operator approves `POST /api/v1/syncro/deployments/{id}/promote` or triggers `rollback`.
2. **Flutter Desktop Agent (`apps/syncro-desktop/`)**:
   - Null-safe Flutter 3.24+ Desktop client with native `dart:io` `Process` probe (`LocalAgentBridge`), resilient retry/circuit-breaker HTTP client (`ResilientHttpClient`), real-time WebSocket stream, top-bar **Agentic / Manual DevOps Mode Switcher**, and offline simulation parity.
