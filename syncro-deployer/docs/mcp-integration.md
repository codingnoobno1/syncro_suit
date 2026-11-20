# MCP Server & Guardrailed Ops Bot Integration ("Prompt & Host")

AegisOps ships a native **Model Context Protocol (JSON-RPC 2.0)** server with a **Strict Guardrail Engine** and **Adversarial Prompt-Injection Firewall** so AI assistants (Claude Desktop, Cursor, VS Code, Antigravity) can safely launch VMs/Kubernetes/Docker, read all statuses & bills, and run user-defined bill-saving self-prompt cycles.

## Transports

1. **`stdio` transport (Local IDE / Desktop Host)**:
   ```bash
   aegis mcp serve --transport stdio
   ```
2. **Streamable HTTP / JSON-RPC endpoint (Remote / K8s Hosted)**:
   ```bash
   aegis server --host 127.0.0.1 --port 8080
   # MCP JSON-RPC endpoint available at POST http://127.0.0.1:8080/mcp
   ```

## Exposed Capabilities (24 Tools · 11 Resources · 5 Prompts)

- **Guardrailed MCP Ops Bot Tools**:
  - `aegis_bot_read_all_statuses` — Unified status across AWS/GCP/Azure VMs, K8s workloads, Docker containers, Kafka/RabbitMQ/Redis, Live Bill, and Auto-Bot feed.
  - `aegis_bot_read_bill` — Itemized multi-cloud bill (MTD, EOM forecast, egress, and directive-aligned savings).
  - `aegis_bot_launch_vm` — Guardrail-enforced AWS/GCP/Azure VM launch (hard budget caps, auto-Spot, TTL clamp, Confidential Compute enforcement).
  - `aegis_bot_launch_k8s` — Guardrail-enforced EKS/GKE/AKS workload launch (production namespace fence, immutable tags, OPA).
  - `aegis_bot_launch_docker` — CIS-hardened Docker launcher (blocks `--privileged`, root, writable rootfs, `:latest`).
  - `aegis_bot_update_guardrails` & `aegis_bot_update_directives` — Live guardrail & user directive configuration (billing targets, favorite infra, 7 traffic-handling techniques).
  - `aegis_bot_generate_prompts` — Synthesizes injectable Guardrail System Prompts & Bill-Saving Self-Prompts.
  - `aegis_bot_self_prompt_save_bill` — Runs Auto-Bot bill-saving self-prompt optimization (`observe_only`, `recommend_and_confirm`, or `bounded_autonomous`).
  - `aegis_bot_prompt` — Natural-language bot execution behind the Prompt-Injection Firewall.
- **Core Platform & Multi-Cloud Tools**: `aegis_list_projects`, `aegis_register_project`, `aegis_vm_compare_clouds`, `aegis_vm_provision`, `aegis_security_scan`, `aegis_terraform_plan`, `aegis_ansible_harden`, `aegis_k8s_launch`, `aegis_preview_destroy`, `aegis_quick_destroy`, `aegis_powershell_rbac_plan`, `aegis_finops_summary`, `aegis_drift_scan`, `aegis_broker_health`.
- **Resources**: `aegis://bot/status`, `aegis://bot/bill`, `aegis://bot/guardrails`, `aegis://bot/prompts`, `aegis://projects`, `aegis://environments`, `aegis://vms/catalog`, `aegis://finops/summary`, `aegis://scans/latest`, `aegis://policies/opa`, `aegis://events/kafka-tail`.
- **Prompts**: `autobot_bill_saving_self_prompt`, `devsecops_preflight_audit`, `multicloud_vm_selection`, `emergency_teardown_runbook`, `multicloud_least_privilege_review`.
