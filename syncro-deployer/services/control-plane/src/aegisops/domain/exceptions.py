"""Typed domain exception hierarchy."""

from __future__ import annotations


class AegisError(Exception):
    """Base domain error."""


class EntityNotFoundError(AegisError):
    """Raised when a project, environment, or extension cannot be located."""


class PolicyViolationError(AegisError):
    """Raised when an OPA policy gate denies an operation."""

    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        super().__init__(message)
        self.violations = violations or []


class LockAcquisitionError(AegisError):
    """Raised when a Redis distributed workspace lock is already held."""


class InvalidConfirmationTokenError(AegisError):
    """Raised when a Quick Destruction HMAC token is missing, invalid, or expired."""
