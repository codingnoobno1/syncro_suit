# Runbook: Emergency Quick Destruction (Kill-Switch)

## When to Trigger

- Compromised ephemeral environment or leaked workload credential
- Runaway AKS node pool spend in non-production
- Stale PR preview environment past TTL lease

## Procedure

1. **Preview Blast Radius & Acquire HMAC Confirmation Token**:
   ```bash
   aegis destroy preview --env env-pr-412
   ```
2. **Verify Zero Protected Production Targets**:
   Confirm `tier != production` and inspect the dependency graph and `CanNotDelete` lock status.
3. **Execute Kill-Switch**:
   ```bash
   aegis destroy execute --env env-pr-412 --confirm <HMAC_TOKEN> --kill-switch
   ```
4. **Verify Kafka Audit Trail**:
   ```bash
   aegis broker kafka-tail --topic aegis.destroy.events --limit 5
   ```
