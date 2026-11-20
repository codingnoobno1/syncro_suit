"""Terraform execution adapter with live CLI support and HCL-aware simulator."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any


class TerraformRunner:
    """Wraps terraform init/plan/apply/destroy safely with a deterministic HCL simulator."""

    def __init__(self, terraform_dir: Path, mode: str = "simulation") -> None:
        self._terraform_dir = terraform_dir
        self._mode = mode

    @property
    def binary_available(self) -> bool:
        return shutil.which("terraform") is not None

    def discover_resources(self) -> list[str]:
        resources: list[str] = []
        pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"')
        if self._terraform_dir.exists():
            for tf_file in sorted(self._terraform_dir.rglob("*.tf")):
                content = tf_file.read_text(encoding="utf-8", errors="ignore")
                for res_type, res_name in pattern.findall(content):
                    resources.append(f"{res_type}.{res_name}")
        return resources

    async def plan(self, environment_id: str, project_id: str, ttl_hours: int = 4) -> dict[str, Any]:
        env_dir = self._terraform_dir / "environments" / "ephemeral"
        if self._mode == "live" and self.binary_available and env_dir.exists():
            proc = await asyncio.create_subprocess_exec(
                "terraform",
                f"-chdir={env_dir}",
                "plan",
                "-input=false",
                "-no-color",
                f"-var=project_id={project_id}",
                f"-var=environment_id={environment_id}",
                f"-var=ttl_hours={ttl_hours}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return {
                "engine": "terraform-cli",
                "exit_code": proc.returncode,
                "stdout": stdout.decode()[:4000],
                "stderr": stderr.decode()[:1000],
            }

        discovered = self.discover_resources()
        return {
            "engine": "terraform-simulator",
            "environment_id": environment_id,
            "project_id": project_id,
            "working_dir": str(env_dir),
            "plan_summary": {"to_add": len(discovered), "to_change": 0, "to_destroy": 0},
            "planned_resources": discovered,
            "tags_enforced": {
                "aegis:managed": "true",
                "aegis:ephemeral": "true",
                "aegis:ttl_hours": str(ttl_hours),
            },
            "status": "planned",
        }

    async def destroy(self, environment_id: str, resource_group: str) -> dict[str, Any]:
        env_dir = self._terraform_dir / "environments" / "ephemeral"
        if self._mode == "live" and self.binary_available and env_dir.exists():
            proc = await asyncio.create_subprocess_exec(
                "terraform",
                f"-chdir={env_dir}",
                "destroy",
                "-auto-approve",
                "-input=false",
                "-no-color",
                f"-var=environment_id={environment_id}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return {
                "engine": "terraform-cli",
                "exit_code": proc.returncode,
                "stdout": stdout.decode()[:4000],
                "stderr": stderr.decode()[:1000],
            }
        return {
            "engine": "terraform-simulator",
            "environment_id": environment_id,
            "resource_group": resource_group,
            "destroyed_modules": ["module.aks", "module.acr", "module.keyvault", "module.network"],
            "status": "destroyed",
        }
