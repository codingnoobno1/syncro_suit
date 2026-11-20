"""Tests for Quick Destruction blast-radius preview, HMAC tokens, Redis locks, kill-switch, and TTL reaper."""

from __future__ import annotations

from datetime import timedelta

import pytest

from aegisops.application.platform_service import PlatformService
from aegisops.domain.exceptions import (
    InvalidConfirmationTokenError,
    LockAcquisitionError,
    PolicyViolationError,
)
from aegisops.domain.models import EnvironmentStatus, utc_now
from aegisops.workers.runner import run_worker_cycle


async def test_production_env_blocked_by_opa_guardrails(platform: PlatformService) -> None:
    preview = await platform.destroyer.preview("env-prod-core")
    assert preview.opa_gate.allowed is False
    assert preview.confirmation_token is None
    assert preview.has_delete_lock is True

    with pytest.raises(PolicyViolationError):
        await platform.destroyer.execute("env-prod-core", confirmation_token="FAKE", kill_switch=True)


async def test_ephemeral_quick_destroy_and_kill_switch_lifecycle(platform: PlatformService) -> None:
    preview = await platform.destroyer.preview("env-pr-412")
    assert preview.opa_gate.allowed is True
    assert preview.confirmation_token is not None
    assert preview.blast_radius_count == 4
    assert preview.estimated_monthly_savings_usd > 0

    with pytest.raises(InvalidConfirmationTokenError):
        await platform.destroyer.execute("env-pr-412", confirmation_token="WRONGTOKEN")

    # Simulate distributed lock contention
    assert await platform.redis.acquire_lock("lock:env:env-pr-412", owner="other-worker", ttl_seconds=60)
    with pytest.raises(LockAcquisitionError):
        await platform.destroyer.execute(
            "env-pr-412", confirmation_token=preview.confirmation_token, kill_switch=True
        )
    assert await platform.redis.release_lock("lock:env:env-pr-412", owner="other-worker")

    result = await platform.destroyer.execute(
        "env-pr-412",
        confirmation_token=preview.confirmation_token,
        kill_switch=True,
        actor="sec-ops",
    )
    assert result.status == "destroyed"
    assert result.kill_switch is True
    assert result.resources_destroyed == 4
    assert platform.environments["env-pr-412"].status == EnvironmentStatus.DESTROYED

    events = await platform.kafka.list_events(topic="aegis.destroy.events")
    assert any(e.id == result.audit_event_id for e in events)


async def test_ttl_auto_reaper_destroys_expired_ephemerals(platform: PlatformService) -> None:
    platform.environments["env-staging-edge"].expires_at = utc_now() - timedelta(minutes=5)
    stats = await run_worker_cycle(platform)
    assert stats["reaped_environments"] == 1
    assert platform.environments["env-staging-edge"].status == EnvironmentStatus.DESTROYED
    assert platform.environments["env-prod-core"].status == EnvironmentStatus.HARDENED
