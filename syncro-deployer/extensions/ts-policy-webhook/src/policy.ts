export interface PullRequestEvent {
  repository: string;
  prNumber: number;
  changedFiles: string[];
  criticalFindings: number;
  hasDestroyApproval: boolean;
  touchesProduction: boolean;
}

export interface PolicyEvaluation {
  allowed: boolean;
  summary: string;
  violations: string[];
  annotations: Record<string, string>;
}

export function evaluatePullRequestGate(event: PullRequestEvent): PolicyEvaluation {
  const violations: string[] = [];

  if (event.criticalFindings > 0) {
    violations.push(`Blocking PR #${event.prNumber}: ${event.criticalFindings} CRITICAL DevSecOps finding(s).`);
  }

  const modifiesIaC = event.changedFiles.some(
    (f) => f.endsWith(".tf") || f.endsWith(".rego") || f.endsWith(".ps1")
  );

  if (event.touchesProduction && modifiesIaC && !event.hasDestroyApproval) {
    violations.push("Production IaC/RBAC/OPA mutations require security dual-approval.");
  }

  return {
    allowed: violations.length === 0,
    summary:
      violations.length === 0
        ? `PR #${event.prNumber} on ${event.repository} passed AegisOps TS admission gate.`
        : `PR #${event.prNumber} denied with ${violations.length} violation(s).`,
    violations,
    annotations: {
      extension: "ts-policy-webhook",
      contract: "aegisops.v1.ExtensionService",
      iac_modified: String(modifiesIaC),
    },
  };
}
