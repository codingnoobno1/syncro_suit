"""Multi-Cloud Provider Registry unifying AWS, GCP, and Azure behind a single facade."""

from __future__ import annotations

from typing import Any

from aegisops.domain.models import CloudProvider
from aegisops.ports.cloud import CloudProviderPort


class MultiCloudRegistry:
    """Dispatches operations across AWS, GCP, and Azure adapters uniformly."""

    def __init__(self, providers: dict[CloudProvider, CloudProviderPort]) -> None:
        self._providers = providers

    def get(self, cloud: CloudProvider) -> CloudProviderPort:
        return self._providers[cloud]

    def list_regions_by_cloud(self) -> dict[str, list[str]]:
        return {cloud.value: adapter.list_regions() for cloud, adapter in self._providers.items()}

    async def all_statuses(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for cloud, adapter in self._providers.items():
            out[cloud.value] = await adapter.account_status()
        return out
