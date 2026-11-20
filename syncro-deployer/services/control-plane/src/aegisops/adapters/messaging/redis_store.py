"""Redis distributed locks, TTL registry, state cache, and Pub/Sub adapter."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any


class RedisStateStore:
    """Provides SET NX PX workspace locks, TTL keys, caching, and Pub/Sub fanout."""

    def __init__(self, redis_url: str, backend: str = "memory") -> None:
        self._redis_url = redis_url
        self._backend = backend
        self._kv: dict[str, tuple[Any, float | None]] = {}
        self._locks: dict[str, tuple[str, float]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._pubsub_count = 0
        self._client: Any | None = None

    async def start(self) -> None:
        if self._backend == "live":
            try:
                import redis.asyncio as aioredis

                client = aioredis.from_url(self._redis_url, decode_responses=True)
                await client.ping()
                self._client = client
            except Exception:
                self._backend = "memory"
                self._client = None

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired_kv = [k for k, (_, exp) in self._kv.items() if exp is not None and exp <= now]
        for key in expired_kv:
            self._kv.pop(key, None)
        expired_locks = [k for k, (_, exp) in self._locks.items() if exp <= now]
        for key in expired_locks:
            self._locks.pop(key, None)

    async def acquire_lock(self, key: str, owner: str, ttl_seconds: int = 60) -> bool:
        if self._client is not None:
            ok = await self._client.set(key, owner, nx=True, ex=ttl_seconds)
            return bool(ok)
        self._evict_expired()
        if key in self._locks:
            return False
        self._locks[key] = (owner, time.monotonic() + ttl_seconds)
        return True

    async def release_lock(self, key: str, owner: str) -> bool:
        if self._client is not None:
            current = await self._client.get(key)
            if current == owner:
                await self._client.delete(key)
                return True
            return False
        self._evict_expired()
        existing = self._locks.get(key)
        if existing and existing[0] == owner:
            del self._locks[key]
            return True
        return False

    async def set_value(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        if self._client is not None:
            raw = json.dumps(value)
            if ttl_seconds is not None:
                await self._client.setex(key, ttl_seconds, raw)
            else:
                await self._client.set(key, raw)
            return
        exp = (time.monotonic() + ttl_seconds) if ttl_seconds is not None else None
        self._kv[key] = (value, exp)

    async def get_value(self, key: str) -> Any | None:
        if self._client is not None:
            raw = await self._client.get(key)
            return json.loads(raw) if raw is not None else None
        self._evict_expired()
        entry = self._kv.get(key)
        return entry[0] if entry is not None else None

    async def delete_key(self, key: str) -> None:
        if self._client is not None:
            await self._client.delete(key)
            return
        self._kv.pop(key, None)

    async def get_ttl(self, key: str) -> int | None:
        if self._client is not None:
            ttl = await self._client.ttl(key)
            return int(ttl) if ttl >= 0 else None
        self._evict_expired()
        entry = self._kv.get(key)
        if entry is None or entry[1] is None:
            return None
        return max(0, int(entry[1] - time.monotonic()))

    async def publish_channel(self, channel: str, payload: dict[str, Any]) -> None:
        self._pubsub_count += 1
        if self._client is not None:
            await self._client.publish(channel, json.dumps(payload))
        for q in list(self._subscribers.get(channel, set())):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await q.put(payload)

    async def subscribe_channel(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(channel, set()).add(q)
        try:
            while True:
                item = await q.get()
                yield item
        finally:
            self._subscribers.get(channel, set()).discard(q)

    async def health(self) -> dict[str, Any]:
        self._evict_expired()
        return {
            "broker": "redis",
            "mode": self._backend,
            "status": "healthy",
            "active_locks": list(self._locks.keys()),
            "cached_keys": len(self._kv),
            "pubsub_messages_published": self._pubsub_count,
            "active_ws_subscribers": sum(len(s) for s in self._subscribers.values()),
        }
