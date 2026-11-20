package aegisops.destruction.guardrails

# OPA Policy Gate: Quick Destruction Safety & Protected Environment Fence
default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    input.environment.tier == "production"
    not input.break_glass_approved
    msg := sprintf("Environment '%s' is protected production tier; automated destruction requires dual-approval break-glass", [input.environment.id])
}

deny contains msg if {
    input.environment.has_delete_lock == true
    not input.force_unlock
    msg := sprintf("Azure CanNotDelete resource lock is active on '%s'", [input.environment.id])
}

deny contains msg if {
    input.blast_radius_count > 25
    not input.confirmation_token_verified
    msg := sprintf("Blast radius (%d resources) requires verified HMAC confirmation token", [input.blast_radius_count])
}
