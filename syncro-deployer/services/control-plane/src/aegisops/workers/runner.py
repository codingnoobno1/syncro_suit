"""Async Background Worker consuming RabbitMQ queues and running the Redis TTL Reaper."""

from __future__ import annotations

import asyncio

from aegisops.application.container import build_platform
from aegisops.application.platform_service import PlatformService


async def run_worker_cycle(platform: PlatformService) -> dict[str, int]:
    """Runs a single deterministic worker pass (ephemeral TTL reap + pending queue drain)."""
    reaped = await platform.destroyer.reap_expired_ephemerals()
    processed_jobs = 0
    for queue_name in ("jobs.quick-destroy", "jobs.security-scan", "jobs.terraform", "jobs.ansible"):
        while True:
            job = await platform.rabbitmq.dequeue(queue_name)
            if job is None:
                break
            await platform.rabbitmq.complete(job.id, {"handled_by": "aegis-async-worker"})
            processed_jobs += 1
    return {"reaped_environments": len(reaped), "processed_jobs": processed_jobs}


async def run_worker_forever(poll_interval_seconds: float = 15.0) -> None:
    platform = build_platform()
    await platform.kafka.start()
    await platform.rabbitmq.start()
    await platform.redis.start()
    try:
        while True:
            await run_worker_cycle(platform)
            await asyncio.sleep(poll_interval_seconds)
    finally:
        await platform.redis.stop()
        await platform.rabbitmq.stop()
        await platform.kafka.stop()


if __name__ == "__main__":
    asyncio.run(run_worker_forever())
