"""Shared pytest fixtures for AegisOps control plane tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aegisops.api.app import create_app
from aegisops.application.container import build_platform
from aegisops.application.platform_service import PlatformService


@pytest.fixture()
def platform() -> PlatformService:
    return build_platform(seed_demo=True)


@pytest.fixture()
def client(platform: PlatformService) -> TestClient:
    app = create_app(platform=platform)
    with TestClient(app) as tc:
        yield tc
