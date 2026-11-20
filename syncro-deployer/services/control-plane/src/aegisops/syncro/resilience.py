"""Production resilience primitives: CircuitBreaker and async exponential backoff retries."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a downstream dependency circuit breaker is open."""


class CircuitBreaker:
    """Protects external cloud/extension calls against cascading failures."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and (time.monotonic() - self._opened_at) >= self._recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        current = self.state
        if current == CircuitState.OPEN:
            raise CircuitOpenError(f"Circuit breaker '{self.name}' is OPEN")
        try:
            result = await fn()
        except Exception:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
            raise
        else:
            self._failure_count = 0
            self._success_count += 1
            self._state = CircuitState.CLOSED
            self._opened_at = None
            return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self._failure_threshold,
            "recovery_timeout_seconds": self._recovery_timeout,
        }


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    attempts: int = 3,
    base_delay_seconds: float = 0.05,
) -> T:
    """Executes an async operation with bounded exponential backoff retries."""
    last_exc: Exception | None = None
    for idx in range(max(1, attempts)):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if idx < attempts - 1:
                await asyncio.sleep(base_delay_seconds * (2**idx))
    assert last_exc is not None
    raise last_exc
