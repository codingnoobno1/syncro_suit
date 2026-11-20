# ADR-002: Tri-Broker Event & State Fabric (Kafka + RabbitMQ + Redis)

- **Status**: Accepted
- **Date**: 2026-11-19

## Context

DevSecOps pipelines combine three distinct workload patterns that perform poorly when forced into a single broker:
1. Immutable multi-consumer compliance/audit streams (requiring replay and consumer groups).
2. Long-running, failure-prone infrastructure jobs (Terraform, Ansible, destruction) requiring retries, priority lanes, and dead-letter queues.
3. Low-latency distributed locks, ephemeral TTL timers, and live WebSocket state fanout.

## Decision

Assign each broker a strict, non-overlapping responsibility behind hexagonal ports (`ports/messaging.py`):

| Broker | Port Interface | Topics / Queues / Keyspaces | Purpose |
| :--- | :--- | :--- | :--- |
| **Apache Kafka** | `EventBusPort` | `aegis.audit.events`, `aegis.security.findings`, `aegis.infra.lifecycle`, `aegis.destroy.events` | Immutable CloudEvents 1.0 audit & security telemetry; multi-project consumer groups (Go, Java, TS). |
| **RabbitMQ** | `JobQueuePort` | `jobs.quick-destroy` (priority 10), `jobs.security-scan` (priority 7), `jobs.terraform` (5), `jobs.ansible` (5), `jobs.k8s-launch` (5), `jobs.dlq` | Reliable task dispatch, retry backoff, and dead-letter inspection for async workers. |
| **Redis** | `StateStorePort` | `lock:env:*`, `ttl:env:*`, `token:destroy:*`, `cache:dashboard:*`, Pub/Sub `aegis:live` | Distributed locks preventing concurrent Terraform state corruption, TTL auto-reaping, HMAC token storage, and sub-10ms dashboard streaming. |

## Consequences

- Each broker operates in its optimal sweet spot.
- Every port ships with both a **live async driver** (`aiokafka`, `aio-pika`, `redis.asyncio`) and a **local simulator** so CI and local development work out-of-the-box.
