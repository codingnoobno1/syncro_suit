package aegisops.bot.guardrails

# OPA Policy Gate: Strict Guardrails for Autonomous AegisOps MCP Bot
# Governs VM launches, Kubernetes workloads, Docker containers, and self-prompted cost actions.

default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    input.action_type == "launch_vm"
    not input.cloud_allowed
    msg := sprintf("Cloud '%s' is not permitted by Bot Guardrail policy", [input.cloud])
}

deny contains msg if {
    input.estimated_hourly_usd > input.policy.max_single_resource_hourly_usd
    msg := sprintf("Estimated hourly cost ($%.2f/h) exceeds single-resource guardrail ($%.2f/h)", [input.estimated_hourly_usd, input.policy.max_single_resource_hourly_usd])
}

deny contains msg if {
    input.projected_monthly_total_usd > input.policy.max_monthly_budget_usd
    msg := sprintf("Action pushes projected monthly bill ($%.2f) above hard budget cap ($%.2f)", [input.projected_monthly_total_usd, input.policy.max_monthly_budget_usd])
}

deny contains msg if {
    input.action_type == "launch_docker"
    input.privileged == true
    msg := "Docker privileged containers are strictly forbidden by Bot Guardrail policy"
}

deny contains msg if {
    input.action_type == "launch_docker"
    input.policy.require_non_root_docker == true
    input.run_as_non_root == false
    msg := "Docker containers MUST run as non-root UID >= 10000"
}

deny contains msg if {
    input.prompt_injection_detected == true
    msg := "Adversarial guardrail-bypass attempt detected in prompt input"
}
