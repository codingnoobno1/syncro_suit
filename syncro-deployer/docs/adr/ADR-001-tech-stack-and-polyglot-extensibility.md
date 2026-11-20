# ADR-001: Structured Tech Stack & Polyglot Multi-Project Extensibility

- **Status**: Accepted
- **Date**: 2026-11-19

## Context

The platform must serve as an enterprise Azure DevSecOps Control Plane with CLI, MCP server, Terraform/Ansible orchestration, security scanning, Kubernetes launchability, and high-throughput multi-project connectivity. Ad-hoc Python prototyping scripts fail under concurrency, type drift, and multi-team extension requirements where downstream teams build tools in **Go**, **TypeScript**, or **Java**.

## Decision

1. **Structured Hexagonal Python 3.11+ Core (`services/control-plane`)**:
   - Strict separation into `domain/`, `ports/`, `adapters/`, `application/`, `api/`, `mcp/`, `workers/`, and `cli/`.
   - Strict static typing (`mypy`), `ruff` linting, Pydantic typed schemas, async I/O (`asyncio` + FastAPI/Uvicorn), and Dependency Injection container (`container.py`).
   - Python was retained for the orchestration plane due to first-class ecosystems for Azure CLI/SDK, Ansible, Checkov/Bandit, and MCP server hosting.
2. **Contract-First Polyglot Extension Mesh (`contracts/` + `extensions/`)**:
   - All cross-project boundaries are defined in **Protobuf v3** (`contracts/proto/aegisops/v1/`), **CloudEvents 1.0 JSON Schema** (`contracts/schemas/`), and **OpenAPI 3.1**.
   - High-concurrency drift/K8s scanning extensions run in **Go** (`extensions/go-drift-scanner`).
   - PR & admission webhooks run in **TypeScript** (`extensions/ts-policy-webhook`).
   - Enterprise Kafka SIEM & compliance bridges run in **Java 17** (`extensions/java-audit-bridge`), easily deployable alongside Spring Boot ecosystems.
3. **Kubernetes-First Packaging (`deploy/k8s` + `deploy/helm`)**:
   - Every service and extension ships with a non-root container image, Kustomize overlays, Helm v3 chart, HPA, and NetworkPolicy.

## Consequences

- Teams do not need to write Python to extend AegisOps.
- Performance-critical scanning and high-volume Kafka consumers scale horizontally in Go or Java pods without GIL contention.
- Local simulation adapters guarantee fast deterministic CI tests without live Azure subscriptions.
