"""Comprehensive robustness tests for Syncro Deployer, SQLite WAL persistence, CircuitBreaker & Suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aegisops.adapters.persistence.journal import SqliteStateJournal
from aegisops.application.platform_service import PlatformService
from aegisops.domain.models import CloudProvider
from aegisops.syncro.models import (
    DeploymentStage,
    DeploymentStrategy,
    DeploymentTargetType,
    DesktopAgentHeartbeat,
    DesktopAgentRegistration,
    SyncroDeployRequest,
    SyncroMode,
)
from aegisops.syncro.resilience import CircuitBreaker, CircuitOpenError, CircuitState, retry_with_backoff


async def test_agentic_vs_manual_devops_modes_and_idempotency(platform: PlatformService) -> None:
    # 1. Agentic Mode auto-progresses 5% -> 25% -> 100%
    agentic_dep = await platform.syncro.deploy(
        SyncroDeployRequest(
            project_id="edge-gateway",
            environment_name="syncro-agentic-01",
            cloud=CloudProvider.GCP,
            target_type=DeploymentTargetType.KUBERNETES,
            strategy=DeploymentStrategy.CANARY,
            mode=SyncroMode.AGENTIC,
            idempotency_key="idem-agentic-001",
        )
    )
    assert agentic_dep.stage == DeploymentStage.PROMOTED_100
    assert agentic_dep.traffic_split == {"stable": 0, "canary": 100}
    assert agentic_dep.idempotent_replay is False

    # Replay with same idempotency_key returns original deployment without re-provisioning
    replayed = await platform.syncro.deploy(
        SyncroDeployRequest(
            project_id="edge-gateway",
            environment_name="syncro-agentic-01",
            idempotency_key="idem-agentic-001",
        )
    )
    assert replayed.id == agentic_dep.id
    assert replayed.idempotent_replay is True

    # 2. Manual DevOps Mode pauses at CANARY_5 until explicit promote gates (25% -> 100%)
    manual_dep = await platform.syncro.deploy(
        SyncroDeployRequest(
            project_id="edge-gateway",
            environment_name="syncro-manual-01",
            cloud=CloudProvider.AWS,
            target_type=DeploymentTargetType.DOCKER,
            image="nginxinc/nginx-unprivileged:1.27-alpine",
            mode=SyncroMode.MANUAL,
        )
    )
    assert manual_dep.stage == DeploymentStage.CANARY_5
    assert manual_dep.traffic_split == {"stable": 95, "canary": 5}

    p25 = await platform.syncro.promote(manual_dep.id, actor="sre-lead")
    assert p25.stage == DeploymentStage.CANARY_25
    assert p25.traffic_split == {"stable": 75, "canary": 25}

    p100 = await platform.syncro.promote(manual_dep.id, actor="sre-lead")
    assert p100.stage == DeploymentStage.PROMOTED_100

    # Manual rollback restores previous revision
    rolled = await platform.syncro.rollback(manual_dep.id, reason="Latency regression")
    assert rolled.stage == DeploymentStage.ROLLED_BACK
    assert rolled.traffic_split == {"stable": 100, "canary": 0}


async def test_automatic_slo_fault_rollback(platform: PlatformService) -> None:
    dep = await platform.syncro.deploy(
        SyncroDeployRequest(
            project_id="edge-gateway",
            environment_name="syncro-faulty-canary",
            cloud=CloudProvider.AZURE,
            target_type=DeploymentTargetType.KUBERNETES,
            mode=SyncroMode.AGENTIC,
            simulate_canary_fault=True,
        )
    )
    assert dep.stage == DeploymentStage.ROLLED_BACK
    assert dep.auto_rolled_back is True
    assert dep.traffic_split == {"stable": 100, "canary": 0}


async def test_circuit_breaker_retry_and_sqlite_wal_persistence(tmp_path: Path) -> None:
    cb = CircuitBreaker("test-downstream", failure_threshold=2, recovery_timeout_seconds=0.05)

    async def failing() -> None:
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(failing)
    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        await cb.call(failing)

    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return "recovered"

    assert await retry_with_backoff(flaky, attempts=3, base_delay_seconds=0.01) == "recovered"

    # Disk SQLite WAL journal survives reload
    db_file = tmp_path / "syncro.db"
    j1 = SqliteStateJournal(db_file)
    j1.save_deployment("sync-persisted", "key-99", "manual", "canary_5", {"id": "sync-persisted"}, "2026-11-20T00:00:00Z")
    j1.close()

    j2 = SqliteStateJournal(db_file)
    loaded = j2.get_deployment_by_idempotency("key-99")
    assert loaded is not None and loaded["id"] == "sync-persisted"
    j2.close()


def test_syncro_suite_and_desktop_agent_api(client: TestClient) -> None:
    suite = client.get("/api/v1/syncro/suite").json()
    mod_ids = {m["id"] for m in suite["modules"]}
    assert {
        "syncro-desktop",
        "syncro-deployer",
        "syncro-cli",
        "syncro-ide",
        "syncro-db",
        "syncro-git",
        "syncro-tester",
    } == mod_ids

    reg = client.post(
        "/api/v1/syncro/agents/register",
        json=DesktopAgentRegistration(
            agent_id="desk-win-01", hostname="dev-win11", os_platform="windows"
        ).model_dump(mode="json"),
    )
    assert reg.status_code == 201

    hb = client.post(
        "/api/v1/syncro/agents/desk-win-01/heartbeat",
        json=DesktopAgentHeartbeat(active_mode=SyncroMode.MANUAL).model_dump(mode="json"),
    )
    assert hb.status_code == 200
    assert hb.json()["active_mode"] == "manual"

    mode_resp = client.post("/api/v1/syncro/mode", json={"mode": "manual"})
    assert mode_resp.status_code == 200 and mode_resp.json()["mode"] == "manual"
    assert client.get("/api/v1/syncro/resilience/health").status_code == 200
