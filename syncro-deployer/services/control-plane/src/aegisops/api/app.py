"""FastAPI Multi-Cloud Control Plane (AWS · GCP · Azure), VM Selector, FinOps, Drift, WebSockets & MCP Host."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aegisops import __version__
from aegisops.adapters.cloud.cli_wrapper import CliExecutionRequest, CliProvider
from aegisops.adapters.docker.docker_launcher import DockerLaunchRequest
from aegisops.application.container import build_platform
from aegisops.application.platform_service import PlatformService
from aegisops.bot.models import BotGuardrailSettings, UserPromptDirectives
from aegisops.config import Settings
from aegisops.domain.exceptions import (
    EntityNotFoundError,
    InvalidConfirmationTokenError,
    LockAcquisitionError,
    PolicyViolationError,
)
from aegisops.domain.models import (
    CloudProvider,
    ExtensionPlugin,
    K8sLaunchRequest,
    Project,
    VmProvisionRequest,
    VmSelectionCriteria,
)
from aegisops.iac.models import (
    AnsibleGenerateRequest,
    CicdGenerateRequest,
    ContainerGenerateRequest,
    HelmGenerateRequest,
    TerraformGenerateRequest,
    TerraformRunRequest,
)
from aegisops.mcp.server import AegisMcpServer
from aegisops.syncro.models import (
    DesktopAgentHeartbeat,
    DesktopAgentRegistration,
    SyncroDeployRequest,
    SyncroMode,
)


class ScanRequestBody(BaseModel):
    project_id: str = "payments-core"
    target_path: str | None = None
    scanners: list[str] = Field(
        default_factory=lambda: ["checkov", "trivy", "bandit", "tfsec", "opa"]
    )


class TerraformPlanBody(BaseModel):
    project_id: str = "payments-core"
    environment_id: str = "env-pr-412"
    cloud: CloudProvider = CloudProvider.AZURE
    ttl_hours: int = 4


class AnsibleRunBody(BaseModel):
    project_id: str = "payments-core"
    playbook: str = "cis_azure_linux.yml"
    target_group: str = "aegis_ephemeral"
    check_mode: bool = False


class DestroyExecuteBody(BaseModel):
    confirmation_token: str
    kill_switch: bool = False
    actor: str = "dashboard-operator"
    break_glass_approved: bool = False


class RbacPlanBody(BaseModel):
    cloud: CloudProvider = CloudProvider.AZURE
    resource_group: str = "rg-aegis-payments-pr-412"
    principal_object_id: str = "7b8f12c0-4a91-4d30-9f1a-000000000101"
    personas: list[str] = Field(default_factory=lambda: ["auditor", "deployer", "destroyer"])
    pim_max_duration_hours: int = 1
    requested_role_override: str | None = None


class ExtensionHookBody(BaseModel):
    hook_name: str = "drift_check"
    payload: dict[str, Any] = Field(default_factory=dict)


class CloudCliProviderBody(BaseModel):
    args: list[str] = Field(min_length=1, max_length=64)
    dry_run: bool = False
    allow_destructive: bool = False
    allow_secrets: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    subscription_or_project: str | None = None
    region: str | None = None
    actor: str = "electron-desktop"


class TerraformBuildBody(BaseModel):
    workspace_id: str | None = None
    workspace_dir: str | None = None


class DevSecOpsGraphBody(BaseModel):
    workspace_id: str | None = None
    workspace_dir: str | None = None
    include_pipeline: bool = True


class SecurityPathAssessBody(BaseModel):
    project_id: str = "syncro-workspace"
    target_path: str | None = None


class SecurityDastBody(BaseModel):
    project_id: str = "syncro-workspace"
    target_url: str = "http://127.0.0.1:8080/api/v1/health"
    live_probe: bool = True


class SecurityFullAssessBody(BaseModel):
    project_id: str = "payments-core"
    target_path: str | None = None
    target_url: str | None = "http://127.0.0.1:8080/api/v1/health"
    include_dast: bool = True
    include_graph: bool = True
    live_dast_probe: bool = True


def create_app(
    settings: Settings | None = None,
    platform: PlatformService | None = None,
) -> FastAPI:
    svc = platform or build_platform(settings=settings, seed_demo=True)
    mcp_server = AegisMcpServer(svc)
    boot_monotonic = time.monotonic()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await svc.kafka.start()
        await svc.rabbitmq.start()
        await svc.redis.start()
        yield
        await svc.redis.stop()
        await svc.rabbitmq.stop()
        await svc.kafka.stop()

    app = FastAPI(
        title="AegisOps / Syncro Multi-Cloud DevSecOps Control Plane (AWS · GCP · Azure)",
        version=__version__,
        description=(
            "Polyglot-extensible Multi-Cloud DevSecOps Control Plane with Guardrailed Azure/GCP/AWS "
            "CLI Wrapper MCP, Intelligent VM Selector, Tri-Broker Fabric (Kafka + RabbitMQ + Redis), "
            "Security Pipeline, Quick Destruction, FinOps Analytics, and Least-Privilege IAM/PowerShell Planning."
        ),
        lifespan=lifespan,
    )
    app.state.platform = svc
    app.state.mcp = mcp_server

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observability_and_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        req_id = request.headers.get("X-Request-Id") or f"req-{uuid.uuid4().hex[:12]}"
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        response.headers["X-Request-Id"] = req_id
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "detail": str(exc)},
        )

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        cli_status = await svc.cloud_cli.toolchain_status()
        return {
            "status": "ok",
            "version": __version__,
            "mode": svc.settings.mode,
            "uptime_seconds": round(time.monotonic() - boot_monotonic, 2),
            "clouds": ["aws", "gcp", "azure"],
            "cloud_clis": {
                k: {
                    "installed": v["installed"],
                    "execution_mode": v["execution_mode"],
                    "mcp_tool": v["mcp_tool"],
                }
                for k, v in cli_status["cloud_clis"].items()
            },
            "mcp_tools_count": len(mcp_server.list_tools()),
        }

    @app.get("/api/v1/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/api/v1/health/ready")
    async def health_ready() -> dict[str, Any]:
        brokers = await svc.broker_health()
        return {
            "status": "ready",
            "brokers": brokers,
            "journal": svc.syncro.resilience_health()["journal"],
        }

    @app.get("/api/v1/overview")
    async def overview() -> dict[str, Any]:
        return await svc.overview_snapshot()

    @app.get("/api/v1/clouds/status")
    async def clouds_status() -> dict[str, Any]:
        return {
            "accounts": await svc.clouds.all_statuses(),
            "regions": svc.clouds.list_regions_by_cloud(),
        }

    @app.get("/api/v1/finops/summary")
    async def finops_summary() -> dict[str, Any]:
        return svc.finops_summary().model_dump(mode="json")

    # =========================================================================
    # Multi-Cloud VM Selector, Cross-Cloud Comparator & Provisioner
    # =========================================================================
    @app.get("/api/v1/vms/catalog")
    async def list_vm_catalog(cloud: CloudProvider | None = None) -> list[dict[str, Any]]:
        return [sku.model_dump(mode="json") for sku in svc.vm_selector.list_catalog(cloud)]

    @app.post("/api/v1/vms/recommend")
    async def recommend_vms(criteria: VmSelectionCriteria) -> list[dict[str, Any]]:
        return [r.model_dump(mode="json") for r in svc.vm_selector.recommend(criteria)]

    @app.post("/api/v1/vms/compare")
    async def compare_vms_across_clouds(criteria: VmSelectionCriteria) -> dict[str, Any]:
        return svc.vm_selector.compare_clouds(criteria).model_dump(mode="json")

    @app.post("/api/v1/vms/provision", status_code=201)
    async def provision_vm(req: VmProvisionRequest) -> dict[str, Any]:
        try:
            res = await svc.vm_selector.provision_ephemeral_vm(req)
            return res.model_dump(mode="json")
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # =========================================================================
    # Projects, Environments & Drift Detection
    # =========================================================================
    @app.get("/api/v1/projects")
    async def list_projects() -> list[dict[str, Any]]:
        return [p.model_dump(mode="json") for p in svc.projects.values()]

    @app.post("/api/v1/projects", status_code=201)
    async def create_project(project: Project) -> dict[str, Any]:
        saved = await svc.register_project(project)
        return saved.model_dump(mode="json")

    @app.get("/api/v1/environments")
    async def list_environments(cloud: CloudProvider | None = None) -> list[dict[str, Any]]:
        envs = list(svc.environments.values())
        if cloud is not None:
            envs = [e for e in envs if e.cloud == cloud]
        return [e.model_dump(mode="json") for e in envs]

    @app.post("/api/v1/drift/{environment_id}/check")
    async def check_drift(environment_id: str) -> dict[str, Any]:
        try:
            report = await svc.run_drift_check(environment_id)
            return report.model_dump(mode="json")
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # =========================================================================
    # Security Pipeline, OPA Gates & SARIF
    # =========================================================================
    @app.post("/api/v1/scans")
    async def trigger_scan(body: ScanRequestBody) -> dict[str, Any]:
        report = await svc.run_security_scan(
            project_id=body.project_id,
            target_path=body.target_path,
            scanners=body.scanners,
        )
        return report.model_dump(mode="json")

    @app.get("/api/v1/scans")
    async def list_scans() -> list[dict[str, Any]]:
        return [s.model_dump(mode="json") for s in svc.scan_history[:25]]

    @app.get("/api/v1/scans/{scan_id}/sarif")
    async def get_scan_sarif(scan_id: str) -> dict[str, Any]:
        try:
            return svc.export_scan_sarif(scan_id)
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/policies/opa")
    async def list_opa_policies() -> list[dict[str, str]]:
        return svc.opa_gate.list_policy_files()

    # =========================================================================
    # Terraform, Ansible & Kubernetes Launcher
    # =========================================================================
    @app.post("/api/v1/infra/terraform/plan")
    async def terraform_plan(body: TerraformPlanBody) -> dict[str, Any]:
        return await svc.plan_terraform(
            project_id=body.project_id,
            environment_id=body.environment_id,
            ttl_hours=body.ttl_hours,
            cloud=body.cloud,
        )

    @app.post("/api/v1/infra/ansible/run")
    async def ansible_run(body: AnsibleRunBody) -> dict[str, Any]:
        try:
            return await svc.run_ansible_hardening(
                project_id=body.project_id,
                playbook=body.playbook,
                target_group=body.target_group,
                check_mode=body.check_mode,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/k8s/launch")
    async def k8s_launch(body: K8sLaunchRequest) -> dict[str, Any]:
        result = await svc.launch_kubernetes_workload(body)
        return result.model_dump(mode="json")

    @app.get("/api/v1/k8s/launches")
    async def list_k8s_launches() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in svc.k8s_launches[:25]]

    # =========================================================================
    # Multi-Cloud Quick Destruction & IAM/PowerShell Planner
    # =========================================================================
    @app.post("/api/v1/destroy/{environment_id}/preview")
    async def destroy_preview(environment_id: str) -> dict[str, Any]:
        try:
            preview = await svc.destroyer.preview(environment_id)
            return preview.model_dump(mode="json")
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/destroy/{environment_id}/execute")
    async def destroy_execute(environment_id: str, body: DestroyExecuteBody) -> dict[str, Any]:
        try:
            res = await svc.destroyer.execute(
                environment_id=environment_id,
                confirmation_token=body.confirmation_token,
                kill_switch=body.kill_switch,
                actor=body.actor,
                break_glass_approved=body.break_glass_approved,
            )
            return res.model_dump(mode="json")
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PolicyViolationError as exc:
            raise HTTPException(
                status_code=403, detail={"message": str(exc), "violations": exc.violations}
            ) from exc
        except InvalidConfirmationTokenError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LockAcquisitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/rbac/powershell-plan")
    async def rbac_plan(body: RbacPlanBody) -> dict[str, Any]:
        plan = await svc.generate_powershell_rbac_plan(
            resource_group=body.resource_group,
            principal_object_id=body.principal_object_id,
            personas=body.personas,
            pim_max_duration_hours=body.pim_max_duration_hours,
            requested_role_override=body.requested_role_override,
            cloud=body.cloud,
        )
        return plan.model_dump(mode="json")

    # =========================================================================
    # Guardrailed MCP Ops Bot (VMs, K8s, Docker, Live Bill Reader & Self-Prompting)
    # =========================================================================
    @app.get("/api/v1/bot/status")
    async def bot_read_all_statuses() -> dict[str, Any]:
        return (await svc.bot.read_all_statuses()).model_dump(mode="json")

    @app.get("/api/v1/bot/bill")
    async def bot_read_live_bill() -> dict[str, Any]:
        return svc.bot.read_live_bill().model_dump(mode="json")

    @app.get("/api/v1/bot/guardrails")
    async def bot_get_guardrails() -> dict[str, Any]:
        return svc.bot.guardrail_engine.settings.model_dump(mode="json")

    @app.put("/api/v1/bot/guardrails")
    async def bot_put_guardrails(body: BotGuardrailSettings) -> dict[str, Any]:
        return svc.bot.update_guardrails(body).model_dump(mode="json")

    @app.get("/api/v1/bot/directives")
    async def bot_get_directives() -> dict[str, Any]:
        return svc.bot.directives.model_dump(mode="json")

    @app.put("/api/v1/bot/directives")
    async def bot_put_directives(body: UserPromptDirectives) -> dict[str, Any]:
        return svc.bot.update_directives(body).model_dump(mode="json")

    @app.get("/api/v1/bot/traffic-playbooks")
    async def bot_traffic_playbooks() -> list[dict[str, str]]:
        return svc.bot.prompt_composer.list_traffic_playbooks()

    @app.post("/api/v1/bot/prompts/generate")
    async def bot_generate_prompts(body: dict[str, Any] | None = None) -> dict[str, Any]:
        custom = str((body or {}).get("custom_user_prompt") or "") or None
        return svc.bot.generate_prompts(custom_user_prompt=custom).model_dump(mode="json")

    @app.post("/api/v1/bot/self-prompt/run")
    async def bot_run_self_prompt(body: dict[str, Any] | None = None) -> dict[str, Any]:
        custom = str((body or {}).get("custom_user_prompt") or "") or None
        res = await svc.bot.run_self_prompt_bill_saving_cycle(custom_user_prompt=custom)
        return res.model_dump(mode="json")

    @app.post("/api/v1/bot/prompt")
    async def bot_natural_prompt(body: dict[str, Any]) -> dict[str, Any]:
        try:
            return await svc.bot.execute_natural_prompt(str(body.get("prompt", "")))
        except PolicyViolationError as exc:
            raise HTTPException(
                status_code=403, detail={"message": str(exc), "violations": exc.violations}
            ) from exc

    @app.post("/api/v1/bot/launch/vm", status_code=201)
    async def bot_launch_vm(req: VmProvisionRequest) -> dict[str, Any]:
        try:
            dec, res = await svc.bot.launch_vm_guardrailed(req)
            return {
                "guardrail": dec.model_dump(mode="json"),
                "provision": res.model_dump(mode="json") if res else None,
            }
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PolicyViolationError as exc:
            raise HTTPException(
                status_code=403, detail={"message": str(exc), "violations": exc.violations}
            ) from exc

    @app.post("/api/v1/bot/launch/k8s", status_code=201)
    async def bot_launch_k8s(req: K8sLaunchRequest) -> dict[str, Any]:
        try:
            dec, res = await svc.bot.launch_k8s_guardrailed(req)
            return {
                "guardrail": dec.model_dump(mode="json"),
                "k8s": res.model_dump(mode="json") if res else None,
            }
        except PolicyViolationError as exc:
            raise HTTPException(
                status_code=403, detail={"message": str(exc), "violations": exc.violations}
            ) from exc

    @app.get("/api/v1/bot/docker")
    async def bot_list_docker() -> list[dict[str, Any]]:
        return [c.model_dump(mode="json") for c in svc.bot.docker.list_containers()]

    @app.post("/api/v1/bot/launch/docker", status_code=201)
    async def bot_launch_docker(req: DockerLaunchRequest) -> dict[str, Any]:
        try:
            dec, ctr = await svc.bot.launch_docker_guardrailed(req)
            return {
                "guardrail": dec.model_dump(mode="json"),
                "container": ctr.model_dump(mode="json") if ctr else None,
            }
        except PolicyViolationError as exc:
            raise HTTPException(
                status_code=403, detail={"message": str(exc), "violations": exc.violations}
            ) from exc

    @app.post("/api/v1/bot/docker/{container_id}/stop")
    async def bot_stop_docker(container_id: str) -> dict[str, Any]:
        try:
            return await svc.bot.docker.stop_container(container_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # =========================================================================
    # Syncro Suite & Dual-Mode Syncro Deployer (Flutter Desktop Agent Backend)
    # =========================================================================
    @app.get("/api/v1/syncro/suite")
    async def syncro_suite() -> dict[str, Any]:
        return {
            "suite_reference": "https://project-syncroo.netlify.app",
            "active_mode": svc.syncro.active_mode.value,
            "modules": [m.model_dump(mode="json") for m in svc.syncro.suite_modules()],
        }

    @app.get("/api/v1/syncro/resilience/health")
    async def syncro_resilience_health() -> dict[str, Any]:
        return svc.syncro.resilience_health()

    @app.post("/api/v1/syncro/mode")
    async def syncro_set_mode(body: dict[str, str]) -> dict[str, Any]:
        try:
            mode = SyncroMode(body.get("mode", "agentic").lower())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="mode must be 'agentic' or 'manual'") from exc
        return await svc.syncro.set_mode(mode)

    @app.get("/api/v1/syncro/deployments")
    async def syncro_list_deployments(limit: int = 50) -> list[dict[str, Any]]:
        return [d.model_dump(mode="json") for d in svc.syncro.list_deployments(limit)]

    @app.post("/api/v1/syncro/deploy", status_code=201)
    async def syncro_deploy(req: SyncroDeployRequest) -> dict[str, Any]:
        try:
            dep = await svc.syncro.deploy(req)
            return dep.model_dump(mode="json")
        except PolicyViolationError as exc:
            raise HTTPException(
                status_code=403, detail={"message": str(exc), "violations": exc.violations}
            ) from exc
        except LockAcquisitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/syncro/deployments/{deployment_id}/promote")
    async def syncro_promote(deployment_id: str, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            actor = (body or {}).get("actor", "syncro-desktop")
            return (await svc.syncro.promote(deployment_id, actor=actor)).model_dump(mode="json")
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/syncro/deployments/{deployment_id}/rollback")
    async def syncro_rollback(deployment_id: str, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            reason = (body or {}).get("reason", "Manual rollback from Syncro Desktop")
            actor = (body or {}).get("actor", "syncro-desktop")
            return (await svc.syncro.rollback(deployment_id, reason=reason, actor=actor)).model_dump(mode="json")
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/syncro/agents")
    async def syncro_list_agents() -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in svc.syncro.list_agents()]

    @app.post("/api/v1/syncro/agents/register", status_code=201)
    async def syncro_register_agent(reg: DesktopAgentRegistration) -> dict[str, Any]:
        return svc.syncro.register_agent(reg).model_dump(mode="json")

    @app.post("/api/v1/syncro/agents/{agent_id}/heartbeat")
    async def syncro_agent_heartbeat(agent_id: str, hb: DesktopAgentHeartbeat) -> dict[str, Any]:
        return svc.syncro.heartbeat_agent(agent_id, hb).model_dump(mode="json")

    # =========================================================================
    # Polyglot Extension Hub, Tri-Broker Telemetry, MCP & Metrics
    # =========================================================================
    @app.get("/api/v1/extensions")
    async def list_extensions() -> list[dict[str, Any]]:
        return [ext.model_dump(mode="json") for ext in svc.extensions.list_extensions()]

    @app.post("/api/v1/extensions", status_code=201)
    async def register_extension(plugin: ExtensionPlugin) -> dict[str, Any]:
        saved = await svc.extensions.register(plugin)
        return saved.model_dump(mode="json")

    @app.post("/api/v1/extensions/{extension_id}/hooks")
    async def invoke_extension(extension_id: str, body: ExtensionHookBody) -> dict[str, Any]:
        try:
            return await svc.extensions.invoke_hook(extension_id, body.hook_name, body.payload)
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/brokers/health")
    async def brokers_health() -> dict[str, Any]:
        return await svc.broker_health()

    @app.get("/api/v1/brokers/kafka/events")
    async def kafka_events(topic: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        events = await svc.kafka.list_events(topic=topic, limit=limit)
        return [evt.model_dump(mode="json") for evt in events]

    @app.get("/api/v1/brokers/rabbitmq/jobs")
    async def rabbitmq_jobs(queue: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        jobs = await svc.rabbitmq.list_jobs(queue=queue, limit=limit)
        return [j.model_dump(mode="json") for j in jobs]

    # =========================================================================
    # Multi-Cloud CLI Wrappers (Azure `az`, GCP `gcloud`, AWS `aws`)
    # =========================================================================
    @app.get("/api/v1/cli/status")
    async def cli_toolchain_status() -> dict[str, Any]:
        return await svc.cloud_cli.toolchain_status()

    @app.get("/api/v1/cli/presets")
    async def cli_presets(provider: CliProvider | None = None) -> list[dict[str, Any]]:
        presets = svc.cloud_cli.list_presets()
        if provider is not None:
            presets = [p for p in presets if p.provider == provider]
        return [p.model_dump(mode="json") for p in presets]

    @app.get("/api/v1/cli/history")
    async def cli_history(provider: CliProvider | None = None, limit: int = 40) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in svc.cloud_cli.history(provider=provider, limit=limit)]

    @app.post("/api/v1/cli/exec")
    async def cli_exec(req: CliExecutionRequest) -> dict[str, Any]:
        result = await svc.cloud_cli.execute(req)
        return result.model_dump(mode="json")

    @app.post("/api/v1/cli/az")
    async def cli_exec_az(body: CloudCliProviderBody) -> dict[str, Any]:
        result = await svc.cloud_cli.execute(
            CliExecutionRequest(provider=CliProvider.AZ, **body.model_dump())
        )
        return result.model_dump(mode="json")

    @app.post("/api/v1/cli/gcp")
    async def cli_exec_gcp(body: CloudCliProviderBody) -> dict[str, Any]:
        result = await svc.cloud_cli.execute(
            CliExecutionRequest(provider=CliProvider.GCLOUD, **body.model_dump())
        )
        return result.model_dump(mode="json")

    @app.post("/api/v1/cli/aws")
    async def cli_exec_aws(body: CloudCliProviderBody) -> dict[str, Any]:
        result = await svc.cloud_cli.execute(
            CliExecutionRequest(provider=CliProvider.AWS, **body.model_dump())
        )
        return result.model_dump(mode="json")

    # =========================================================================
    # IaC Terraform Studio, DevSecOps Graph & Script Writers (Ansible/Helm/CICD)
    # =========================================================================
    @app.get("/api/v1/iac/workspaces")
    async def iac_list_workspaces() -> list[dict[str, Any]]:
        return [w.model_dump(mode="json") for w in svc.iac_studio.list_workspaces()]

    @app.post("/api/v1/iac/terraform/generate", status_code=201)
    async def iac_terraform_generate(req: TerraformGenerateRequest) -> dict[str, Any]:
        bundle = svc.iac_studio.generate(req)
        await svc.redis.publish_channel(
            "aegis:live",
            {
                "type": "iac.terraform.generated",
                "workspace_id": bundle.workspace_id,
                "cloud": bundle.cloud.value,
                "resources": len(bundle.resources),
            },
        )
        return bundle.model_dump(mode="json")

    @app.post("/api/v1/iac/terraform/build")
    async def iac_terraform_build(body: TerraformBuildBody) -> dict[str, Any]:
        res = await svc.iac_studio.build(
            workspace_id=body.workspace_id,
            workspace_dir=body.workspace_dir,
        )
        await svc.redis.publish_channel(
            "aegis:live",
            {
                "type": "iac.terraform.built",
                "workspace_id": res.workspace_id,
                "validate_ok": res.validate_ok,
                "resources": len(res.resources_discovered),
            },
        )
        return res.model_dump(mode="json")

    @app.post("/api/v1/iac/terraform/run")
    async def iac_terraform_run(req: TerraformRunRequest) -> dict[str, Any]:
        try:
            res = await svc.iac_studio.run(req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await svc.redis.publish_channel(
            "aegis:live",
            {
                "type": "iac.terraform.run",
                "workspace_id": res.workspace_id,
                "action": res.action,
                "status": res.status,
            },
        )
        return res.model_dump(mode="json")

    @app.post("/api/v1/iac/graph/devsecops")
    async def iac_devsecops_graph(body: DevSecOpsGraphBody) -> dict[str, Any]:
        graph = svc.iac_studio.build_graph(
            workspace_id=body.workspace_id,
            workspace_dir=body.workspace_dir,
            include_pipeline=body.include_pipeline,
        )
        return graph.model_dump(mode="json")

    @app.get("/api/v1/scripts/bundles")
    async def scripts_list_bundles() -> list[dict[str, Any]]:
        return [b.model_dump(mode="json") for b in svc.script_writers.list_bundles()]

    @app.post("/api/v1/scripts/ansible/generate", status_code=201)
    async def scripts_generate_ansible(req: AnsibleGenerateRequest) -> dict[str, Any]:
        bundle = svc.script_writers.generate_ansible(req)
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "scripts.ansible.generated", "bundle_id": bundle.bundle_id, "name": bundle.name},
        )
        return bundle.model_dump(mode="json")

    @app.post("/api/v1/scripts/helm/generate", status_code=201)
    async def scripts_generate_helm(req: HelmGenerateRequest) -> dict[str, Any]:
        bundle = svc.script_writers.generate_helm(req)
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "scripts.helm.generated", "bundle_id": bundle.bundle_id, "name": bundle.name},
        )
        return bundle.model_dump(mode="json")

    @app.post("/api/v1/scripts/cicd/generate", status_code=201)
    async def scripts_generate_cicd(req: CicdGenerateRequest) -> dict[str, Any]:
        bundle = svc.script_writers.generate_cicd(req)
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "scripts.cicd.generated", "bundle_id": bundle.bundle_id, "kind": bundle.kind},
        )
        return bundle.model_dump(mode="json")

    @app.post("/api/v1/scripts/container/generate", status_code=201)
    async def scripts_generate_container(req: ContainerGenerateRequest) -> dict[str, Any]:
        bundle = svc.script_writers.generate_container(req)
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "scripts.container.generated", "bundle_id": bundle.bundle_id, "name": bundle.name},
        )
        return bundle.model_dump(mode="json")

    # =========================================================================
    # Security Assessment MCP (Trivy · Bandit · Multi-Lang SAST · DAST · Full)
    # =========================================================================
    @app.get("/api/v1/security/mcp/status")
    async def security_mcp_status() -> dict[str, Any]:
        return svc.security_mcp.toolchain_status()

    @app.get("/api/v1/security/assessments")
    async def security_list_assessments() -> list[dict[str, Any]]:
        return [r.model_dump(mode="json") for r in svc.security_mcp.history[:20]]

    @app.post("/api/v1/security/assess/trivy")
    async def security_assess_trivy(body: SecurityPathAssessBody) -> dict[str, Any]:
        tpath = Path(body.target_path) if body.target_path else svc.settings.repo_root
        rep = await svc.security_mcp.run_trivy(target_path=tpath, project_id=body.project_id)
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "security.trivy.completed", "assessment_id": rep.assessment_id, "grade": rep.grade},
        )
        return rep.model_dump(mode="json")

    @app.post("/api/v1/security/assess/bandit")
    async def security_assess_bandit(body: SecurityPathAssessBody) -> dict[str, Any]:
        tpath = Path(body.target_path) if body.target_path else svc.settings.repo_root
        rep = await svc.security_mcp.run_bandit(target_path=tpath, project_id=body.project_id)
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "security.bandit.completed", "assessment_id": rep.assessment_id, "grade": rep.grade},
        )
        return rep.model_dump(mode="json")

    @app.post("/api/v1/security/assess/sast")
    async def security_assess_sast(body: SecurityPathAssessBody) -> dict[str, Any]:
        tpath = Path(body.target_path) if body.target_path else svc.settings.repo_root
        rep = await svc.security_mcp.run_sast(target_path=tpath, project_id=body.project_id)
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "security.sast.completed", "assessment_id": rep.assessment_id, "grade": rep.grade},
        )
        return rep.model_dump(mode="json")

    @app.post("/api/v1/security/assess/dast")
    async def security_assess_dast(body: SecurityDastBody) -> dict[str, Any]:
        try:
            rep = await svc.security_mcp.run_dast(
                target_url=body.target_url,
                project_id=body.project_id,
                live_probe=body.live_probe,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await svc.redis.publish_channel(
            "aegis:live",
            {"type": "security.dast.completed", "assessment_id": rep.assessment_id, "grade": rep.grade},
        )
        return rep.model_dump(mode="json")

    @app.post("/api/v1/security/assess/full")
    async def security_assess_full(body: SecurityFullAssessBody) -> dict[str, Any]:
        tpath = Path(body.target_path) if body.target_path else svc.settings.repo_root
        rep = await svc.security_mcp.run_full_assessment(
            project_id=body.project_id,
            target_path=tpath,
            target_url=body.target_url,
            include_dast=body.include_dast,
            include_graph=body.include_graph,
            live_dast_probe=body.live_dast_probe,
        )
        await svc.redis.publish_channel(
            "aegis:live",
            {
                "type": "security.full.completed",
                "assessment_id": rep.assessment_id,
                "grade": rep.grade,
                "score": rep.compliance_score,
            },
        )
        return rep.model_dump(mode="json")

    @app.post("/mcp")
    async def mcp_http_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return await mcp_server.handle_jsonrpc(payload)

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus_metrics() -> str:
        kafka_h = await svc.kafka.health()
        rmq_h = await svc.rabbitmq.health()
        redis_h = await svc.redis.health()
        finops = svc.finops_summary()
        cli_count = len(svc.cloud_cli.history(limit=200))
        return "\n".join(
            [
                "# HELP aegisops_projects_total Registered projects in control plane",
                "# TYPE aegisops_projects_total gauge",
                f"aegisops_projects_total {len(svc.projects)}",
                "# HELP aegisops_multicloud_hourly_burn_usd Hourly spend across AWS, GCP, Azure",
                "# TYPE aegisops_multicloud_hourly_burn_usd gauge",
                f"aegisops_multicloud_hourly_burn_usd {finops.total_hourly_usd}",
                "# HELP aegisops_kafka_events_published_total Published Kafka CloudEvents",
                "# TYPE aegisops_kafka_events_published_total counter",
                f"aegisops_kafka_events_published_total {kafka_h['total_published']}",
                "# HELP aegisops_rabbitmq_jobs_total Total jobs dispatched via RabbitMQ",
                "# TYPE aegisops_rabbitmq_jobs_total counter",
                f"aegisops_rabbitmq_jobs_total {rmq_h['total_jobs']}",
                "# HELP aegisops_redis_pubsub_total Redis Pub/Sub events fanned out",
                "# TYPE aegisops_redis_pubsub_total counter",
                f"aegisops_redis_pubsub_total {redis_h['pubsub_messages_published']}",
                "# HELP aegisops_cloud_cli_executions_total Guardrailed az/gcloud/aws CLI executions",
                "# TYPE aegisops_cloud_cli_executions_total counter",
                f"aegisops_cloud_cli_executions_total {cli_count}",
                "",
            ]
        )

    @app.websocket("/ws/events")
    async def websocket_live_events(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_json({"type": "connected", "channel": "aegis:live"})
        try:
            async for message in svc.redis.subscribe_channel("aegis:live"):
                await ws.send_json(message)
        except (WebSocketDisconnect, asyncio.CancelledError):
            return

    dashboard_dist = svc.settings.repo_root / "apps" / "dashboard" / "dist"
    if dashboard_dist.exists():
        app.mount("/", StaticFiles(directory=str(dashboard_dist), html=True), name="dashboard")

    return app
