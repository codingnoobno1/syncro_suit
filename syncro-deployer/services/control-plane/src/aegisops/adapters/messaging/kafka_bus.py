"""Kafka CloudEvents 1.0 adapter with live aiokafka driver and local simulator."""

from __future__ import annotations

from collections import deque
from typing import Any

from aegisops.domain.models import CloudEvent


class KafkaEventBus:
    """Publishes immutable CloudEvents to Kafka topics (or local append-only ring buffer)."""

    TOPICS = (
        "aegis.audit.events",
        "aegis.security.findings",
        "aegis.infra.lifecycle",
        "aegis.destroy.events",
    )

    def __init__(self, bootstrap_servers: str, backend: str = "memory") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._backend = backend
        self._topics: dict[str, deque[CloudEvent]] = {
            topic: deque(maxlen=500) for topic in self.TOPICS
        }
        self._total_published = 0
        self._producer: Any | None = None

    async def start(self) -> None:
        if self._backend == "live":
            try:
                from aiokafka import AIOKafkaProducer

                self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
                await self._producer.start()
            except Exception:
                self._backend = "memory"
                self._producer = None

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, event: CloudEvent) -> CloudEvent:
        enriched = event.model_copy(update={"topic": topic})
        if topic not in self._topics:
            self._topics[topic] = deque(maxlen=500)
        self._topics[topic].appendleft(enriched)
        self._total_published += 1

        if self._producer is not None:
            payload = enriched.model_dump_json().encode("utf-8")
            await self._producer.send_and_wait(topic, payload)

        return enriched

    async def list_events(self, topic: str | None = None, limit: int = 50) -> list[CloudEvent]:
        if topic:
            return list(self._topics.get(topic, deque()))[:limit]
        merged: list[CloudEvent] = []
        for events in self._topics.values():
            merged.extend(events)
        merged.sort(key=lambda evt: evt.time, reverse=True)
        return merged[:limit]

    async def health(self) -> dict[str, Any]:
        return {
            "broker": "kafka",
            "mode": self._backend,
            "bootstrap_servers": self._bootstrap_servers,
            "status": "healthy",
            "topics": {name: len(buf) for name, buf in self._topics.items()},
            "total_published": self._total_published,
        }
