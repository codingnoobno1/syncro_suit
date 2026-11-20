"""Typed runtime settings loaded from environment variables (AWS + GCP + Azure)."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "policies" / "opa").exists():
            return parent
    return Path.cwd()


class Settings(BaseSettings):
    """Application settings with strict defaults safe for local simulation and prod."""

    model_config = SettingsConfigDict(env_prefix="AEGIS_", env_file=".env", extra="ignore")

    mode: Literal["simulation", "live"] = "simulation"
    broker_backend: Literal["memory", "live"] = "memory"
    env: str = "dev"
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8080
    mcp_port: int = 8090
    hmac_secret: str = Field(default_factory=lambda: secrets.token_hex(24))

    # Azure target defaults
    azure_subscription_id: str = Field(
        default="11111111-2222-3333-4444-555555555555",
        alias="AZURE_SUBSCRIPTION_ID",
    )
    azure_tenant_id: str = Field(
        default="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        alias="AZURE_TENANT_ID",
    )
    azure_location: str = Field(default="eastus2", alias="AZURE_LOCATION")

    # AWS target defaults
    aws_account_id: str = Field(default="420198765432", alias="AWS_ACCOUNT_ID")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")

    # GCP target defaults
    gcp_project_id: str = Field(default="aegisops-devsecops-sim", alias="GCP_PROJECT_ID")
    gcp_region: str = Field(default="us-central1", alias="GCP_REGION")

    # Tri-Broker Fabric
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    rabbitmq_url: str = Field(
        default="amqp://aegis:aegis-dev-pass@localhost:5672/aegis",
        alias="RABBITMQ_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    max_critical_findings: int = 0
    max_high_findings: int = 5
    protected_envs: str = "prod,production,shared-core"
    k8s_namespace: str = "aegisops"

    repo_root: Path = Field(default_factory=_default_repo_root)

    @property
    def protected_env_set(self) -> set[str]:
        return {item.strip().lower() for item in self.protected_envs.split(",") if item.strip()}

    @property
    def opa_policy_dir(self) -> Path:
        return self.repo_root / "policies" / "opa"

    @property
    def terraform_dir(self) -> Path:
        return self.repo_root / "infra" / "terraform"

    @property
    def ansible_dir(self) -> Path:
        return self.repo_root / "infra" / "ansible"

    @property
    def powershell_dir(self) -> Path:
        return self.repo_root / "infra" / "powershell"

    @property
    def k8s_dir(self) -> Path:
        return self.repo_root / "deploy" / "k8s"
