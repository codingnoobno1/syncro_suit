package aegisops.kubernetes.security

# OPA Policy Gate: Kubernetes Workload Hardening
default allow := false

allow if {
    count(deny) == 0
}

deny contains msg if {
    input.kind == "Deployment"
    some c in input.spec.template.spec.containers
    c.securityContext.privileged == true
    msg := sprintf("Container '%s' cannot run in privileged mode", [c.name])
}

deny contains msg if {
    input.kind == "Deployment"
    some c in input.spec.template.spec.containers
    not c.securityContext.runAsNonRoot
    msg := sprintf("Container '%s' MUST set runAsNonRoot: true", [c.name])
}

deny contains msg if {
    input.kind == "Deployment"
    some c in input.spec.template.spec.containers
    endswith(c.image, ":latest")
    msg := sprintf("Container '%s' uses mutable ':latest' image tag", [c.name])
}
