"""Tests for Tri-Broker fabric (Kafka CloudEvents, RabbitMQ priority/DLQ, Redis locks/PubSub)."""

from __future__ import annotations

import asyncio

from aegisops.application.platform_service import PlatformService
from aegisops.domain.models import CloudEvent, JobStatus, QueueJob


async def test_kafka_rabbitmq_redis_distinct_semantics(platform: PlatformService) -> None:
    # 1. Kafka CloudEvents append & filter
    evt = await platform.kafka.publish(
        "aegis.audit.events",
        CloudEvent(type="io.aegisops.test.audit", subject="test/1", data={"ok": True}),
    )
    listed = await platform.kafka.list_events(topic="aegis.audit.events")
    assert any(item.id == evt.id for item in listed)

    # 2. RabbitMQ priority ordering & DLQ
    low = await platform.rabbitmq.enqueue(
        QueueJob(queue="jobs.terraform", routing_key="tf.plan", priority=2, project_id="p1")
    )
    high = await platform.rabbitmq.enqueue(
        QueueJob(queue="jobs.terraform", routing_key="tf.urgent", priority=9, project_id="p1")
    )
    first = await platform.rabbitmq.dequeue("jobs.terraform")
    assert first is not None and first.id == high.id
    second = await platform.rabbitmq.dequeue("jobs.terraform")
    assert second is not None and second.id == low.id
    await platform.rabbitmq.fail(low.id, "timeout", dead_letter=True)
    assert (await platform.rabbitmq.health())["queued_by_lane"]["jobs.dlq"] == 1
    assert platform.rabbitmq._jobs[low.id].status == JobStatus.DEAD_LETTERED

    # 3. Redis distributed lock & Pub/Sub
    assert await platform.redis.acquire_lock("lock:test", owner="worker-a", ttl_seconds=30)
    assert not await platform.redis.acquire_lock("lock:test", owner="worker-b", ttl_seconds=30)
    assert not await platform.redis.release_lock("lock:test", owner="worker-b")
    assert await platform.redis.release_lock("lock:test", owner="worker-a")

    received: list[dict[str, object]] = []

    async def consumer() -> None:
        async for msg in platform.redis.subscribe_channel("aegis:test"):
            received.append(msg)
            break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.02)
    await platform.redis.publish_channel("aegis:test", {"ping": "pong"})
    await asyncio.wait_for(task, timeout=1.0)
    assert received == [{"ping": "pong"}]
