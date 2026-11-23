"""AegisOps Production Multi-Cloud DevSecOps CLI (`aegis`) powered by Typer + Rich."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from aegisops import __version__
from aegisops.adapters.cloud.cli_wrapper import CliExecutionRequest, CliProvider
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
from aegisops.iac.models import (
    AnsibleGenerateRequest,
    CicdGenerateRequest,
    ContainerGenerateRequest,
    HelmGenerateRequest,
    IacBlueprintKind,
    TerraformGenerateRequest,
    TerraformRunRequest,
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
    help="Syncro Deployer / AegisOps — Multi-Cloud (AWS · GCP · Azure) DevSecOps CLI, Electron/Flutter Desktop Backend & MCP Bot.",
    no_args_is_help=True,
)
syncro_app = typer.Typer(help="Syncro Suite & Dual-Mode Deployer (Agentic Mode vs Manual DevOps Mode).")
project_app = typer.Typer(help="Manage multi-project polyglot registrations.")
vm_app = typer.Typer(help="Intelligent Multi-Cloud VM Selector, Comparator & Ephemeral Provisioner.")
bot_app = typer.Typer(help="Guardrailed MCP Ops Bot (Launch VMs/K8s/Docker, Read Bills & Statuses, Self-Prompt).")
cloud_app = typer.Typer(help="Inspect AWS, GCP, Azure status, FinOps spend & Drift checks.")
cloud_cli_app = typer.Typer(help="Guardrailed Azure (az), GCP (gcloud), and AWS (aws) CLI Wrapper.")
iac_app = typer.Typer(help="IaC Terraform Studio (generate/build/run/graph) & DevOps Script Writers (Ansible, Helm, CI/CD, Container).")
sec_app = typer.Typer(help="Security Assessment MCP CLI (Trivy, Bandit, Multi-Lang SAST, OWASP DAST, Full DevSecOps Audit).")
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
app.add_typer(cloud_cli_app, name="cloud-cli")
app.add_typer(iac_app, name="iac")
app.add_typer(sec_app, name="sec")
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


@cloud_cli_app.command("status")
def cloud_cli_status() -> None:
    """Inspect Azure (az), GCP (gcloud), and AWS (aws) CLI wrapper status and guardrails."""
    platform = build_platform()
    console.print_json(json.dumps(asyncio.run(platform.cloud_cli.toolchain_status())))


@cloud_cli_app.command("exec")
def cloud_cli_exec(
    provider: Annotated[str, typer.Option("--provider", "-p", help="az, gcloud, or aws")] = "az",
    args: Annotated[str, typer.Option("--args", "-a", help="Space-separated CLI args")] = "account show",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    allow_destructive: Annotated[bool, typer.Option("--allow-destructive")] = False,
) -> None:
    """Execute a guardrailed az, gcloud, or aws command through the Multi-Cloud CLI Wrapper."""
    platform = build_platform()
    req = CliExecutionRequest(
        provider=CliProvider(provider.lower()),
        args=args.split(),
        dry_run=dry_run,
        allow_destructive=allow_destructive,
        actor="syncro-cli",
    )
    res = asyncio.run(platform.cloud_cli.execute(req))
    console.print_json(res.model_dump_json())


# =============================================================================
# IaC Terraform Studio, DevSecOps Graph & Script Writers (`syncro iac ...`)
# =============================================================================
@iac_app.command("tf-generate")
def iac_tf_generate_cmd(
    name: Annotated[str, typer.Option("--name", "-n")] = "syncro-workload",
    cloud: Annotated[str, typer.Option("--cloud", "-c", help="aws | gcp | azure")] = "aws",
    blueprint: Annotated[str, typer.Option("--blueprint", "-b", help="vpc-k8s | hardened-vm | serverless-api | zero-trust-mesh | data-platform")] = "vpc-k8s",
    region: Annotated[str | None, typer.Option("--region", "-r")] = None,
    environment: Annotated[str, typer.Option("--env", "-e")] = "staging",
    output_dir: Annotated[str | None, typer.Option("--out", "-o")] = None,
    write: Annotated[bool, typer.Option("--write/--no-write")] = True,
) -> None:
    """Generate production-hardened multi-file Terraform HCL for AWS, GCP, or Azure."""
    platform = build_platform()
    req = TerraformGenerateRequest(
        project_name=name,
        cloud=CloudProvider(cloud.lower()),
        blueprint=IacBlueprintKind(blueprint.lower()),
        region=region,
        environment=environment,
        write_to_disk=write,
        output_dir=output_dir,
    )
    bundle = platform.iac_studio.generate(req)
    console.print_json(bundle.model_dump_json())


@iac_app.command("tf-build")
def iac_tf_build_cmd(
    workspace_dir: Annotated[str | None, typer.Option("--dir", "-d")] = None,
    workspace_id: Annotated[str | None, typer.Option("--workspace-id", "-w")] = None,
) -> None:
    """Build and validate Terraform HCL (init, fmt check, validate, resource extraction)."""
    platform = build_platform()
    res = asyncio.run(platform.iac_studio.build(workspace_id=workspace_id, workspace_dir=workspace_dir))
    console.print_json(res.model_dump_json())
    if not res.validate_ok:
        raise typer.Exit(code=1)


@iac_app.command("tf-run")
def iac_tf_run_cmd(
    workspace_dir: Annotated[str | None, typer.Option("--dir", "-d")] = None,
    workspace_id: Annotated[str | None, typer.Option("--workspace-id", "-w")] = None,
    action: Annotated[str, typer.Option("--action", "-a", help="plan | apply | destroy")] = "plan",
    dry_run: Annotated[bool, typer.Option("--dry-run/--execute")] = True,
    auto_approve: Annotated[bool, typer.Option("--auto-approve")] = False,
    environment: Annotated[str, typer.Option("--env", "-e")] = "staging",
) -> None:
    """Run guardrailed Terraform plan/apply/destroy and generate its DevSecOps graph."""
    platform = build_platform()
    req = TerraformRunRequest(
        workspace_id=workspace_id,
        workspace_dir=workspace_dir,
        action=action,
        dry_run=dry_run,
        auto_approve=auto_approve,
        environment=environment,
    )
    res = asyncio.run(platform.iac_studio.run(req))
    console.print_json(res.model_dump_json())
    if not res.guardrail_allowed or res.exit_code != 0:
        raise typer.Exit(code=2)


@iac_app.command("graph")
def iac_graph_cmd(
    workspace_dir: Annotated[str | None, typer.Option("--dir", "-d")] = None,
    workspace_id: Annotated[str | None, typer.Option("--workspace-id", "-w")] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help="mermaid | dot | ascii | json")] = "mermaid",
) -> None:
    """Emit a DevSecOps architecture & security dependency graph (Mermaid, DOT, ASCII, JSON)."""
    platform = build_platform()
    target_dir = workspace_dir or str(platform.settings.terraform_dir)
    graph = platform.iac_studio.build_graph(workspace_id=workspace_id, workspace_dir=target_dir)
    f = fmt.lower()
    if f == "mermaid":
        console.print(graph.mermaid)
    elif f == "dot":
        console.print(graph.dot)
    elif f == "ascii":
        console.print(graph.ascii_summary)
    else:
        console.print_json(graph.model_dump_json())


@iac_app.command("ansible")
def iac_ansible_cmd(
    service: Annotated[str, typer.Option("--service", "-s")] = "syncro-edge",
    cloud: Annotated[str, typer.Option("--cloud", "-c")] = "aws",
    profile: Annotated[str, typer.Option("--profile", "-p", help="cis-l1 | cis-l2 | pci-dss | zero-trust")] = "cis-l2",
    output_dir: Annotated[str | None, typer.Option("--out", "-o")] = None,
    write: Annotated[bool, typer.Option("--write/--no-write")] = True,
) -> None:
    """Generate a hardened Ansible CIS/Zero-Trust playbook, role, and inventory bundle."""
    platform = build_platform()
    req = AnsibleGenerateRequest(
        service_name=service,
        cloud=CloudProvider(cloud.lower()),
        hardening_profile=profile,
        write_to_disk=write,
        output_dir=output_dir,
    )
    console.print_json(platform.script_writers.generate_ansible(req).model_dump_json())


@iac_app.command("helm")
def iac_helm_cmd(
    chart: Annotated[str, typer.Option("--chart", "-n")] = "syncro-service",
    image: Annotated[str, typer.Option("--image", "-i")] = "ghcr.io/syncrosuite/syncro-api:1.0.0",
    port: Annotated[int, typer.Option("--port")] = 8080,
    replicas: Annotated[int, typer.Option("--replicas")] = 3,
    cloud: Annotated[str, typer.Option("--cloud", "-c")] = "aws",
    output_dir: Annotated[str | None, typer.Option("--out", "-o")] = None,
    write: Annotated[bool, typer.Option("--write/--no-write")] = True,
) -> None:
    """Generate a Restricted Pod-Security Helm v3 chart with NetworkPolicy, HPA & PDB."""
    platform = build_platform()
    req = HelmGenerateRequest(
        chart_name=chart,
        image=image,
        port=port,
        replicas=replicas,
        cloud=CloudProvider(cloud.lower()),
        write_to_disk=write,
        output_dir=output_dir,
    )
    console.print_json(platform.script_writers.generate_helm(req).model_dump_json())


@iac_app.command("cicd")
def iac_cicd_cmd(
    project: Annotated[str, typer.Option("--project", "-n")] = "syncro-service",
    platform_name: Annotated[str, typer.Option("--platform", "-p", help="github-actions | gitlab-ci | azure-devops | jenkins")] = "github-actions",
    language: Annotated[str, typer.Option("--language", "-l")] = "python",
    cloud: Annotated[str, typer.Option("--cloud", "-c")] = "aws",
    strategy: Annotated[str, typer.Option("--strategy")] = "canary",
    output_dir: Annotated[str | None, typer.Option("--out", "-o")] = None,
    write: Annotated[bool, typer.Option("--write/--no-write")] = True,
) -> None:
    """Generate a DevSecOps CI/CD pipeline integrated with Syncro CLI, Trivy, Bandit, SAST & DAST."""
    platform = build_platform()
    req = CicdGenerateRequest(
        project_name=project,
        platform=platform_name,
        language=language,
        cloud=CloudProvider(cloud.lower()),
        deploy_strategy=strategy,
        write_to_disk=write,
        output_dir=output_dir,
    )
    console.print_json(platform.script_writers.generate_cicd(req).model_dump_json())


@iac_app.command("container")
def iac_container_cmd(
    service: Annotated[str, typer.Option("--service", "-s")] = "syncro-api",
    language: Annotated[str, typer.Option("--language", "-l", help="python | node | go | java")] = "python",
    port: Annotated[int, typer.Option("--port")] = 8080,
    output_dir: Annotated[str | None, typer.Option("--out", "-o")] = None,
    write: Annotated[bool, typer.Option("--write/--no-write")] = True,
) -> None:
    """Generate a hardened multi-stage non-root Dockerfile & .dockerignore."""
    platform = build_platform()
    req = ContainerGenerateRequest(
        service_name=service,
        language=language,
        port=port,
        write_to_disk=write,
        output_dir=output_dir,
    )
    console.print_json(platform.script_writers.generate_container(req).model_dump_json())


# =============================================================================
# Security Assessment MCP CLI (`syncro sec ...`: Trivy, Bandit, SAST, DAST)
# =============================================================================
@sec_app.command("status")
def sec_status_cmd() -> None:
    """Inspect installed Security & IaC MCP scanner binaries and guardrails."""
    platform = build_platform()
    console.print_json(json.dumps(platform.security_mcp.toolchain_status()))


@sec_app.command("trivy")
def sec_trivy_cmd(
    path: Annotated[str | None, typer.Option("--path", "-p")] = None,
    project: Annotated[str, typer.Option("--project")] = "syncro-workspace",
    json_output: Annotated[bool, typer.Option("--json")] = True,
) -> None:
    """Run Trivy vulnerability, secret, Dockerfile, K8s/Helm, and IaC assessment."""
    platform = build_platform()
    target = Path(path) if path else platform.settings.repo_root
    rep = asyncio.run(platform.security_mcp.run_trivy(target_path=target, project_id=project))
    if json_output:
        console.print_json(rep.model_dump_json())
    else:
        console.print(f"[bold]Trivy Assessment[/bold]: Grade={rep.grade} Score={rep.compliance_score}/100 Findings={len(rep.findings)}")


@sec_app.command("bandit")
def sec_bandit_cmd(
    path: Annotated[str | None, typer.Option("--path", "-p")] = None,
    project: Annotated[str, typer.Option("--project")] = "syncro-workspace",
    json_output: Annotated[bool, typer.Option("--json")] = True,
) -> None:
    """Run Bandit Python AST security assessment."""
    platform = build_platform()
    target = Path(path) if path else platform.settings.repo_root
    rep = asyncio.run(platform.security_mcp.run_bandit(target_path=target, project_id=project))
    if json_output:
        console.print_json(rep.model_dump_json())
    else:
        console.print(f"[bold]Bandit Assessment[/bold]: Grade={rep.grade} Score={rep.compliance_score}/100 Findings={len(rep.findings)}")


@sec_app.command("sast")
def sec_sast_cmd(
    path: Annotated[str | None, typer.Option("--path", "-p")] = None,
    project: Annotated[str, typer.Option("--project")] = "syncro-workspace",
    json_output: Annotated[bool, typer.Option("--json")] = True,
) -> None:
    """Run multi-language OWASP Top 10 SAST security assessment."""
    platform = build_platform()
    target = Path(path) if path else platform.settings.repo_root
    rep = asyncio.run(platform.security_mcp.run_sast(target_path=target, project_id=project))
    if json_output:
        console.print_json(rep.model_dump_json())
    else:
        console.print(f"[bold]SAST Assessment[/bold]: Grade={rep.grade} Score={rep.compliance_score}/100 Findings={len(rep.findings)}")


@sec_app.command("dast")
def sec_dast_cmd(
    url: Annotated[str, typer.Option("--url", "-u")] = "http://127.0.0.1:8080/api/v1/health",
    project: Annotated[str, typer.Option("--project")] = "syncro-workspace",
    live: Annotated[bool, typer.Option("--live/--simulate")] = True,
    json_output: Annotated[bool, typer.Option("--json")] = True,
) -> None:
    """Run non-destructive OWASP DAST baseline assessment against a target HTTP/HTTPS URL."""
    platform = build_platform()
    rep = asyncio.run(platform.security_mcp.run_dast(target_url=url, project_id=project, live_probe=live))
    if json_output:
        console.print_json(rep.model_dump_json())
    else:
        console.print(f"[bold]DAST Assessment[/bold]: Grade={rep.grade} Score={rep.compliance_score}/100 Probes={len(rep.dast_probes)}")


@sec_app.command("assess")
def sec_full_assess_cmd(
    path: Annotated[str | None, typer.Option("--path", "-p")] = None,
    url: Annotated[str | None, typer.Option("--url", "-u")] = None,
    project: Annotated[str, typer.Option("--project")] = "payments-core",
    sarif_out: Annotated[str | None, typer.Option("--sarif-out")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = True,
) -> None:
    """Run unified DevSecOps assessment (Trivy + Bandit + SAST + IaC + optional DAST + OPA + SARIF + Graph)."""
    platform = build_platform()
    target = Path(path) if path else platform.settings.repo_root
    rep = asyncio.run(
        platform.security_mcp.run_full_assessment(
            project_id=project,
            target_path=target,
            target_url=url,
            include_dast=bool(url),
            include_graph=True,
        )
    )
    if sarif_out and rep.sarif:
        Path(sarif_out).write_text(json.dumps(rep.sarif, indent=2), encoding="utf-8")
    if json_output:
        console.print_json(rep.model_dump_json())
    else:
        console.print(
            Panel(
                f"Grade: [bold]{rep.grade}[/bold]  Score: [bold]{rep.compliance_score}/100[/bold]\n"
                f"OPA Allowed: {rep.opa_gate.allowed}  Findings: {len(rep.findings)}\n"
                f"{rep.devsecops_graph.ascii_summary if rep.devsecops_graph else ''}",
                title="Syncro Security MCP Assessment",
            )
        )
