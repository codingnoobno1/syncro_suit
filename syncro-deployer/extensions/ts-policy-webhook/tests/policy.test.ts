import test from "node:test";
import assert from "node:assert/strict";
import { evaluatePullRequestGate } from "../src/policy.js";

test("denies PR with critical findings or unapproved production Terraform changes", () => {
  const res = evaluatePullRequestGate({
    repository: "aegisops/payments-core",
    prNumber: 412,
    changedFiles: ["infra/terraform/modules/aks/main.tf"],
    criticalFindings: 1,
    hasDestroyApproval: false,
    touchesProduction: true,
  });
  assert.equal(res.allowed, false);
  assert.equal(res.violations.length, 2);
});

test("approves clean ephemeral PR with zero critical findings", () => {
  const res = evaluatePullRequestGate({
    repository: "aegisops/portal-web",
    prNumber: 415,
    changedFiles: ["src/App.tsx"],
    criticalFindings: 0,
    hasDestroyApproval: false,
    touchesProduction: false,
  });
  assert.equal(res.allowed, true);
  assert.equal(res.violations.length, 0);
});
