"""DevSecOps Architecture, Terraform Dependency & Security Posture Graph Builder."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aegisops.iac.models import DevSecOpsGraph, GraphEdge, GraphNode

_LAYER_ORDER = [
    "cicd",
    "security",
    "edge",
    "identity",
    "network",
    "compute",
    "data",
    "observability",
]

_RESOURCE_BLOCK_RE = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
_MODULE_BLOCK_RE = re.compile(r'module\s+"([^"]+)"\s*\{', re.MULTILINE)
_DEPENDS_ON_RE = re.compile(r"depends_on\s*=\s*\[([^\]]*)\]", re.DOTALL)


def _classify_layer(resource_type: str) -> str:
    rt = resource_type.lower()
    if any(k in rt for k in ("waf", "cloudfront", "frontdoor", "cdn", "ingress", "alb", "lb", "gateway", "firewall")):
        return "edge"
    if any(k in rt for k in ("iam", "role", "identity", "kms", "key_vault", "secret", "policy", "rbac", "service_account")):
        return "identity"
    if any(k in rt for k in ("vpc", "vnet", "subnet", "network", "security_group", "nsg", "route", "nat", "private_endpoint")):
        return "network"
    if any(k in rt for k in ("eks", "aks", "gke", "kubernetes", "container", "instance", "virtual_machine", "lambda", "function", "cloud_run", "ecs", "vm")):
        return "compute"
    if any(k in rt for k in ("rds", "sql", "postgres", "cosmos", "dynamodb", "s3", "storage", "bucket", "redis", "kafka", "acr", "ecr", "artifact")):
        return "data"
    if any(k in rt for k in ("log", "monitor", "cloudwatch", "insight", "prometheus", "metric", "audit", "trail", "alarm")):
        return "observability"
    return "compute"


def _classify_cloud(resource_type: str, default_cloud: str = "multi") -> str:
    rt = resource_type.lower()
    if rt.startswith("aws_"):
        return "aws"
    if rt.startswith("azurerm_") or rt.startswith("azuread_"):
        return "azure"
    if rt.startswith("google_"):
        return "gcp"
    return default_cloud


def _default_controls_for_resource(resource_type: str, body: str) -> list[str]:
    controls: list[str] = []
    rt = resource_type.lower()
    if "encrypted = true" in body or "kms_key" in body or "cmek" in body or "purge_protection_enabled = true" in body:
        controls.append("Encryption-at-Rest (KMS/CMEK)")
    if "http_tokens" in body and "required" in body:
        controls.append("IMDSv2 Enforced")
    if "enable_secure_boot = true" in body or "secure_boot_enabled = true" in body:
        controls.append("Secure Boot + vTPM")
    if "private_cluster" in body or "endpoint_private_access = true" in body or "private_endpoint" in rt:
        controls.append("Private Endpoint / Zero Public Exposure")
    if "uniform_bucket_level_access = true" in body or "block_public_acls = true" in body:
        controls.append("Public Access Blocked")
    if "waf" in rt or "firewall" in rt or "security_group" in rt or "network_security_group" in rt:
        controls.append("Zero-Trust Network Boundary")
    if "iam" in rt or "role" in rt or "service_account" in rt:
        controls.append("Least-Privilege Identity")
    if not controls:
        controls.append("Syncro Managed IaC Guardrail")
    return controls


def _extract_block_body(text: str, open_brace_idx: int) -> str:
    depth = 0
    for idx in range(open_brace_idx, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_idx + 1 : idx]
    return text[open_brace_idx + 1 :]


def _safe_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned or "node"


def _severity_rank(level: str) -> int:
    return {"ok": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(level.lower(), 0)


class DevSecOpsGraphBuilder:
    """Builds Terraform dependency + DevSecOps security posture graphs in JSON, Mermaid, DOT, and ASCII."""

    def build_from_hcl_files(
        self,
        title: str,
        cloud: str,
        hcl_files: dict[str, str],
        findings: list[dict[str, Any]] | None = None,
        include_devsecops_pipeline: bool = True,
    ) -> DevSecOpsGraph:
        nodes_map: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        block_bodies: dict[str, str] = {}

        if include_devsecops_pipeline:
            pipeline_nodes = [
                GraphNode(
                    id="cicd_git_pr",
                    label="GitOps PR & Syncro CLI",
                    kind="cicd.source",
                    layer="cicd",
                    cloud="multi",
                    controls=["Signed Commits", "Branch Protection"],
                ),
                GraphNode(
                    id="sec_sast_bandit",
                    label="SAST + Bandit + Secrets Gate",
                    kind="security.sast",
                    layer="security",
                    cloud="multi",
                    controls=["Bandit Python AST", "Multi-Lang SAST", "Secret Scanner"],
                ),
                GraphNode(
                    id="sec_trivy_iac",
                    label="Trivy + Checkov + OPA Rego",
                    kind="security.iac",
                    layer="security",
                    cloud="multi",
                    controls=["Trivy FS/Container/IaC", "OPA Rego Admission", "SBOM"],
                ),
                GraphNode(
                    id="sec_dast_canary",
                    label="DAST + Canary SLO Gate",
                    kind="security.dast",
                    layer="security",
                    cloud="multi",
                    controls=["OWASP Header/CORS/TLS DAST", "Auto-Rollback Circuit Breaker"],
                ),
            ]
            for pn in pipeline_nodes:
                nodes_map[pn.id] = pn
            edges.extend(
                [
                    GraphEdge(source="cicd_git_pr", target="sec_sast_bandit", relation="static-scan", protocol="MCP/CLI"),
                    GraphEdge(source="sec_sast_bandit", target="sec_trivy_iac", relation="iac-policy-gate", protocol="OPA/SARIF"),
                ]
            )

        # 1. Discover all Terraform resources and modules
        for filename, content in sorted(hcl_files.items()):
            for match in _RESOURCE_BLOCK_RE.finditer(content):
                res_type, res_name = match.group(1), match.group(2)
                addr = f"{res_type}.{res_name}"
                nid = _safe_id(addr)
                body = _extract_block_body(content, match.end() - 1)
                block_bodies[nid] = body
                nodes_map[nid] = GraphNode(
                    id=nid,
                    label=f"{res_type}\n({res_name})",
                    kind=res_type,
                    layer=_classify_layer(res_type),
                    cloud=_classify_cloud(res_type, cloud),
                    controls=_default_controls_for_resource(res_type, body),
                    metadata={"address": addr, "file": filename},
                )

            for match in _MODULE_BLOCK_RE.finditer(content):
                mod_name = match.group(1)
                addr = f"module.{mod_name}"
                nid = _safe_id(addr)
                body = _extract_block_body(content, match.end() - 1)
                block_bodies[nid] = body
                nodes_map[nid] = GraphNode(
                    id=nid,
                    label=f"module.{mod_name}",
                    kind="terraform.module",
                    layer=_classify_layer(mod_name),
                    cloud=cloud,
                    controls=["Reusable Hardened Module"],
                    metadata={"address": addr, "file": filename},
                )

        # 2. Infer dependency edges from Terraform references & depends_on
        addr_to_id = {
            str(node.metadata.get("address")): node.id
            for node in nodes_map.values()
            if node.metadata.get("address")
        }
        seen_edges: set[tuple[str, str, str]] = {(e.source, e.target, e.relation) for e in edges}

        for nid, body in block_bodies.items():
            for ref_addr, ref_id in addr_to_id.items():
                if ref_id == nid:
                    continue
                if f"{ref_addr}." in body or re.search(rf"\b{re.escape(ref_addr)}\b", body):
                    key = (ref_id, nid, "provisions/depends")
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(
                            GraphEdge(
                                source=ref_id,
                                target=nid,
                                relation="provisions/depends",
                                encrypted=True,
                                protocol="Terraform DAG",
                            )
                        )
            dep_match = _DEPENDS_ON_RE.search(body)
            if dep_match:
                for token in re.findall(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+", dep_match.group(1)):
                    dep_id = addr_to_id.get(token)
                    if dep_id and dep_id != nid:
                        key = (dep_id, nid, "depends_on")
                        if key not in seen_edges:
                            seen_edges.add(key)
                            edges.append(
                                GraphEdge(
                                    source=dep_id,
                                    target=nid,
                                    relation="depends_on",
                                    encrypted=True,
                                    protocol="Explicit DAG",
                                )
                            )

        # 3. Wire DevSecOps pipeline gate -> root IaC nodes and leaf compute/edge -> DAST
        iac_ids = [nid for nid in nodes_map if nid not in {"cicd_git_pr", "sec_sast_bandit", "sec_trivy_iac", "sec_dast_canary"}]
        if include_devsecops_pipeline and iac_ids:
            incoming = {e.target for e in edges if e.source in iac_ids and e.target in iac_ids}
            roots = [nid for nid in iac_ids if nid not in incoming] or iac_ids[:2]
            for root_id in roots[:4]:
                edges.append(
                    GraphEdge(
                        source="sec_trivy_iac",
                        target=root_id,
                        relation="approved-apply",
                        protocol="Terraform/MCP",
                    )
                )
            dast_targets = [
                nid for nid in iac_ids if nodes_map[nid].layer in {"edge", "compute"}
            ] or iac_ids[-2:]
            for dt in dast_targets[:3]:
                edges.append(
                    GraphEdge(
                        source=dt,
                        target="sec_dast_canary",
                        relation="runtime-dast-verify",
                        protocol="HTTPS/OWASP",
                    )
                )

        # 4. Overlay security findings onto matching graph nodes
        findings_list = findings or []
        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0
        for finding in findings_list:
            sev = str(finding.get("severity", "LOW")).lower()
            if sev == "critical":
                critical_count += 1
            elif sev == "high":
                high_count += 1
            elif sev == "medium":
                medium_count += 1
            else:
                low_count += 1

            scanner = str(finding.get("scanner", "")).lower()
            file_path = str(finding.get("file_path", "")).lower()
            matched_node: GraphNode | None = None
            for node in nodes_map.values():
                nf = str(node.metadata.get("file", "")).lower()
                if nf and nf in file_path:
                    matched_node = node
                    break
            if matched_node is None:
                if scanner in {"bandit", "sast", "semgrep"} and "sec_sast_bandit" in nodes_map:
                    matched_node = nodes_map["sec_sast_bandit"]
                elif scanner in {"dast", "zap", "nuclei"} and "sec_dast_canary" in nodes_map:
                    matched_node = nodes_map["sec_dast_canary"]
                elif "sec_trivy_iac" in nodes_map:
                    matched_node = nodes_map["sec_trivy_iac"]
                elif iac_ids:
                    matched_node = nodes_map[iac_ids[0]]

            if matched_node is not None:
                matched_node.findings_count += 1
                if _severity_rank(sev) > _severity_rank(matched_node.risk_level):
                    matched_node.risk_level = sev

        penalty = critical_count * 25 + high_count * 12 + medium_count * 5 + low_count * 2
        security_score = round(max(0.0, 100.0 - penalty), 1)

        ordered_nodes = sorted(
            nodes_map.values(),
            key=lambda n: (_LAYER_ORDER.index(n.layer) if n.layer in _LAYER_ORDER else 99, n.id),
        )
        layers_present = [layer for layer in _LAYER_ORDER if any(n.layer == layer for n in ordered_nodes)]

        blast_radius = {
            "total_nodes": len(ordered_nodes),
            "iac_resources": len(iac_ids),
            "total_edges": len(edges),
            "findings_overlaid": len(findings_list),
            "critical_nodes": [n.id for n in ordered_nodes if n.risk_level == "critical"],
            "high_risk_nodes": [n.id for n in ordered_nodes if n.risk_level == "high"],
            "layers": layers_present,
        }

        mermaid = self._render_mermaid(ordered_nodes, edges, layers_present)
        dot = self._render_dot(title, ordered_nodes, edges)
        ascii_summary = self._render_ascii(title, ordered_nodes, edges, security_score)

        return DevSecOpsGraph(
            title=title,
            cloud=cloud,
            nodes=ordered_nodes,
            edges=edges,
            layers=layers_present,
            security_score=security_score,
            blast_radius_summary=blast_radius,
            mermaid=mermaid,
            dot=dot,
            ascii_summary=ascii_summary,
        )

    def build_from_directory(
        self,
        target_dir: Path,
        title: str | None = None,
        cloud: str = "multi",
        findings: list[dict[str, Any]] | None = None,
    ) -> DevSecOpsGraph:
        hcl_files: dict[str, str] = {}
        if target_dir.exists():
            for tf_file in sorted(target_dir.rglob("*.tf")):
                if ".terraform" in tf_file.parts or ".venv" in tf_file.parts:
                    continue
                rel = str(tf_file.relative_to(target_dir))
                hcl_files[rel] = tf_file.read_text(encoding="utf-8", errors="ignore")
        return self.build_from_hcl_files(
            title=title or f"DevSecOps Graph ({target_dir.name})",
            cloud=cloud,
            hcl_files=hcl_files,
            findings=findings,
            include_devsecops_pipeline=True,
        )

    @staticmethod
    def _render_mermaid(nodes: list[GraphNode], edges: list[GraphEdge], layers: list[str]) -> str:
        lines = ["flowchart LR"]
        lines.append("  classDef ok fill:#0f2922,stroke:#22c55e,color:#e6f4ea;")
        lines.append("  classDef low fill:#17253a,stroke:#38bdf8,color:#e0f2fe;")
        lines.append("  classDef medium fill:#33260f,stroke:#f59e0b,color:#fef3c7;")
        lines.append("  classDef high fill:#3b1818,stroke:#f97316,color:#ffedd5;")
        lines.append("  classDef critical fill:#450a0a,stroke:#ef4444,color:#fee2e2,stroke-width:2px;")

        for layer in layers:
            layer_nodes = [n for n in nodes if n.layer == layer]
            if not layer_nodes:
                continue
            lines.append(f'  subgraph layer_{layer}["{layer.upper()}"]')
            for node in layer_nodes:
                lbl = node.label.replace('"', "'").replace("\n", " - ")
                if node.findings_count > 0:
                    lbl = f"{lbl} [{node.findings_count} findings]"
                lines.append(f'    {node.id}["{lbl}"]:::{node.risk_level}')
            lines.append("  end")

        for edge in edges:
            rel = edge.relation.replace('"', "'")
            lines.append(f'  {edge.source} -->|"{rel}"| {edge.target}')

        return "\n".join(lines)

    @staticmethod
    def _render_dot(title: str, nodes: list[GraphNode], edges: list[GraphEdge]) -> str:
        color_map = {
            "ok": "#22c55e",
            "low": "#38bdf8",
            "medium": "#f59e0b",
            "high": "#f97316",
            "critical": "#ef4444",
        }
        lines = [
            f'digraph "{title.replace(chr(34), "")}" {{',
            '  rankdir=LR;',
            '  node [shape=box, style="rounded,filled", fillcolor="#111827", fontcolor="#f3f4f6", fontname="IBM Plex Mono"];',
            '  edge [color="#64748b", fontcolor="#94a3b8", fontsize=9];',
        ]
        for n in nodes:
            col = color_map.get(n.risk_level, "#22c55e")
            lbl = n.label.replace('"', "'").replace("\n", "\\n")
            lines.append(f'  {n.id} [label="{lbl}", color="{col}"];')
        for e in edges:
            lines.append(f'  {e.source} -> {e.target} [label="{e.relation}"];')
        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _render_ascii(title: str, nodes: list[GraphNode], edges: list[GraphEdge], score: float) -> str:
        lines = [f"=== {title} (Security Score: {score}/100) ==="]
        for layer in _LAYER_ORDER:
            layer_nodes = [n for n in nodes if n.layer == layer]
            if not layer_nodes:
                continue
            items = ", ".join(
                f"{n.id}[{n.risk_level.upper()}]" for n in layer_nodes
            )
            lines.append(f"  [{layer.upper():<13}] {items}")
        lines.append(f"  Edges ({len(edges)}):")
        for e in edges[:12]:
            lines.append(f"    {e.source} --({e.relation})--> {e.target}")
        if len(edges) > 12:
            lines.append(f"    ... +{len(edges) - 12} more edges")
        return "\n".join(lines)
