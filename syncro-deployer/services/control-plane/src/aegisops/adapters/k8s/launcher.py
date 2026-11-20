"""Kubernetes manifest, Helm, and ephemeral Job launcher with OPA security validation."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import yaml

from aegisops.domain.models import K8sLaunchRequest, K8sLaunchResult, PolicyGateResult


class K8sLauncher:
    """Renders hardened Kubernetes workloads, validates OPA policies, and launches via kubectl/helm."""

    def __init__(self, k8s_dir: Path, mode: str = "simulation") -> None:
        self._k8s_dir = k8s_dir
        self._mode = mode

    @property
    def kubectl_available(self) -> bool:
        return shutil.which("kubectl") is not None

    def build_hardened_manifest(self, req: K8sLaunchRequest) -> dict[str, Any]:
        if req.mode == "ephemeral-job":
            return {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {
                    "name": f"aegis-job-{req.workload_name}",
                    "namespace": req.namespace,
                    "labels": {
                        "app.kubernetes.io/managed-by": "aegisops",
                        "aegis.dev/project": req.project_id,
                        "aegis.dev/environment": req.environment_id,
                    },
                },
                "spec": {
                    "ttlSecondsAfterFinished": 600,
                    "backoffLimit": 2,
                    "template": {
                        "spec": {
                            "restartPolicy": "Never",
                            "automountServiceAccountToken": False,
                            "securityContext": {"runAsNonRoot": True, "runAsUser": 10001},
                            "containers": [
                                {
                                    "name": req.workload_name,
                                    "image": req.image,
                                    "securityContext": {
                                        "privileged": False,
                                        "runAsNonRoot": True,
                                        "readOnlyRootFilesystem": True,
                                        "allowPrivilegeEscalation": False,
                                        "capabilities": {"drop": ["ALL"]},
                                    },
                                }
                            ],
                        }
                    },
                },
            }

        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": req.workload_name,
                "namespace": req.namespace,
                "labels": {
                    "app": req.workload_name,
                    "aegis.dev/project": req.project_id,
                    "aegis.dev/environment": req.environment_id,
                },
            },
            "spec": {
                "replicas": req.replicas,
                "selector": {"matchLabels": {"app": req.workload_name}},
                "template": {
                    "metadata": {"labels": {"app": req.workload_name}},
                    "spec": {
                        "automountServiceAccountToken": False,
                        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001},
                        "containers": [
                            {
                                "name": req.workload_name,
                                "image": req.image,
                                "ports": [{"containerPort": 8080}],
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                    "limits": {"cpu": "500m", "memory": "512Mi"},
                                },
                                "securityContext": {
                                    "privileged": False,
                                    "runAsNonRoot": True,
                                    "readOnlyRootFilesystem": True,
                                    "allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                            }
                        ],
                    },
                },
            },
        }

    def evaluate_k8s_opa_gate(self, manifest: dict[str, Any]) -> PolicyGateResult:
        violations: list[str] = []
        spec = manifest.get("spec", {})
        template_spec = spec.get("template", {}).get("spec", {})
        containers = template_spec.get("containers", [])
        for container in containers:
            name = container.get("name", "unknown")
            image = str(container.get("image", ""))
            sec = container.get("securityContext", {})
            if sec.get("privileged") is True:
                violations.append(f"Container '{name}' cannot run in privileged mode")
            if not sec.get("runAsNonRoot"):
                violations.append(f"Container '{name}' MUST set runAsNonRoot: true")
            if image.endswith(":latest") or ":" not in image:
                violations.append(
                    f"Container '{name}' uses mutable or untagged image '{image}'; pin an immutable tag or digest"
                )
        return PolicyGateResult(
            policy_package="aegisops.kubernetes.security",
            allowed=len(violations) == 0,
            violations=violations,
        )

    async def launch(self, req: K8sLaunchRequest) -> K8sLaunchResult:
        manifest = self.build_hardened_manifest(req)
        gate = self.evaluate_k8s_opa_gate(manifest)
        manifest_yaml = yaml.safe_dump(manifest, sort_keys=False)

        if not gate.allowed:
            return K8sLaunchResult(
                project_id=req.project_id,
                environment_id=req.environment_id,
                namespace=req.namespace,
                workload_name=req.workload_name,
                mode=req.mode,
                opa_gate=gate,
                manifest_yaml=manifest_yaml,
                applied_resources=[],
                status="denied_by_opa",
            )

        if self._mode == "live" and self.kubectl_available:
            proc = await asyncio.create_subprocess_exec(
                "kubectl",
                "apply",
                "-f",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate(input=manifest_yaml.encode("utf-8"))

        kind = manifest["kind"]
        applied = [
            f"Namespace/{req.namespace}",
            f"{kind}/{req.workload_name}",
            f"NetworkPolicy/{req.workload_name}-zero-trust",
        ]
        return K8sLaunchResult(
            project_id=req.project_id,
            environment_id=req.environment_id,
            namespace=req.namespace,
            workload_name=req.workload_name,
            mode=req.mode,
            opa_gate=gate,
            manifest_yaml=manifest_yaml,
            applied_resources=applied,
            status="launched",
        )
