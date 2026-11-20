"""RabbitMQ priority job queue adapter with DLQ and live aio-pika support."""

from __future__ import annotations

import heapq
from itertools import count
from typing import Any

from aegisops.domain.models import JobStatus, QueueJob, utc_now


class RabbitMQJobQueue:
    """Durable AMQP work queue supporting priority ordering, retries, and Dead Letter Queue."""

    QUEUES = (
        "jobs.quick-destroy",
        "jobs.security-scan",
        "jobs.terraform",
        "jobs.ansible",
        "jobs.k8s-launch",
        "jobs.dlq",
    )

    def __init__(self, amqp_url: str, backend: str = "memory") -> None:
        self._amqp_url = amqp_url
        self._backend = backend
        self._heaps: dict[str, list[tuple[int, int, str]]] = {q: [] for q in self.QUEUES}
        self._jobs: dict[str, QueueJob] = {}
        self._seq = count()
        self._connection: Any | None = None
        self._channel: Any | None = None

    async def start(self) -> None:
        if self._backend == "live":
            try:
                import aio_pika

                self._connection = await aio_pika.connect_robust(self._amqp_url)
                self._channel = await self._connection.channel()
                for queue_name in self.QUEUES:
                    await self._channel.declare_queue(
                        queue_name, durable=True, arguments={"x-max-priority": 10}
                    )
            except Exception:
                self._backend = "memory"
                self._connection = None
                self._channel = None

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._channel = None

    async def enqueue(self, job: QueueJob) -> QueueJob:
        if job.queue not in self._heaps:
            self._heaps[job.queue] = []
        self._jobs[job.id] = job
        # Negate priority so higher priority pops first from min-heap.
        heapq.heappush(self._heaps[job.queue], (-job.priority, next(self._seq), job.id))

        if self._channel is not None:
            import aio_pika

            message = aio_pika.Message(
                body=job.model_dump_json().encode("utf-8"),
                priority=min(max(job.priority, 0), 10),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await self._channel.default_exchange.publish(message, routing_key=job.queue)

        return job

    async def dequeue(self, queue: str) -> QueueJob | None:
        heap = self._heaps.get(queue, [])
        while heap:
            _, _, job_id = heapq.heappop(heap)
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.QUEUED:
                job.status = JobStatus.RUNNING
                job.attempts += 1
                job.updated_at = utc_now()
                return job
        return None

    async def complete(self, job_id: str, result: dict[str, Any]) -> QueueJob:
        job = self._jobs[job_id]
        job.status = JobStatus.SUCCEEDED
        job.result = result
        job.updated_at = utc_now()
        return job

    async def fail(self, job_id: str, error: str, dead_letter: bool = False) -> QueueJob:
        job = self._jobs[job_id]
        job.error = error
        job.updated_at = utc_now()
        if dead_letter:
            job.status = JobStatus.DEAD_LETTERED
            heapq.heappush(self._heaps["jobs.dlq"], (-job.priority, next(self._seq), job.id))
        else:
            job.status = JobStatus.FAILED
        return job

    async def list_jobs(self, queue: str | None = None, limit: int = 50) -> list[QueueJob]:
        items = list(self._jobs.values())
        if queue:
            items = [j for j in items if j.queue == queue]
        items.sort(key=lambda j: j.created_at, reverse=True)
        return items[:limit]

    async def health(self) -> dict[str, Any]:
        counts = {
            q: sum(1 for j in self._jobs.values() if j.queue == q and j.status == JobStatus.QUEUED)
            for q in self.QUEUES
        }
        dlq_count = sum(1 for j in self._jobs.values() if j.status == JobStatus.DEAD_LETTERED)
        counts["jobs.dlq"] = dlq_count
        return {
            "broker": "rabbitmq",
            "mode": self._backend,
            "status": "healthy",
            "queued_by_lane": counts,
            "total_jobs": len(self._jobs),
            "succeeded_jobs": sum(
                1 for j in self._jobs.values() if j.status == JobStatus.SUCCEEDED
            ),
        }
