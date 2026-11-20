"""Safe Azure CLI subprocess adapter with deterministic local simulation mode."""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any


class AzureCliAdapter:
    """Executes Azure CLI commands safely via argv list (never shell=True) or simulates them."""

    def __init__(self, subscription_id: str, tenant_id: str, mode: str = "simulation") -> None:
        self._subscription_id = subscription_id
        self._tenant_id = tenant_id
        self._mode = mode

    @property
    def az_available(self) -> bool:
        return shutil.which("az") is not None

    async def _run_az(self, args: list[str]) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            "az",
            *args,
            "--output",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"az {' '.join(args)} failed: {stderr.decode().strip()}")
        raw = stdout.decode().strip()
        return json.loads(raw) if raw else {"ok": True}

    async def account_status(self) -> dict[str, Any]:
        if self._mode == "live" and self.az_available:
            return await self._run_az(["account", "show"])
        return {
            "mode": "simulation",
            "subscription_id": self._subscription_id,
            "tenant_id": self._tenant_id,
            "cloud_name": "AzureCloud",
            "auth_method": "OIDC-Workload-Identity",
            "defender_for_cloud": "Standard",
        }

    async def check_resource_locks(self, resource_group: str) -> list[dict[str, Any]]:
        if self._mode == "live" and self.az_available:
            res = await self._run_az(["lock", "list", "--resource-group", resource_group])
            return res if isinstance(res, list) else []
        if "prod" in resource_group.lower():
            return [
                {
                    "name": "lock-prod-cannot-delete",
                    "level": "CanNotDelete",
                    "notes": "Protected production workload",
                }
            ]
        return []

    async def delete_resource_group(self, resource_group: str, dry_run: bool = False) -> dict[str, Any]:
        if dry_run or self._mode != "live" or not self.az_available:
            return {
                "action": "az group delete",
                "resource_group": resource_group,
                "mode": "simulation" if self._mode != "live" else "dry-run",
                "status": "deleted",
            }
        return await self._run_az(["group", "delete", "--name", resource_group, "--yes", "--no-wait"])
