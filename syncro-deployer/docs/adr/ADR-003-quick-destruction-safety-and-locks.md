# ADR-003: Quick Destruction Safety, Distributed Locking & Kill-Switch Protocol

- **Status**: Accepted
- **Date**: 2026-11-19

## Context

Ephemeral cloud environments save 40-70% of Azure spend and shrink attack surface, but automated teardown introduces catastrophic blast-radius risk if misconfigured or invoked concurrently.

## Decision

All quick-destruction operations follow a mandatory 5-stage safety protocol:
1. **Blast-Radius Graph & Cost Preview**: Compute resource dependency order (K8s Namespace -> AKS -> ACR -> Key Vault -> VNet -> Resource Group) and detect Azure `CanNotDelete` locks.
2. **OPA Policy Guardrails (`destruction_guardrails.rego`)**: Automatically block production tier (`prod`, `production`, `shared-core`) unless dual-approval break-glass is explicitly supplied.
3. **Short-Lived HMAC Confirmation Token**: Stored in Redis with a 300-second TTL, bound to `(environment_id, resource_hash, requester)`.
4. **Redis Distributed Workspace Lock**: Acquire `lock:env:{id}` (`NX PX`) before dispatching teardown to RabbitMQ priority queue `jobs.quick-destroy`.
5. **Immutable Kafka Audit & Ordered Teardown**: Emit `io.aegisops.destroy.requested` and `io.aegisops.destroy.completed` CloudEvents while draining K8s workloads, revoking ephemeral RBAC, executing `terraform destroy`, and sweeping orphaned NICs/disks.
