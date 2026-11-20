"""Azure CloudProviderPort adapter wrapping AzureCliAdapter."""

from __future__ import annotations

from typing import Any

from aegisops.adapters.azure.azure_cli import AzureCliAdapter
from aegisops.domain.models import CloudProvider


class AzureCloudAdapter:
    """Implements CloudProviderPort for Microsoft Azure."""

    REGIONS = [
        "eastus2",
        "westus3",
        "westeurope",
        "northeurope",
        "southeastasia",
    ]

    def __init__(self, azure_cli: AzureCliAdapter) -> None:
        self._cli = azure_cli

    @property
    def cloud(self) -> CloudProvider:
        return CloudProvider.AZURE

    @property
    def lock_mechanism_name(self) -> str:
        return "Azure CanNotDelete Management Lock"

    async def account_status(self) -> dict[str, Any]:
        status = await self._cli.account_status()
        return {"cloud": "azure", **status}

    def list_regions(self) -> list[str]:
        return list(self.REGIONS)

    async def check_delete_protection(self, scope_name: str) -> list[dict[str, Any]]:
        return await self._cli.check_resource_locks(scope_name)

    async def destroy_scope(self, scope_name: str, dry_run: bool = False) -> dict[str, Any]:
        res = await self._cli.delete_resource_group(scope_name, dry_run=dry_run)
        return {"cloud": "azure", **res}
