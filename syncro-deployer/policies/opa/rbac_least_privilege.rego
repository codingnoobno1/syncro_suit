package aegisops.rbac.least_privilege

# OPA Policy Gate: Azure PowerShell RBAC & ABAC Least Privilege Enforcement
default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    some assignment in input.assignments
    assignment.role_name == "Owner"
    assignment.scope_level == "subscription"
    msg := sprintf("Principal '%s' cannot hold subscription-wide Owner role; scope to Resource Group with Custom Role", [assignment.principal])
}

deny contains msg if {
    some assignment in input.assignments
    assignment.persona == "destroyer"
    not contains(assignment.abac_condition, "aegis:ephemeral")
    msg := sprintf("Destroyer assignment for '%s' MUST enforce Azure ABAC condition requiring 'aegis:ephemeral=true'", [assignment.principal])
}

deny contains msg if {
    some assignment in input.assignments
    assignment.persona == "destroyer"
    assignment.pim_max_duration_hours > 2
    msg := sprintf("Destroyer PIM activation duration (%dh) exceeds 2-hour maximum", [assignment.pim_max_duration_hours])
}
