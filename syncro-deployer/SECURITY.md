# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :--- |
| `0.1.x` (main) | Yes |

## Threat Model & Guardrails

AegisOps orchestrates privileged Azure infrastructure provisioning, RBAC planning, and automated destruction. By design, the following controls are mandatory:

1. **Zero Static Credentials in Code**: Production deployments MUST use Azure OIDC Federated Workload Identity or Managed Identity.
2. **Two-Phase Quick Destruction**: Teardown requires a short-lived Redis-backed HMAC confirmation token, an acquired distributed lock, and an OPA `destruction_guardrails.rego` policy check.
3. **Protected Environment Fence**: Environments listed in `AEGIS_PROTECTED_ENVS` (`prod`, `production`, `shared-core`) are blocked from automated kill-switch destruction unless explicit dual-approval break-glass metadata is validated.
4. **PowerShell ABAC Enforcement**: Destroyer custom roles MUST attach an Azure ABAC condition restricting deletions to resource groups tagged `aegis:ephemeral=true`.
5. **Immutable Kafka Audit Trail**: Every plan, scan, RBAC mutation, MCP tool call, and destroy operation emits a signed CloudEvents 1.0 audit record.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities. Report privately via GitHub Security Advisories or email `security@aegisops.dev` with reproduction steps and impact assessment. We acknowledge reports within 24 hours.
