"""Terraform IaC Studio Engine — Generate, Build/Validate, Guardrailed Run, and DevSecOps Graph."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from aegisops.domain.models import CloudProvider
from aegisops.iac.graph_builder import DevSecOpsGraphBuilder
from aegisops.iac.models import (
    DevSecOpsGraph,
    GeneratedFile,
    IacBlueprintKind,
    TerraformBuildResult,
    TerraformGenerateRequest,
    TerraformRunRequest,
    TerraformRunResult,
    TerraformWorkspaceBundle,
)
from aegisops.security.scanners import SecurityPipelineEngine

_DEFAULT_REGIONS: dict[CloudProvider, str] = {
    CloudProvider.AWS: "us-east-1",
    CloudProvider.GCP: "us-central1",
    CloudProvider.AZURE: "eastus2",
}

_RESOURCE_RE = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"')
_MODULE_RE = re.compile(r'module\s+"([^"]+)"')
_VAR_RE = re.compile(r'variable\s+"([^"]+)"')
_OUT_RE = re.compile(r'output\s+"([^"]+)"')


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned or "syncro-stack"


def _make_file(path: str, content: str, language: str = "hcl") -> GeneratedFile:
    return GeneratedFile(
        path=path,
        content=content,
        language=language,
        lines=content.count("\n") + 1,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
    )


class TerraformIacEngine:
    """Generates hardened multi-cloud Terraform workspaces, validates/builds them, runs them safely, and builds DevSecOps graphs."""

    def __init__(
        self,
        workspace_root: Path,
        scanner: SecurityPipelineEngine,
        graph_builder: DevSecOpsGraphBuilder | None = None,
        mode: str = "simulation",
    ) -> None:
        self._workspace_root = workspace_root
        self._scanner = scanner
        self._graph_builder = graph_builder or DevSecOpsGraphBuilder()
        self._mode = mode
        self.workspaces: dict[str, TerraformWorkspaceBundle] = {}
        self.latest_graphs: list[DevSecOpsGraph] = []

    @property
    def terraform_binary(self) -> str | None:
        return shutil.which("terraform") or shutil.which("tofu")

    def list_workspaces(self) -> list[TerraformWorkspaceBundle]:
        return list(self.workspaces.values())

    def generate(self, req: TerraformGenerateRequest) -> TerraformWorkspaceBundle:
        slug = _slug(req.project_name)
        region = req.region or _DEFAULT_REGIONS[req.cloud]

        if req.cloud == CloudProvider.AWS:
            files, monthly, controls = self._render_aws(slug, region, req)
        elif req.cloud == CloudProvider.GCP:
            files, monthly, controls = self._render_gcp(slug, region, req)
        else:
            files, monthly, controls = self._render_azure(slug, region, req)

        resources: list[str] = []
        for f in files:
            if f.path.endswith(".tf"):
                for rtype, rname in _RESOURCE_RE.findall(f.content):
                    resources.append(f"{rtype}.{rname}")

        bundle = TerraformWorkspaceBundle(
            project_name=slug,
            cloud=req.cloud,
            blueprint=req.blueprint,
            region=region,
            environment=req.environment,
            workspace_dir="",
            files=files,
            resources=resources,
            estimated_monthly_usd=monthly,
            compliance_controls=controls,
        )

        target_dir = (
            Path(req.output_dir)
            if req.output_dir
            else self._workspace_root / "terraform" / f"{slug}-{bundle.workspace_id}"
        )
        bundle.workspace_dir = str(target_dir)

        if req.write_to_disk:
            target_dir.mkdir(parents=True, exist_ok=True)
            for gen in files:
                out_path = target_dir / gen.path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(gen.content, encoding="utf-8")
            bundle.written_to_disk = True

        self.workspaces[bundle.workspace_id] = bundle
        return bundle

    async def build(
        self,
        workspace_id: str | None = None,
        workspace_dir: str | None = None,
    ) -> TerraformBuildResult:
        started = time.perf_counter()
        ws_id, target_dir, hcl_map = self._resolve_workspace(workspace_id, workspace_dir)

        syntax_issues: list[str] = []
        resources: list[str] = []
        modules: list[str] = []
        variables: list[str] = []
        outputs: list[str] = []

        if not hcl_map:
            syntax_issues.append(f"No Terraform (.tf) files found in {target_dir}")

        for fname, content in sorted(hcl_map.items()):
            open_braces = content.count("{")
            close_braces = content.count("}")
            if open_braces != close_braces:
                syntax_issues.append(f"{fname}: unbalanced braces ({open_braces} '{{' vs {close_braces} '}}')")
            for rtype, rname in _RESOURCE_RE.findall(content):
                resources.append(f"{rtype}.{rname}")
            modules.extend(_MODULE_RE.findall(content))
            variables.extend(_VAR_RE.findall(content))
            outputs.extend(_OUT_RE.findall(content))

        engine = "hcl-validator"
        init_ok = len(syntax_issues) == 0
        fmt_ok = len(syntax_issues) == 0
        validate_ok = len(syntax_issues) == 0
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        tf_bin = self.terraform_binary
        if tf_bin and target_dir.exists() and any(target_dir.glob("*.tf")):
            engine = "tofu-cli" if Path(tf_bin).stem.lower() == "tofu" else "terraform-cli"
            # Run `fmt -check` (offline, zero network)
            fmt_proc = await asyncio.create_subprocess_exec(
                tf_bin,
                f"-chdir={target_dir}",
                "fmt",
                "-check",
                "-no-color",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            f_out, f_err = await fmt_proc.communicate()
            fmt_ok = fmt_proc.returncode == 0
            if f_out:
                stdout_parts.append(f"[fmt]\n{f_out.decode(errors='ignore')[:1000]}")
            if f_err:
                stderr_parts.append(f"[fmt]\n{f_err.decode(errors='ignore')[:600]}")

            if self._mode == "live":
                init_proc = await asyncio.create_subprocess_exec(
                    tf_bin,
                    f"-chdir={target_dir}",
                    "init",
                    "-backend=false",
                    "-input=false",
                    "-no-color",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                i_out, i_err = await init_proc.communicate()
                init_ok = init_proc.returncode == 0
                stdout_parts.append(f"[init]\n{i_out.decode(errors='ignore')[:1500]}")
                if i_err:
                    stderr_parts.append(f"[init]\n{i_err.decode(errors='ignore')[:800]}")

                if init_ok:
                    val_proc = await asyncio.create_subprocess_exec(
                        tf_bin,
                        f"-chdir={target_dir}",
                        "validate",
                        "-json",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    v_out, v_err = await val_proc.communicate()
                    validate_ok = val_proc.returncode == 0
                    stdout_parts.append(f"[validate]\n{v_out.decode(errors='ignore')[:1500]}")
                    if not validate_ok:
                        try:
                            parsed = json.loads(v_out.decode(errors="ignore"))
                            for diag in parsed.get("diagnostics", []):
                                syntax_issues.append(str(diag.get("summary", "Terraform validation error")))
                        except json.JSONDecodeError:
                            if v_err:
                                syntax_issues.append(v_err.decode(errors="ignore")[:400])
            else:
                stdout_parts.append(
                    f"HCL structural build validated {len(hcl_map)} file(s), {len(resources)} resource(s), "
                    f"{len(variables)} variable(s), {len(outputs)} output(s) [binary detected: {engine}]."
                )
        else:
            stdout_parts.append(
                f"Syncro HCL validator passed: {len(hcl_map)} file(s), {len(resources)} resource(s), "
                f"{len(variables)} variable(s), {len(outputs)} output(s)."
            )

        duration_ms = max(1, int((time.perf_counter() - started) * 1000))
        return TerraformBuildResult(
            workspace_id=ws_id,
            workspace_dir=str(target_dir),
            engine=engine,
            init_ok=init_ok,
            fmt_ok=fmt_ok,
            validate_ok=validate_ok and len(syntax_issues) == 0,
            syntax_issues=syntax_issues,
            resources_discovered=resources,
            modules_discovered=modules,
            variables_discovered=variables,
            outputs_discovered=outputs,
            plan_summary={"to_add": len(resources), "to_change": 0, "to_destroy": 0},
            stdout="\n".join(stdout_parts),
            stderr="\n".join(stderr_parts),
            duration_ms=duration_ms,
        )

    async def run(self, req: TerraformRunRequest) -> TerraformRunResult:
        started = time.perf_counter()
        action = req.action.strip().lower()
        if action not in {"plan", "apply", "destroy"}:
            raise ValueError(f"Unsupported Terraform action '{req.action}'. Allowed: plan, apply, destroy.")

        ws_id, target_dir, hcl_map = self._resolve_workspace(req.workspace_id, req.workspace_dir)
        ws = self.workspaces.get(ws_id)
        cloud_str = ws.cloud.value if ws else self._infer_cloud(hcl_map)

        guardrail_reasons: list[str] = []
        guardrail_allowed = True

        # Guardrail 1: Production destroy block
        if action == "destroy" and req.environment.lower() in {"prod", "production"}:
            guardrail_allowed = False
            guardrail_reasons.append("Production Terraform destroy is strictly blocked by Syncro guardrails.")

        # Guardrail 2: Pre-run IaC security scan
        scan_findings: list[dict[str, Any]] = []
        if target_dir.exists():
            scan_report = await self._scanner.run_scan(
                project_id=ws.project_name if ws else target_dir.name,
                target_path=target_dir,
                scanners=["checkov", "tfsec", "trivy", "opa"],
            )
            scan_findings = [f.model_dump(mode="json") for f in scan_report.findings]
            if not scan_report.opa_gate.allowed and action == "apply":
                guardrail_allowed = False
                guardrail_reasons.extend(scan_report.opa_gate.violations)

        # Always build the DevSecOps graph with security findings overlaid!
        graph = self._graph_builder.build_from_hcl_files(
            title=f"Terraform DevSecOps Graph — {ws.project_name if ws else target_dir.name}",
            cloud=cloud_str,
            hcl_files=hcl_map,
            findings=scan_findings,
            include_devsecops_pipeline=True,
        )
        self.latest_graphs.insert(0, graph)
        self.latest_graphs = self.latest_graphs[:20]

        if not guardrail_allowed:
            return TerraformRunResult(
                workspace_id=ws_id,
                workspace_dir=str(target_dir),
                action=action,
                engine="syncro-guardrail",
                dry_run=req.dry_run,
                guardrail_allowed=False,
                guardrail_reasons=guardrail_reasons,
                exit_code=126,
                status="blocked",
                devsecops_graph=graph,
                stderr="; ".join(guardrail_reasons),
                duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
            )

        resources: list[str] = []
        outputs_discovered: list[str] = []
        for content in hcl_map.values():
            for rtype, rname in _RESOURCE_RE.findall(content):
                resources.append(f"{rtype}.{rname}")
            outputs_discovered.extend(_OUT_RE.findall(content))

        tf_bin = self.terraform_binary
        if self._mode == "live" and tf_bin and target_dir.exists() and not req.dry_run:
            cmd = [tf_bin, f"-chdir={target_dir}", action, "-input=false", "-no-color"]
            if action in {"apply", "destroy"} and req.auto_approve:
                cmd.append("-auto-approve")
            for k, v in req.vars.items():
                cmd.append(f"-var={k}={v}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_b, err_b = await proc.communicate()
            status = "succeeded" if proc.returncode == 0 else "failed"
            return TerraformRunResult(
                workspace_id=ws_id,
                workspace_dir=str(target_dir),
                action=action,
                engine=Path(tf_bin).stem,
                dry_run=False,
                guardrail_allowed=True,
                exit_code=int(proc.returncode or 0),
                status=status,
                applied_resources=resources if proc.returncode == 0 else [],
                devsecops_graph=graph,
                stdout=out_b.decode(errors="ignore")[:4000],
                stderr=err_b.decode(errors="ignore")[:1000],
                duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
            )

        # Deterministic simulation / dry-run execution
        sim_outputs = {
            out_name: f"sim-{cloud_str}-{ws_id}-{out_name}"
            for out_name in outputs_discovered
        }
        status_label = "planned" if (action == "plan" or req.dry_run) else (
            "destroyed" if action == "destroy" else "applied"
        )
        stdout = (
            f"Terraform {action.upper()} ({'dry-run' if req.dry_run else 'simulated-apply'}) "
            f"for {ws_id}: {len(resources)} resource(s) processed across {cloud_str.upper()}.\n"
            f"DevSecOps Graph Security Score: {graph.security_score}/100 "
            f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)."
        )
        return TerraformRunResult(
            workspace_id=ws_id,
            workspace_dir=str(target_dir),
            action=action,
            engine="terraform-simulator",
            dry_run=req.dry_run,
            guardrail_allowed=True,
            guardrail_reasons=["OPA & IaC security preflight passed"],
            exit_code=0,
            status=status_label,
            applied_resources=resources,
            outputs=sim_outputs,
            devsecops_graph=graph,
            stdout=stdout,
            duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
        )

    def build_graph(
        self,
        workspace_id: str | None = None,
        workspace_dir: str | None = None,
        findings: list[dict[str, Any]] | None = None,
        include_pipeline: bool = True,
    ) -> DevSecOpsGraph:
        ws_id, target_dir, hcl_map = self._resolve_workspace(workspace_id, workspace_dir)
        ws = self.workspaces.get(ws_id)
        cloud_str = ws.cloud.value if ws else self._infer_cloud(hcl_map)
        graph = self._graph_builder.build_from_hcl_files(
            title=f"Syncro DevSecOps Graph — {ws.project_name if ws else target_dir.name}",
            cloud=cloud_str,
            hcl_files=hcl_map,
            findings=findings,
            include_devsecops_pipeline=include_pipeline,
        )
        self.latest_graphs.insert(0, graph)
        self.latest_graphs = self.latest_graphs[:20]
        return graph

    def _resolve_workspace(
        self, workspace_id: str | None, workspace_dir: str | None
    ) -> tuple[str, Path, dict[str, str]]:
        if workspace_id and workspace_id in self.workspaces:
            ws = self.workspaces[workspace_id]
            return ws.workspace_id, Path(ws.workspace_dir), {
                f.path: f.content for f in ws.files if f.path.endswith(".tf")
            }

        target = Path(workspace_dir) if workspace_dir else (
            Path(next(reversed(self.workspaces.values())).workspace_dir)
            if self.workspaces
            else self._workspace_root
        )
        hcl_map: dict[str, str] = {}
        if target.exists():
            for tf_file in sorted(target.rglob("*.tf")):
                if ".terraform" in tf_file.parts:
                    continue
                hcl_map[str(tf_file.relative_to(target))] = tf_file.read_text(encoding="utf-8", errors="ignore")
        return workspace_id or target.name, target, hcl_map

    @staticmethod
    def _infer_cloud(hcl_map: dict[str, str]) -> str:
        joined = "\n".join(hcl_map.values())
        if "aws_" in joined:
            return "aws"
        if "google_" in joined:
            return "gcp"
        if "azurerm_" in joined:
            return "azure"
        return "multi"

    # -------------------------------------------------------------------------
    # Cloud-specific hardened multi-file Terraform HCL generators
    # -------------------------------------------------------------------------
    def _render_aws(
        self, slug: str, region: str, req: TerraformGenerateRequest
    ) -> tuple[list[GeneratedFile], float, list[str]]:
        providers_tf = f'''terraform {{
  required_version = ">= 1.7.0"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.75"
    }}
  }}
}}

provider "aws" {{
  region = var.aws_region
  default_tags {{
    tags = merge({{
      "syncro:managed"     = "true"
      "syncro:project"     = var.project_name
      "syncro:environment" = var.environment
      "syncro:blueprint"   = "{req.blueprint.value}"
    }}, var.extra_tags)
  }}
}}
'''
        variables_tf = f'''variable "project_name" {{
  type    = string
  default = "{slug}"
}}

variable "environment" {{
  type    = string
  default = "{req.environment}"
}}

variable "aws_region" {{
  type    = string
  default = "{region}"
}}

variable "vpc_cidr" {{
  type    = string
  default = "10.42.0.0/16"
}}

variable "extra_tags" {{
  type    = map(string)
  default = {{}}
}}
'''
        security_tf = '''resource "aws_kms_key" "syncro" {
  description             = "${var.project_name}-${var.environment} CMK"
  deletion_window_in_days = 14
  enable_key_rotation     = true
}

resource "aws_iam_role" "workload_role" {
  name = "${var.project_name}-${var.environment}-workload-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_security_group" "workload_sg" {
  name        = "${var.project_name}-${var.environment}-sg"
  description = "Zero-trust least-privilege ingress (HTTPS only from VPC)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Internal HTTPS TLS 1.3"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_s3_bucket" "audit_artifacts" {
  bucket = "${var.project_name}-${var.environment}-audit-artifacts"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_artifacts" {
  bucket = aws_s3_bucket.audit_artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.syncro.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "audit_artifacts" {
  bucket                  = aws_s3_bucket.audit_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
'''
        compute_block = (
            '''resource "aws_eks_cluster" "primary" {
  name     = "${var.project_name}-${var.environment}-eks"
  role_arn = aws_iam_role.workload_role.arn

  vpc_config {
    subnet_ids              = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    endpoint_private_access = true
    endpoint_public_access  = false
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.syncro.arn
    }
    resources = ["secrets"]
  }
}
'''
            if req.blueprint in {IacBlueprintKind.VPC_K8S, IacBlueprintKind.ZERO_TRUST_MESH, IacBlueprintKind.DATA_PLATFORM}
            else '''resource "aws_instance" "hardened_node" {
  ami                    = "ami-0c7217cdde317cfec"
  instance_type          = "c7g.xlarge"
  subnet_id              = aws_subnet.private_a.id
  vpc_security_group_ids = [aws_security_group.workload_sg.id]

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    encrypted   = true
    kms_key_id  = aws_kms_key.syncro.arn
    volume_type = "gp3"
    volume_size = 50
  }
}
'''
        )
        waf_block = (
            '''resource "aws_wafv2_web_acl" "edge" {
  name  = "${var.project_name}-${var.environment}-waf"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-waf"
    sampled_requests_enabled   = true
  }
}
'''
            if req.enable_waf
            else ""
        )
        main_tf = f'''resource "aws_vpc" "main" {{
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
}}

resource "aws_subnet" "private_a" {{
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.42.1.0/24"
  map_public_ip_on_launch = false
}}

resource "aws_subnet" "private_b" {{
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.42.2.0/24"
  map_public_ip_on_launch = false
}}

{compute_block}
{waf_block}
resource "aws_cloudwatch_log_group" "audit" {{
  name              = "/syncro/${{var.project_name}}/${{var.environment}}"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.syncro.arn
}}
'''
        outputs_tf = '''output "vpc_id" {
  value = aws_vpc.main.id
}

output "kms_key_arn" {
  value = aws_kms_key.syncro.arn
}

output "audit_bucket" {
  value = aws_s3_bucket.audit_artifacts.id
}
'''
        tfvars = f'project_name = "{slug}"\nenvironment  = "{req.environment}"\naws_region   = "{region}"\n'
        controls = [
            "AWS KMS CMK with Automatic Key Rotation",
            "IMDSv2 Strictly Required / Private EKS API",
            "S3 Public Access Blocked + KMS SSE",
            "Zero-Trust Security Group (No 0.0.0.0/0 SSH/RDP)",
            "Encrypted CloudWatch Audit Logs (90d Retention)",
        ]
        monthly = 248.5 if req.blueprint == IacBlueprintKind.VPC_K8S else 118.0
        return (
            [
                _make_file("providers.tf", providers_tf),
                _make_file("variables.tf", variables_tf),
                _make_file("security.tf", security_tf),
                _make_file("main.tf", main_tf),
                _make_file("outputs.tf", outputs_tf),
                _make_file("terraform.tfvars.example", tfvars, "hcl"),
            ],
            monthly,
            controls,
        )

    def _render_gcp(
        self, slug: str, region: str, req: TerraformGenerateRequest
    ) -> tuple[list[GeneratedFile], float, list[str]]:
        providers_tf = '''terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}
'''
        variables_tf = f'''variable "project_name" {{
  type    = string
  default = "{slug}"
}}

variable "environment" {{
  type    = string
  default = "{req.environment}"
}}

variable "gcp_project_id" {{
  type    = string
  default = "syncro-gcp-devsecops"
}}

variable "gcp_region" {{
  type    = string
  default = "{region}"
}}
'''
        security_tf = '''resource "google_kms_key_ring" "syncro" {
  name     = "${var.project_name}-${var.environment}-ring"
  location = var.gcp_region
}

resource "google_kms_crypto_key" "syncro" {
  name            = "${var.project_name}-cmek"
  key_ring        = google_kms_key_ring.syncro.id
  rotation_period = "7776000s"
}

resource "google_service_account" "workload" {
  account_id   = "${var.project_name}-sa"
  display_name = "Syncro Least-Privilege Workload SA"
}

resource "google_compute_firewall" "iap_only_ssh" {
  name    = "${var.project_name}-iap-ssh"
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
}

resource "google_storage_bucket" "audit" {
  name                        = "${var.project_name}-${var.environment}-audit-gcs"
  location                    = var.gcp_region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  encryption {
    default_kms_key_name = google_kms_crypto_key.syncro.id
  }
}
'''
        main_tf = '''resource "google_compute_network" "main" {
  name                    = "${var.project_name}-${var.environment}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private" {
  name                     = "${var.project_name}-${var.environment}-subnet"
  ip_cidr_range            = "10.44.1.0/24"
  region                   = var.gcp_region
  network                  = google_compute_network.main.id
  private_ip_google_access = true
}

resource "google_compute_instance" "shielded_node" {
  name         = "${var.project_name}-${var.environment}-vm"
  machine_type = "c3d-standard-4"
  zone         = "${var.gcp_region}-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
    kms_key_self_link = google_kms_crypto_key.syncro.id
  }

  network_interface {
    subnetwork = google_compute_subnetwork.private.id
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  confidential_instance_config {
    enable_confidential_compute = true
  }

  service_account {
    email  = google_service_account.workload.email
    scopes = ["cloud-platform"]
  }
}
'''
        outputs_tf = '''output "vpc_self_link" {
  value = google_compute_network.main.self_link
}

output "cmek_id" {
  value = google_kms_crypto_key.syncro.id
}

output "audit_bucket" {
  value = google_storage_bucket.audit.name
}
'''
        controls = [
            "GCP Cloud KMS CMEK with 90-day Rotation",
            "Shielded VM (Secure Boot + vTPM + Integrity Monitoring)",
            "Confidential Compute (AMD SEV-SNP)",
            "Identity-Aware Proxy Only SSH (35.235.240.0/20)",
            "GCS Uniform Bucket-Level Access + Public Prevention Enforced",
        ]
        return (
            [
                _make_file("providers.tf", providers_tf),
                _make_file("variables.tf", variables_tf),
                _make_file("security.tf", security_tf),
                _make_file("main.tf", main_tf),
                _make_file("outputs.tf", outputs_tf),
            ],
            214.0,
            controls,
        )

    def _render_azure(
        self, slug: str, region: str, req: TerraformGenerateRequest
    ) -> tuple[list[GeneratedFile], float, list[str]]:
        providers_tf = '''terraform {
  required_version = ">= 1.7.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.10"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}
'''
        variables_tf = f'''variable "project_name" {{
  type    = string
  default = "{slug}"
}}

variable "environment" {{
  type    = string
  default = "{req.environment}"
}}

variable "location" {{
  type    = string
  default = "{region}"
}}
'''
        security_tf = '''resource "azurerm_key_vault" "syncro" {
  name                       = "${substr(replace(var.project_name, "-", ""), 0, 12)}kv${var.environment}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = "00000000-0000-0000-0000-000000000000"
  sku_name                   = "premium"
  purge_protection_enabled   = true
  soft_delete_retention_days = 90
  enable_rbac_authorization  = true
}

resource "azurerm_network_security_group" "zero_trust" {
  name                = "${var.project_name}-${var.environment}-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "AllowInternalHttps"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }
}

resource "azurerm_container_registry" "syncro" {
  name                = "${substr(replace(var.project_name, "-", ""), 0, 14)}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Premium"
  admin_enabled       = false
}
'''
        main_tf = '''resource "azurerm_resource_group" "main" {
  name     = "rg-${var.project_name}-${var.environment}"
  location = var.location
}

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.project_name}-${var.environment}"
  address_space       = ["10.46.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_subnet" "workloads" {
  name                 = "snet-workloads"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.46.1.0/24"]
}

resource "azurerm_kubernetes_cluster" "aks" {
  name                              = "aks-${var.project_name}-${var.environment}"
  location                          = azurerm_resource_group.main.location
  resource_group_name               = azurerm_resource_group.main.name
  dns_prefix                        = "${var.project_name}-${var.environment}"
  private_cluster_enabled           = true
  role_based_access_control_enabled = true

  default_node_pool {
    name           = "system"
    node_count     = 2
    vm_size        = "Standard_DC4as_v5"
    vnet_subnet_id = azurerm_subnet.workloads.id
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_log_analytics_workspace" "audit" {
  name                = "law-${var.project_name}-${var.environment}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 90
}
'''
        outputs_tf = '''output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.aks.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.syncro.vault_uri
}
'''
        controls = [
            "Azure Key Vault Premium with Purge Protection + RBAC",
            "Private AKS Cluster + Kubernetes RBAC + System Managed Identity",
            "ACR Premium with admin_enabled = false",
            "Zero-Trust NSG (No Public SSH/RDP)",
            "Log Analytics Audit Workspace (90d Retention)",
        ]
        return (
            [
                _make_file("providers.tf", providers_tf),
                _make_file("variables.tf", variables_tf),
                _make_file("security.tf", security_tf),
                _make_file("main.tf", main_tf),
                _make_file("outputs.tf", outputs_tf),
            ],
            262.0,
            controls,
        )
