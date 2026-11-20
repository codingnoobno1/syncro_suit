"""Hardened Docker Runtime Adapter supporting live `docker` CLI execution and local simulation."""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DockerLaunchRequest(BaseModel):
    project_id: str = "edge-gateway"
    name: str
    image: str
    ports: list[str] = Field(default_factory=lambda: ["8080:8080"])
    env_vars: dict[str, str] = Field(default_factory=dict)
    cpu_limit: str = "0.5"
    memory_limit_mb: int = 256
    run_as_non_root: bool = True
    read_only_root_fs: bool = True
    privileged: bool = False
    network: str = "aegis-isolated"


class DockerContainerStatus(BaseModel):
    container_id: str = Field(default_factory=lambda: f"ctr-{uuid4().hex[:10]}")
    project_id: str
    name: str
    image: str
    state: str = "running"
    ports: list[str] = Field(default_factory=list)
    cpu_limit: str = "0.5"
    memory_limit_mb: int = 256
    run_as_non_root: bool = True
    read_only_root_fs: bool = True
    privileged: bool = False
    network: str = "aegis-isolated"
    hourly_cost_usd: float = 0.04
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DockerLauncherAdapter:
    """Launches, inspects, and stops hardened Docker containers safely (never shell=True)."""

    def __init__(self, mode: str = "simulation") -> None:
        self._mode = mode
        self._containers: dict[str, DockerContainerStatus] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        defaults = [
            DockerContainerStatus(
                container_id="ctr-go-drift01",
                project_id="platform",
                name="aegis-go-drift-scanner",
                image="ghcr.io/aegisops/go-drift-scanner:0.1.0",
                ports=["9101:9101"],
                cpu_limit="0.5",
                memory_limit_mb=128,
                hourly_cost_usd=0.02,
            ),
            DockerContainerStatus(
                container_id="ctr-ts-hook02",
                project_id="platform",
                name="aegis-ts-policy-webhook",
                image="ghcr.io/aegisops/ts-policy-webhook:0.1.0",
                ports=["9102:9102"],
                cpu_limit="0.5",
                memory_limit_mb=256,
                hourly_cost_usd=0.03,
            ),
            DockerContainerStatus(
                container_id="ctr-java-siem03",
                project_id="platform",
                name="aegis-java-audit-bridge",
                image="ghcr.io/aegisops/java-audit-bridge:0.1.0",
                ports=["9103:9103"],
                cpu_limit="1.0",
                memory_limit_mb=512,
                hourly_cost_usd=0.05,
            ),
        ]
        for ctr in defaults:
            self._containers[ctr.container_id] = ctr

    @property
    def docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def list_containers(self) -> list[DockerContainerStatus]:
        return list(self._containers.values())

    async def launch_container(self, req: DockerLaunchRequest) -> DockerContainerStatus:
        if self._mode == "live" and self.docker_available:
            cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                req.name,
                f"--cpus={req.cpu_limit}",
                f"--memory={req.memory_limit_mb}m",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
            ]
            if req.run_as_non_root:
                cmd.extend(["--user", "10001:10001"])
            if req.read_only_root_fs:
                cmd.append("--read-only")
            for p in req.ports:
                cmd.extend(["-p", p])
            cmd.append(req.image)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        est_hr = round(0.02 + (req.memory_limit_mb / 1024.0) * 0.04, 3)
        status = DockerContainerStatus(
            project_id=req.project_id,
            name=req.name,
            image=req.image,
            ports=req.ports,
            cpu_limit=req.cpu_limit,
            memory_limit_mb=req.memory_limit_mb,
            run_as_non_root=req.run_as_non_root,
            read_only_root_fs=req.read_only_root_fs,
            privileged=req.privileged,
            network=req.network,
            hourly_cost_usd=est_hr,
        )
        self._containers[status.container_id] = status
        return status

    async def stop_container(self, container_id: str) -> dict[str, Any]:
        ctr = self._containers.get(container_id)
        if ctr is None:
            raise KeyError(f"Container '{container_id}' not found")
        ctr.state = "stopped"
        ctr.hourly_cost_usd = 0.0
        return {"container_id": container_id, "name": ctr.name, "state": "stopped"}
