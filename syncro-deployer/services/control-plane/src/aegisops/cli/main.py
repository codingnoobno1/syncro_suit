"""AegisOps Production Multi-Cloud DevSecOps CLI (`aegis`) powered by Typer + Rich."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aegisops import __version__
from aegisops.adapters.docker.docker_launcher import DockerLaunchRequest
from aegisops.application.container import build_platform
from aegisops.bot.models import BotAutonomyMode
from aegisops.domain.models import (
    CloudProvider,
    K8sLaunchRequest,
    Project,
    VmArchitecture,
    VmProvisionRequest,
    VmSelectionCriteria,
    WorkloadProfile,
)
from aegisops.mcp.server import AegisMcpServer
from aegisops.syncro.models import (
    DeploymentStrategy,
    DeploymentTargetType,
    SyncroDeployRequest,
    SyncroMode,
)

app = typer.Typer(
    name="syncro",
    help="Syncro Deployer / AegisOps — Multi-Cloud (AWS · GCP · Azure) DevSecOps CLI, Flutter Desktop Agent Backend & MCP Bot.",
    no_args_is_help=True,
)
syncro_app = typer.Typer(help="Syncro Suite & Dual-Mode Deployer (Agentic Mode vs Manual DevOps Mode).")
project_app = typer.Typer(help="Manage multi-project polyglot registrations.")
vm_app = typer.Typer(help="Intelligent Multi-Cloud VM Selector, Comparator & Ephemeral Provisioner.")
bot_app = typer.Typer(help="Guardrailed MCP Ops Bot (Launch VMs/K8s/Docker, Read Bills & Statuses, Self-Prompt).")
cloud_app = typer.Typer(help="Inspect AWS, GCP, Azure status, FinOps spend & Drift checks.")
infra_app = typer.Typer(help="Terraform & Ansible multi-cloud infrastructure operations.")
k8s_app = typer.Typer(help="Launch and inspect OPA-hardened Kubernetes workloads (EKS/GKE/AKS).")
destroy_app = typer.Typer(help="Quick Destruction blast-radius preview & kill-switch.")
rbac_app = typer.Typer(help="Multi-Cloud IAM & PowerShell ABAC least-privilege planner.")
mcp_app = typer.Typer(help="Run and inspect the Model Context Protocol (MCP) server.")
broker_app = typer.Typer(help="Inspect Kafka, RabbitMQ, and Redis telemetry.")

app.add_typer(syncro_app, name="syncro")
app.add_typer(project_app, name="project")
app.add_typer(vm_app, name="vm")
app.add_typer(bot_app, name="bot")
app.add_typer(cloud_app, name="cloud")
app.add_typer(infra_app, name="infra")
app.add_typer(k8s_app, name="k8s")
app.add_typer(destroy_app, name="destroy")
app.add_typer(rbac_app, name="rbac")
app.add_typer(mcp_app, name="mcp")
app.add_typer(broker_app, name="broker")

console = Console()


@app.command("version")
def version_cmd() -> None:
    """Print AegisOps version."""
    console.print(f"aegisops v{__version__} (AWS · GCP · Azure)")


@app.command("server")
def server_cmd(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8080, help="Bind port"),
) -> None:
    """Start the FastAPI Control Plane, WebSocket event stream, Dashboard, and HTTP MCP host."""
    uvicorn.run("aegisops.api.app:create_app", factory=True, host=host, port=port)


@vm_app.command("compare")
def vm_compare_cmd(
    min_vcpu: int = typer.Option(4, "--vcpu"),
    min_memory: float = typer.Option(16.0, "--ram"),
    profile: Annotated[str | None, typer.Option("--profile", help="general-purpose|compute-optimized|memory-optimized|confidential-sec|gpu-ai")] = None,
    arch: Annotated[str | None, typer.Option("--arch", help="x86_64|arm64")] = None,
    confidential: bool = typer.Option(False, "--confidential"),
    spot: bool = typer.Option(False, "--spot"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compare optimal VMs side-by-side across AWS EC2, GCP GCE, and Azure VMs."""
    platform = build_platform()
    criteria = VmSelectionCriteria(
        min_vcpu=min_vcpu,
        min_memory_gib=min_memory,
        workload_profile=WorkloadProfile(profile) if profile else None,
        architecture=VmArchitecture(arch) if arch else None,
        require_confidential_compute=confidential,
        prefer_spot=spot,
    )
    matrix = platform.vm_selector.compare_clouds(criteria)
    if json_output:
        console.print_json(matrix.model_dump_json())
        return
    table = Table(title="Multi-Cloud VM Comparison (AWS · GCP · Azure)")
    table.add_column("Cloud", style="cyan")
    table.add_column("SKU", style="bold")
    table.add_column("Specs")
    table.add_column("Confidential Tech")
    table.add_column("Est $/mo", style="green")
    table.add_column("Fit Score")
    for cloud_name, rec in matrix.best_by_cloud.items():
        if rec is None:
            table.add_row(cloud_name.upper(), "No match", "-", "-", "-", "-")
        else:
            table.add_row(
                cloud_name.upper(),
                rec.sku.sku,
                f"{rec.sku.vcpu} vCPU / {int(rec.sku.memory_gib)} GiB ({rec.sku.architecture.value})",
                rec.sku.security.confidential_tech or "Trusted/Shielded",
                f"${rec.effective_monthly_usd:.2f}",
                f"{rec.fit_score}/100",
            )
    console.print(table)


@vm_app.command("provision")
def vm_provision_cmd(
    cloud: str = typer.Option("gcp", "--cloud", help="aws | gcp | azure"),
    sku: str = typer.Option("n2d-standard-4", "--sku"),
    region: str = typer.Option("us-central1", "--region"),
    project_id: str = typer.Option("ai-inference", "--project"),
    name: str = typer.Option("ephemeral-vm-cli", "--name"),
    spot: bool = typer.Option(False, "--spot"),
    ttl_hours: int = typer.Option(4, "--ttl-hours"),
) -> None:
    """Provision a CIS-hardened ephemeral VM on AWS, GCP, or Azure."""
    platform = build_platform()
    req = VmProvisionRequest(
        project_id=project_id,
        environment_name=name,
        cloud=CloudProvider(cloud.lower()),
        sku=sku,
        region=region,
        use_spot=spot,
        ttl_hours=ttl_hours,
    )
    res = asyncio.run(platform.vm_selector.provision_ephemeral_vm(req))
    console.print_json(res.model_dump_json())


@syncro_app.command("suite")
def syncro_suite_cmd() -> None:
    """Display all 7 Syncro Suite modules and resilience health."""
    platform = build_platform()
    table = Table(title="Syncro Suite Unified Topology (project-syncroo.netlify.app)")
    table.add_column("Module", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Transport")
    table.add_column("Role")
    for mod in platform.syncro.suite_modules():
        table.add_row(mod.name, mod.status.upper(), mod.transport, mod.role)
    console.print(table)


@syncro_app.command("deploy")
def syncro_deploy_cmd(
    mode: str = typer.Option("agentic", "--mode", help="agentic | manual"),
    cloud: str = typer.Option("gcp", "--cloud", help="aws | gcp | azure"),
    target: str = typer.Option("kubernetes", "--target", help="vm | kubernetes | docker"),
    strategy: str = typer.Option("canary", "--strategy", help="canary | blue-green | rolling"),
    name: str = typer.Option("syncro-cli-release", "--name"),
    idempotency_key: Annotated[str | None, typer.Option("--key")] = None,
    simulate_fault: bool = typer.Option(False, "--simulate-fault"),
) -> None:
    """Run an idempotent Syncro deployment in Agentic Mode or Manual DevOps Mode."""
    platform = build_platform()
    dep = asyncio.run(
        platform.syncro.deploy(
            SyncroDeployRequest(
                environment_name=name,
                cloud=CloudProvider(cloud.lower()),
                target_type=DeploymentTargetType(target.lower()),
                strategy=DeploymentStrategy(strategy.lower()),
                mode=SyncroMode(mode.lower()),
                idempotency_key=idempotency_key,
                simulate_canary_fault=simulate_fault,
            )
        )
    )
    console.print_json(dep.model_dump_json())


@syncro_app.command("health")
def syncro_health_cmd() -> None:
    """Show SQLite WAL journal, Circuit Breakers, and Desktop Agent health."""
    platform = build_platform()
    console.print_json(json.dumps(platform.syncro.resilience_health()))


@bot_app.command("status")
def bot_status_cmd() -> None:
    """Read unified live status across AWS/GCP/Azure VMs, K8s, Docker, Brokers, and Billing."""
    platform = build_platform()
    console.print_json(asyncio.run(platform.bot.read_all_statuses()).model_dump_json())


@bot_app.command("bill")
def bot_bill_cmd() -> None:
    """Read live itemized multi-cloud bill and directive-aligned savings opportunities."""
    platform = build_platform()
    console.print_json(platform.bot.read_live_bill().model_dump_json())


@bot_app.command("generate-prompts")
def bot_generate_prompts_cmd(
    custom: Annotated[str | None, typer.Option("--custom", help="Extra cost/traffic directive")] = None,
) -> None:
    """Generate strict Guardrail System Prompt, Bill-Saving Self-Prompt, and Traffic Blueprints."""
    platform = build_platform()
    bundle = platform.bot.generate_prompts(custom_user_prompt=custom)
    console.print(Panel(bundle.guardrail_system_prompt, title="Guardrail System Prompt", border_style="cyan"))
    console.print(Panel(bundle.billing_self_prompt, title="Bill-Saving Self-Prompt", border_style="green"))


@bot_app.command("self-prompt")
def bot_self_prompt_cmd(
    autonomy: str = typer.Option("recommend_and_confirm", "--autonomy", help="observe_only|recommend_and_confirm|bounded_autonomous"),
    custom: Annotated[str | None, typer.Option("--custom")] = None,
) -> None:
    """Run an Auto-Bot bill-saving self-prompt optimization cycle under strict guardrails."""
    platform = build_platform()
    cfg = platform.bot.guardrail_engine.settings.model_copy(
        update={"autonomy_mode": BotAutonomyMode(autonomy)}
    )
    platform.bot.update_guardrails(cfg)
    res = asyncio.run(platform.bot.run_self_prompt_bill_saving_cycle(custom_user_prompt=custom))
    console.print_json(res.model_dump_json())


@bot_app.command("docker-launch")
def bot_docker_launch_cmd(
    name: str = typer.Option("bot-nginx", "--name"),
    image: str = typer.Option("nginxinc/nginx-unprivileged:1.27-alpine", "--image"),
    privileged: bool = typer.Option(False, "--privileged"),
) -> None:
    """Launch a Docker container gated by strict MCP Bot Guardrails."""
    platform = build_platform()
    dec, ctr = asyncio.run(
        platform.bot.launch_docker_guardrailed(
            DockerLaunchRequest(name=name, image=image, privileged=privileged)
        )
    )
    console.print_json(
        json.dumps(
            {"guardrail": dec.model_dump(mode="json"), "container": ctr.model_dump(mode="json") if ctr else None}
        )
    )


@bot_app.command("prompt")
def bot_prompt_cmd(prompt_text: str = typer.Argument(..., help="Natural-language instruction for the Guardrailed MCP Bot")) -> None:
    """Execute a natural-language instruction through the Prompt-Injection Firewall & Guardrail Engine."""
    platform = build_platform()
    res = asyncio.run(platform.bot.execute_natural_prompt(prompt_text))
    console.print_json(json.dumps(res))


@cloud_app.command("finops")
def cloud_finops_cmd() -> None:
    """Display FinOps hourly/monthly burn and reclaimable ephemeral savings across AWS, GCP, and Azure."""
    platform = build_platform()
    console.print_json(platform.finops_summary().model_dump_json())


@cloud_app.command("drift")
def cloud_drift_cmd(env_id: str = typer.Option("env-aws-edge-501", "--env")) -> None:
    """Run Go Concurrent Drift Scanner against an AWS, GCP, or Azure environment."""
    platform = build_platform()
    console.print_json(asyncio.run(platform.run_drift_check(env_id)).model_dump_json())


@project_app.command("list")
def project_list(json_output: bool = typer.Option(False, "--json", help="Emit raw JSON")) -> None:
    """List registered projects and polyglot extensions."""
    platform = build_platform()
    if json_output:
        console.print_json(
            json.dumps([p.model_dump(mode="json") for p in platform.projects.values()])
        )
        return
    table = Table(title="AegisOps Multi-Cloud Project Registry")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Language", style="green")
    table.add_column("Target Clouds")
    table.add_column("Owner Team")
    for proj in platform.projects.values():
        clouds_str = ", ".join(c.value.upper() for c in proj.target_clouds)
        table.add_row(proj.id, proj.name, proj.primary_language, clouds_str, proj.owner_team)
    console.print(table)


@project_app.command("register")
def project_register(
    project_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(..., "--name"),
    repository: str = typer.Option(..., "--repo"),
    language: str = typer.Option("go", "--lang"),
    owner_team: str = typer.Option("platform-sec", "--owner"),
    clouds: str = typer.Option("aws,gcp,azure", "--clouds"),
) -> None:
    """Register a Go, TypeScript, Java, or Python repository into AegisOps."""
    platform = build_platform()
    proj = Project(
        id=project_id,
        name=name,
        repository=repository,
        primary_language=language,
        owner_team=owner_team,
        target_clouds=[CloudProvider(c.strip().lower()) for c in clouds.split(",") if c.strip()],
        azure_subscription_id=platform.settings.azure_subscription_id,
    )
    saved = asyncio.run(platform.register_project(proj))
    console.print_json(saved.model_dump_json())


@app.command("scan")
def scan_cmd(
    project_id: str = typer.Option("payments-core", "--project"),
    target: Annotated[str | None, typer.Option("--target", help="Directory or file to scan")] = None,
    scanners: str = typer.Option("checkov,trivy,bandit,tfsec,opa", "--scanners"),
    sarif: bool = typer.Option(False, "--sarif", help="Output SARIF 2.1.0 JSON"),
) -> None:
    """Run Checkov, Trivy, Bandit, tfsec, and OPA/Rego policy gates across AWS/GCP/Azure IaC."""
    platform = build_platform()
    scanner_list = [s.strip() for s in scanners.split(",") if s.strip()]
    report = asyncio.run(
        platform.run_security_scan(
            project_id=project_id, target_path=target, scanners=scanner_list
        )
    )
    if sarif:
        console.print_json(json.dumps(platform.export_scan_sarif(report.id)))
        return

    status_color = "green" if report.opa_gate.allowed else "red"
    console.print(
        Panel(
            f"Scan ID: {report.id}\n"
            f"Compliance Score: {report.compliance_score}%\n"
            f"OPA Policy Gate: [{'ALLOWED' if report.opa_gate.allowed else 'DENIED'}]\n"
            f"Summary: {report.summary}",
            title=f"Multi-Cloud DevSecOps Scan — {project_id}",
            border_style=status_color,
        )
    )
    if not report.opa_gate.allowed:
        raise typer.Exit(code=2)


@infra_app.command("tf-plan")
def tf_plan_cmd(
    project_id: str = typer.Option("payments-core", "--project"),
    env_id: str = typer.Option("env-pr-412", "--env"),
    cloud: str = typer.Option("azure", "--cloud", help="aws | gcp | azure"),
    ttl_hours: int = typer.Option(4, "--ttl-hours"),
) -> None:
    """Run an AWS, GCP, or Azure Terraform plan with ephemeral TTL tags."""
    platform = build_platform()
    res = asyncio.run(
        platform.plan_terraform(
            project_id=project_id,
            environment_id=env_id,
            ttl_hours=ttl_hours,
            cloud=CloudProvider(cloud.lower()),
        )
    )
    console.print_json(json.dumps(res))


@infra_app.command("ansible-harden")
def ansible_harden_cmd(
    project_id: str = typer.Option("payments-core", "--project"),
    playbook: str = typer.Option("cis_azure_linux.yml", "--playbook"),
    check_mode: bool = typer.Option(False, "--check"),
) -> None:
    """Run CIS Linux hardening or quarantine Ansible playbook."""
    platform = build_platform()
    res = asyncio.run(
        platform.run_ansible_hardening(project_id=project_id, playbook=playbook, check_mode=check_mode)
    )
    console.print_json(json.dumps(res))


@k8s_app.command("launch")
def k8s_launch_cmd(
    project_id: str = typer.Option("edge-gateway", "--project"),
    env_id: str = typer.Option("env-staging-edge", "--env"),
    cloud: str = typer.Option("azure", "--cloud", help="aws | gcp | azure"),
    name: str = typer.Option("edge-gateway", "--name"),
    image: str = typer.Option("acraegis.azurecr.io/edge-gateway:1.4.2", "--image"),
    namespace: str = typer.Option("aegisops", "--namespace"),
    mode: str = typer.Option("kustomize", "--mode", help="kustomize | helm | ephemeral-job"),
) -> None:
    """Launch an OPA-verified hardened Kubernetes Deployment or ephemeral Job."""
    platform = build_platform()
    req = K8sLaunchRequest(
        project_id=project_id,
        environment_id=env_id,
        cloud=CloudProvider(cloud.lower()),
        namespace=namespace,
        workload_name=name,
        image=image,
        mode=mode,
    )
    res = asyncio.run(platform.launch_kubernetes_workload(req))
    console.print_json(res.model_dump_json())
    if not res.opa_gate.allowed:
        raise typer.Exit(code=2)


@destroy_app.command("preview")
def destroy_preview_cmd(env_id: str = typer.Option("env-pr-412", "--env")) -> None:
    """Compute multi-cloud blast-radius dependency graph, cost savings, and mint HMAC destroy token."""
    platform = build_platform()
    preview = asyncio.run(platform.destroyer.preview(env_id))
    console.print_json(preview.model_dump_json())


@destroy_app.command("execute")
def destroy_execute_cmd(
    env_id: str = typer.Option(..., "--env"),
    confirm: str = typer.Option(..., "--confirm", help="HMAC confirmation token from preview"),
    kill_switch: bool = typer.Option(False, "--kill-switch"),
) -> None:
    """Execute Quick Destruction or emergency kill-switch."""
    platform = build_platform()
    preview = asyncio.run(platform.destroyer.preview(env_id))
    if not preview.opa_gate.allowed:
        console.print(f"[red]OPA Denied:[/red] {preview.opa_gate.violations}")
        raise typer.Exit(code=2)
    res = asyncio.run(
        platform.destroyer.execute(
            environment_id=env_id,
            confirmation_token=confirm,
            kill_switch=kill_switch,
            actor="aegis-cli",
        )
    )
    console.print_json(res.model_dump_json())


@rbac_app.command("plan")
def rbac_plan_cmd(
    cloud: str = typer.Option("azure", "--cloud", help="aws | gcp | azure"),
    resource_group: str = typer.Option("rg-aegis-payments-pr-412", "--rg"),
    principal: str = typer.Option("7b8f12c0-4a91-4d30-9f1a-000000000101", "--principal"),
    personas: str = typer.Option("auditor,deployer,destroyer", "--personas"),
    pim_hours: int = typer.Option(1, "--pim-hours"),
) -> None:
    """Generate an OPA-verified AWS IAM, GCP CEL, or Azure PowerShell RBAC & ABAC permissions plan."""
    platform = build_platform()
    plan = asyncio.run(
        platform.generate_powershell_rbac_plan(
            resource_group=resource_group,
            principal_object_id=principal,
            personas=[p.strip() for p in personas.split(",") if p.strip()],
            pim_max_duration_hours=pim_hours,
            cloud=CloudProvider(cloud.lower()),
        )
    )
    console.print_json(plan.model_dump_json())


@mcp_app.command("serve")
def mcp_serve_cmd(
    transport: str = typer.Option("stdio", "--transport", help="stdio | http"),
    port: int = typer.Option(8090, "--port"),
) -> None:
    """Host the AegisOps MCP Server over stdio (IDE/Claude) or HTTP."""
    platform = build_platform()
    if transport == "stdio":
        server = AegisMcpServer(platform)
        asyncio.run(server.serve_stdio())
    else:
        uvicorn.run("aegisops.api.app:create_app", factory=True, host="127.0.0.1", port=port)


@mcp_app.command("tools")
def mcp_tools_cmd() -> None:
    """List all MCP tools, resources, and prompts exposed by AegisOps."""
    server = AegisMcpServer(build_platform())
    console.print_json(
        json.dumps(
            {
                "tools": [t["name"] for t in server.list_tools()],
                "resources": [r["uri"] for r in server.list_resources()],
                "prompts": [p["name"] for p in server.list_prompts()],
            }
        )
    )


@broker_app.command("health")
def broker_health_cmd() -> None:
    """Display health for Kafka, RabbitMQ, Redis, and AWS/GCP/Azure adapters."""
    platform = build_platform()
    console.print_json(json.dumps(asyncio.run(platform.broker_health())))
