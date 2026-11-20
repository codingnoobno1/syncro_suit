"""Hexagonal Port unifying AWS, GCP, and Azure cloud providers."""

from __future__ import annotations

from typing import Any, Protocol

from aegisops.domain.models import CloudProvider


class CloudProviderPort(Protocol):
    """Uniform contract implemented by AWS, GCP, and Azure adapters."""

    @property
    def cloud(self) -> CloudProvider: ...

    @property
    def lock_mechanism_name(self) -> str: ...

    async def account_status(self) -> dict[str, Any]: ...
    def list_regions(self) -> list[str]: ...
    async def check_delete_protection(self, scope_name: str) -> list[dict[str, Any]]: ...
    async def destroy_scope(self, scope_name: str, dry_run: bool = False) -> dict[str, Any]: ...
