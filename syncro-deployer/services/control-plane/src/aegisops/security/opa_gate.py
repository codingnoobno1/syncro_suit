"""OPA/Rego Policy Gate evaluator covering AWS, GCP, Azure security & destruction guardrails."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from aegisops.domain.models import PolicyGateResult, SecurityFinding, Severity


class OpaPolicyGate:
    """Evaluates multi-cloud security scans and destruction plans against Rego policy gates."""

    def __init__(
        self,
        policy_dir: Path,
        max_critical: int = 0,
        max_high: int = 5,
        protected_envs: set[str] | None = None,
    ) -> None:
        self._policy_dir = policy_dir
        self._max_critical = max_critical
        self._max_high = max_high
        self._protected_envs = protected_envs or {"prod", "production", "shared-core"}

    @property
    def opa_binary_available(self) -> bool:
        return shutil.which("opa") is not None

    def list_policy_files(self) -> list[dict[str, str]]:
        if not self._policy_dir.exists():
            return []
        return [
            {"name": path.name, "path": str(path), "content": path.read_text("utf-8")}
            for path in sorted(self._policy_dir.glob("*.rego"))
        ]

    async def evaluate_scan(
        self, findings: list[SecurityFinding], summary: dict[str, int]
    ) -> PolicyGateResult:
        policy_file = self._policy_dir / "multicloud_security.rego"
        payload = {
            "summary": {k.lower(): v for k, v in summary.items()},
            "thresholds": {"max_critical": self._max_critical, "max_high": self._max_high},
            "findings": [f.model_dump(mode="json") for f in findings],
        }

        if self.opa_binary_available and policy_file.exists():
            cli_result = await self._run_opa_eval(
                policy_file, "data.aegisops.multicloud.security.deny", payload
            )
            if cli_result is not None:
                return PolicyGateResult(
                    policy_package="aegisops.multicloud.security",
                    allowed=len(cli_result) == 0,
                    violations=cli_result,
                    engine="opa-cli",
                )

        violations: list[str] = []
        crit = summary.get(Severity.CRITICAL.value, 0)
        high = summary.get(Severity.HIGH.value, 0)
        if crit > self._max_critical:
            violations.append(
                f"CRITICAL security findings ({crit}) exceed threshold ({self._max_critical})"
            )
        if high > self._max_high:
            violations.append(
                f"HIGH security findings ({high}) exceed threshold ({self._max_high})"
            )

        blocking_rules = {
            "AZ-KV-001": "Azure Key Vault MUST enable purge_protection_enabled and soft_delete_retention_days >= 90",
            "AZ-NET-001": "Azure NSG MUST NOT allow unrestricted inbound SSH (22) or RDP (3389) from 0.0.0.0/0",
            "AZ-AKS-001": "AKS clusters MUST enable Azure AD RBAC and network_policy",
            "AZ-VM-001": "Azure VMs MUST disable password auth and enable Trusted Launch (vTPM + Secure Boot)",
            "AWS-EC2-001": "AWS EC2 MUST enforce IMDSv2 (metadata_options.http_tokens = 'required')",
            "AWS-SG-001": "AWS Security Group MUST NOT allow SSH (22) or RDP (3389) from 0.0.0.0/0",
            "GCP-GCE-001": "GCP Compute Engine MUST enable Shielded VM (Secure Boot + vTPM)",
            "GCP-FW-001": "GCP Firewall MUST NOT expose SSH/RDP to 0.0.0.0/0; use Identity-Aware Proxy",
        }
        for finding in findings:
            if finding.rule_id in blocking_rules and blocking_rules[finding.rule_id] not in violations:
                violations.append(blocking_rules[finding.rule_id])

        return PolicyGateResult(
            policy_package="aegisops.multicloud.security",
            allowed=len(violations) == 0,
            violations=violations,
            engine="aegis-rego-evaluator",
        )

    async def evaluate_destruction(
        self,
        env_id: str,
        tier: str,
        has_delete_lock: bool,
        blast_radius_count: int,
        break_glass_approved: bool = False,
        force_unlock: bool = False,
        confirmation_token_verified: bool = True,
        lock_mechanism: str = "Cloud Delete Lock",
    ) -> PolicyGateResult:
        violations: list[str] = []
        if (tier.lower() == "production" or env_id.lower() in self._protected_envs) and not break_glass_approved:
            violations.append(
                f"Environment '{env_id}' is protected production tier; automated destruction requires dual-approval break-glass"
            )
        if has_delete_lock and not force_unlock:
            violations.append(f"{lock_mechanism} is active on '{env_id}'")
        if blast_radius_count > 25 and not confirmation_token_verified:
            violations.append(
                f"Blast radius ({blast_radius_count} resources) requires verified HMAC confirmation token"
            )
        return PolicyGateResult(
            policy_package="aegisops.destruction.guardrails",
            allowed=len(violations) == 0,
            violations=violations,
            engine="aegis-rego-evaluator",
        )

    async def _run_opa_eval(
        self, policy_file: Path, query: str, input_doc: dict[str, Any]
    ) -> list[str] | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "opa",
                "eval",
                "-I",
                "-d",
                str(policy_file),
                "--format",
                "json",
                query,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate(input=json.dumps(input_doc).encode("utf-8"))
            if proc.returncode != 0:
                return None
            parsed = json.loads(stdout.decode("utf-8"))
            val = parsed["result"][0]["expressions"][0]["value"]
            return list(val) if isinstance(val, list) else []
        except Exception:
            return None
