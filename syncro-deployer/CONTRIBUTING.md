# Contributing to AegisOps

Thank you for your interest in contributing to **AegisOps**!

## Architecture Rules

1. **Preserve Hexagonal Boundaries**: Code under `services/control-plane/src/aegisops/domain/` must never import FastAPI, Redis, Kafka, RabbitMQ, or subprocess runners.
2. **Contract-First Polyglot Changes**: When adding or changing extension payloads or events, update `contracts/proto/` and `contracts/schemas/` first.
3. **Simulation Parity**: Every new Azure, Terraform, Ansible, Kubernetes, or broker adapter must support both `live` and `simulation` modes so contributors can run the full test suite without cloud credentials.
4. **Security Gates Must Pass**: All PRs run Ruff, Mypy, Pytest, Bandit, Checkov/OPA policy tests, Go tests, TypeScript build/tests, and Java Maven tests.

## Local Development Workflow

```bash
make setup        # Install Python, Dashboard, TS, Go, and Java tool dependencies
make test         # Run full polyglot test suite (Python + Go + TypeScript + Java)
make lint         # Run ruff + mypy + go vet + tsc
make run-api      # Start Control Plane + MCP HTTP + WebSocket server on :8080
make run-mcp      # Start MCP server over stdio for Claude Desktop / Cursor / IDE
make up           # Launch full Docker Compose stack (Kafka, RabbitMQ, Redis, OPA, UI)
```
