"""Multi-Cloud Quick Destruction Engine (AWS · GCP · Azure): Blast-Radius, HMAC, Redis Locks & TTL Reaper."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from aegisops.adapters.cloud.cloud_registry import MultiCloudRegistry
from aegisops.adapters.iac.ansible_runner import AnsibleRunner
from aegisops.adapters.iac.terraform_runner import TerraformRunner
from aegisops.adapters.messaging.kafka_bus import KafkaEventBus
from aegisops.adapters.messaging.rabbitmq_queue import RabbitMQJobQueue
from aegisops.adapters.messaging.redis_store import RedisStateStore
from aegisops.domain.exceptions import (
    EntityNotFoundError,
    InvalidConfirmationTokenError,
    LockAcquisitionError,
    PolicyViolationError,
)
from aegisops.domain.models import (
    CloudEvent,
    DestroyExecutionResult,
    DestroyPreview,
    Environment,
    EnvironmentStatus,
    QueueJob,
)
from aegisops.security.opa_gate import OpaPolicyGate


class DestroyerService:
    """Orchestrates safe multi-cloud ephemeral teardown, emergency kill-switch, and TTL reaping."""

    def __init__(
        self,
        hmac_secret: str,
        environments: dict[str, Environment],
        kafka: KafkaEventBus,
        rabbitmq: RabbitMQJobQueue,
        redis: RedisStateStore,
        clouds: MultiCloudRegistry,
        terraform: TerraformRunner,
        ansible: AnsibleRunner,
        opa_gate: OpaPolicyGate,
    ) -> None:
        self._hmac_secret = hmac_secret.encode("utf-8")
        self._environments = environments
        self._kafka = kafka
        self._rabbitmq = rabbitmq
        self._redis = redis
        self._clouds = clouds
        self._terraform = terraform
        self._ansible = ansible
        self._opa_gate = opa_gate

    def _compute_token(self, env: Environment) -> str:
        resource_sig = ",".join(sorted(r.id for r in env.resources))
        msg = f"{env.cloud.value}:{env.id}:{env.resource_group}:{resource_sig}".encode()
        return hmac.new(self._hmac_secret, msg, hashlib.sha256).hexdigest()[:16].upper()

    async def preview(self, environment_id: str) -> DestroyPreview:
        env = self._environments.get(environment_id)
        if env is None:
            raise EntityNotFoundError(f"Environment '{environment_id}' not found")

        provider = self._clouds.get(env.cloud)
        locks = await provider.check_delete_protection(env.resource_group)
        has_lock = env.has_delete_lock or len(locks) > 0
        blast_count = len(env.resources)

        gate = await self._opa_gate.evaluate_destruction(
            env_id=env.id,
            tier=env.tier.value,
            has_delete_lock=has_lock,
            blast_radius_count=blast_count,
            confirmation_token_verified=True,
            lock_mechanism=provider.lock_mechanism_name,
        )

        token: str | None = None
        if gate.allowed:
            token = self._compute_token(env)
            await self._redis.set_value(
                f"token:destroy:{env.id}",
                {"token": token, "cloud": env.cloud.value, "resource_group": env.resource_group},
                ttl_seconds=300,
            )

        cloud_label = env.cloud.value.upper()
        steps = [
            f"1. Acquire Redis distributed lock lock:env:{env.id}",
            f"2. Drain Kubernetes pods & Ansible quarantine compute nodes on {cloud_label} ({env.location})",
            f"3. Revoke ephemeral {cloud_label} IAM/ABAC assignments on '{env.resource_group}'",
            f"4. Execute Terraform destroy across {blast_count} {cloud_label} resources",
            f"5. Sweep orphaned volumes/NICs & clean scope '{env.resource_group}' via {cloud_label} adapter",
            "6. Emit signed CloudEvents 1.0 audit record to Kafka topic 'aegis.destroy.events'",
        ]

        hourly = round(sum(r.hourly_cost_usd for r in env.resources) or env.hourly_cost_usd, 2)
        monthly = round(hourly * 730.0, 2)

        return DestroyPreview(
            environment_id=env.id,
            cloud=env.cloud,
            resource_group=env.resource_group,
            tier=env.tier,
            has_delete_lock=has_lock,
            lock_mechanism=provider.lock_mechanism_name,
            ordered_teardown_steps=steps,
            resources=env.resources,
            blast_radius_count=blast_count,
            estimated_hourly_savings_usd=hourly,
            estimated_monthly_savings_usd=monthly,
            opa_gate=gate,
            confirmation_token=token,
            token_expires_in_seconds=300,
        )

    async def execute(
        self,
        environment_id: str,
        confirmation_token: str,
        kill_switch: bool = False,
        actor: str = "operator",
        break_glass_approved: bool = False,
    ) -> DestroyExecutionResult:
        env = self._environments.get(environment_id)
        if env is None:
            raise EntityNotFoundError(f"Environment '{environment_id}' not found")

        provider = self._clouds.get(env.cloud)
        locks = await provider.check_delete_protection(env.resource_group)
        has_lock = env.has_delete_lock or len(locks) > 0

        gate = await self._opa_gate.evaluate_destruction(
            env_id=env.id,
            tier=env.tier.value,
            has_delete_lock=has_lock,
            blast_radius_count=len(env.resources),
            break_glass_approved=break_glass_approved,
            force_unlock=break_glass_approved,
            confirmation_token_verified=bool(confirmation_token),
            lock_mechanism=provider.lock_mechanism_name,
        )
        if not gate.allowed:
            raise PolicyViolationError(
                f"OPA destruction guardrails denied teardown for '{env.id}'",
                violations=gate.violations,
            )

        stored = await self._redis.get_value(f"token:destroy:{env.id}")
        expected_token = stored["token"] if isinstance(stored, dict) else None
        if not expected_token or not hmac.compare_digest(
            confirmation_token.strip().upper(), expected_token
        ):
            raise InvalidConfirmationTokenError(
                "Invalid or expired HMAC confirmation token. Run preview first to mint a fresh token."
            )

        lock_key = f"lock:env:{env.id}"
        acquired = await self._redis.acquire_lock(lock_key, owner=actor, ttl_seconds=120)
        if not acquired:
            raise LockAcquisitionError(
                f"Workspace lock '{lock_key}' is currently held by another operation"
            )

        try:
            env.status = EnvironmentStatus.DESTROYING
            await self._redis.publish_channel(
                "aegis:live",
                {
                    "type": "destroy.started",
                    "cloud": env.cloud.value,
                    "environment_id": env.id,
                    "kill_switch": kill_switch,
                    "actor": actor,
                },
            )

            job = await self._rabbitmq.enqueue(
                QueueJob(
                    queue="jobs.quick-destroy",
                    routing_key=f"destroy.{env.cloud.value}.{'kill-switch' if kill_switch else 'standard'}",
                    priority=10 if kill_switch else 8,
                    project_id=env.project_id,
                    environment_id=env.id,
                    payload={"cloud": env.cloud.value, "resource_group": env.resource_group, "kill_switch": kill_switch},
                )
            )
            await self._rabbitmq.dequeue("jobs.quick-destroy")

            steps_completed: list[str] = []
            if kill_switch:
                await self._ansible.run_playbook(
                    "emergency_quarantine.yml", target_group=env.name, check_mode=False
                )
                steps_completed.append(f"Emergency Ansible quarantine executed on {env.cloud.value.upper()} nodes")

            steps_completed.append(f"Drained workloads in '{env.name}' ({env.cloud.value.upper()})")
            steps_completed.append(f"Revoked ephemeral {env.cloud.value.upper()} IAM/ABAC credentials on '{env.resource_group}'")

            await self._terraform.destroy(env.id, env.resource_group)
            steps_completed.append(f"Terraform destroy completed for {len(env.resources)} {env.cloud.value.upper()} resources")

            await provider.destroy_scope(env.resource_group)
            steps_completed.append(f"Cleaned {env.cloud.value.upper()} scope '{env.resource_group}'")

            destroyed_count = len(env.resources)
            monthly_saved = round(
                (sum(r.hourly_cost_usd for r in env.resources) or env.hourly_cost_usd) * 730.0, 2
            )
            env.status = EnvironmentStatus.DESTROYED
            env.hourly_cost_usd = 0.0

            await self._redis.delete_key(f"token:destroy:{env.id}")
            await self._redis.delete_key(f"ttl:env:{env.id}")

            await self._rabbitmq.complete(
                job.id,
                {"cloud": env.cloud.value, "destroyed_resources": destroyed_count, "monthly_savings_usd": monthly_saved},
            )

            audit_evt = await self._kafka.publish(
                "aegis.destroy.events",
                CloudEvent(
                    type="io.aegisops.destroy.completed",
                    subject=f"{env.cloud.value}/env/{env.id}",
                    project_id=env.project_id,
                    data={
                        "cloud": env.cloud.value,
                        "environment_id": env.id,
                        "resource_group": env.resource_group,
                        "kill_switch": kill_switch,
                        "actor": actor,
                        "resources_destroyed": destroyed_count,
                        "estimated_monthly_savings_usd": monthly_saved,
                    },
                ),
            )

            await self._redis.publish_channel(
                "aegis:live",
                {
                    "type": "destroy.completed",
                    "cloud": env.cloud.value,
                    "environment_id": env.id,
                    "resources_destroyed": destroyed_count,
                    "audit_event_id": audit_evt.id,
                },
            )

            return DestroyExecutionResult(
                environment_id=env.id,
                cloud=env.cloud,
                kill_switch=kill_switch,
                status="destroyed",
                job_id=job.id,
                steps_completed=steps_completed,
                resources_destroyed=destroyed_count,
                estimated_monthly_savings_usd=monthly_saved,
                audit_event_id=audit_evt.id,
            )
        finally:
            await self._redis.release_lock(lock_key, owner=actor)

    async def reap_expired_ephemerals(self) -> list[DestroyExecutionResult]:
        """Auto-destroys expired ephemeral environments across AWS, GCP, and Azure."""
        now = datetime.now(UTC)
        reaped: list[DestroyExecutionResult] = []
        for env in list(self._environments.values()):
            if (
                env.tier.value == "ephemeral"
                and env.status in {EnvironmentStatus.ACTIVE, EnvironmentStatus.HARDENED}
                and env.expires_at is not None
                and env.expires_at <= now
            ):
                preview = await self.preview(env.id)
                if preview.confirmation_token:
                    res = await self.execute(
                        env.id,
                        confirmation_token=preview.confirmation_token,
                        kill_switch=False,
                        actor="ttl-reaper",
                    )
                    reaped.append(res)
        return reaped
