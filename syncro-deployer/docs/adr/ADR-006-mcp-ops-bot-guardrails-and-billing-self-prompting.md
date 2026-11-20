# ADR-006: Guardrailed Autonomous MCP Ops Bot, Live Billing Reader & User-Defined Self-Prompting

- **Status**: Accepted
- **Date**: 2026-11-19

## Context

Allowing an AI/MCP bot to launch VMs across AWS/GCP/Azure, deploy Kubernetes workloads, run Docker containers, and automatically optimize cloud spend introduces financial runaway risk, container escape risk, and adversarial prompt-injection risk. Simultaneously, platform teams want the bot to continuously read cloud bills and self-prompt cost-saving remediations aligned with their exact **billing caps**, **favorite infrastructure stacks**, and **favorite traffic-handling techniques** (e.g., Canary, KEDA scale-to-zero, Edge CDN caching to cut egress).

## Decision

1. **Strict Guardrail Engine (`bot/guardrail_engine.py` + `policies/opa/bot_guardrails.rego`)**:
   - Every bot action passes a deterministic guardrail check enforcing:
     - Hard monthly/hourly budget ceilings and Spot-enforcement thresholds.
     - Allowed cloud whitelist (`aws`, `gcp`, `azure`), active VM/container count caps, and max ephemeral TTL.
     - Docker CIS hardening (`privileged=False`, `run_as_non_root=True`, `read_only_root_fs=True`, immutable tags, CPU/memory limits).
     - Production mutation fence and an **Adversarial Prompt-Injection Firewall** that rejects jailbreak/bypass directives.
2. **Unified Status Aggregator & Live Cloud Bill Reader (`bot/billing_reader.py`)**:
   - Aggregates real-time status across AWS/GCP/Azure VMs, K8s workloads, Docker containers, and Kafka/RabbitMQ/Redis.
   - Reads itemized MTD/EOM forecasted spend, budget utilization %, idle compute, On-Demand-to-Spot waste, and egress hotspots.
3. **Structured User Directive & Self-Prompt Injection Engine (`bot/prompt_composer.py`)**:
   - Separates **Trusted Operator Directives** (billing targets, favorite infra, favorite traffic-handling techniques, custom cost-saving directives) from untrusted inputs.
   - Generates injectable system/guardrail prompts for external MCP clients AND drives the Auto-Bot's bounded self-prompting bill-saving optimization cycle (`observe_only`, `recommend_and_confirm`, or `bounded_autonomous`).
