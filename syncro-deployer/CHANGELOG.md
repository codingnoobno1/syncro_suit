# Changelog

All notable changes to **AegisOps** are documented in this file following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-19

### Added
- Hexagonal Python 3.11+ Control Plane (`services/control-plane`) with FastAPI REST v1, WebSocket live event streaming, and Prometheus `/metrics`.
- Production CLI (`aegis`) covering multi-project registry, DevSecOps scanning, Terraform/Ansible orchestration, Kubernetes launching, Quick Destruction, PowerShell RBAC planning, and MCP hosting.
- Model Context Protocol (`MCP`) JSON-RPC 2.0 server supporting both `stdio` and Streamable HTTP transports with Tools, Resources, and Prompts.
- Tri-broker messaging fabric: Apache Kafka (CloudEvents 1.0 audit/security stream), RabbitMQ (priority work queues + DLX), and Redis (distributed locks, ephemeral TTL leases, Pub/Sub), with zero-dependency local simulators.
- Security pipeline integrating Checkov, Trivy, Bandit, tfsec, and OPA/Rego policy gates with SARIF 2.1.0 export.
- Quick Destruction engine with blast-radius dependency graph, HMAC confirmation token, Redis lock, emergency kill-switch, and TTL auto-reaper.
- PowerShell Azure RBAC & ABAC permissions module (`AegisOps.Permissions.psm1`), `-WhatIf`-safe planner script, and 3 least-privilege custom role definitions.
- Modular Azure Terraform Landing Zone (`network`, `aks`, `keyvault`, `acr`, `ephemeral`) and Ansible CIS Linux hardening playbooks.
- Polyglot extension contracts (`Protobuf v3` + `CloudEvents 1.0`) with working **Go**, **TypeScript**, and **Java 17** reference extensions.
- Kubernetes launch manifests (Kustomize base + dev/aks-prod overlays + Helm v3 chart) and full Docker Compose stack.
- React + TypeScript + Vite Command Center Dashboard with custom Vanilla CSS design system.
