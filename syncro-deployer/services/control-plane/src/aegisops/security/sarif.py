"""SARIF 2.1.0 serializer for DevSecOps scan reports (GitHub Code Scanning compatible)."""

from __future__ import annotations

from typing import Any

from aegisops.domain.models import ScanReport, Severity

_LEVEL_MAP = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}


def to_sarif(report: ScanReport) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for finding in report.findings:
        rules.setdefault(
            finding.rule_id,
            {
                "id": finding.rule_id,
                "name": finding.title,
                "shortDescription": {"text": finding.title},
                "help": {"text": finding.remediation},
                "properties": {"scanner": finding.scanner, "severity": finding.severity.value},
            },
        )
        results.append(
            {
                "ruleId": finding.rule_id,
                "level": _LEVEL_MAP[finding.severity],
                "message": {"text": f"[{finding.scanner}] {finding.title} — {finding.remediation}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": finding.file_path},
                            "region": {"startLine": max(1, finding.line)},
                        }
                    }
                ],
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "AegisOps DevSecOps Pipeline",
                        "version": "0.1.0",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
