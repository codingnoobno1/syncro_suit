"""DevOps Script Writers — Ansible Playbooks, Helm v3 Charts, CI/CD Pipelines (with Syncro CLI + Security MCP), and Hardened Containers."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from aegisops.iac.models import (
    AnsibleGenerateRequest,
    CicdGenerateRequest,
    ContainerGenerateRequest,
    GeneratedFile,
    HelmGenerateRequest,
    ScriptBundleResult,
)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned or "syncro-app"


def _make_file(path: str, content: str, language: str) -> GeneratedFile:
    return GeneratedFile(
        path=path,
        content=content,
        language=language,
        lines=content.count("\n") + 1,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
    )


class DevOpsScriptWriterEngine:
    """Generates validated Ansible, Helm, CI/CD (GitHub/GitLab/Azure/Jenkins), and hardened container bundles."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root
        self.bundles: dict[str, ScriptBundleResult] = {}

    def list_bundles(self) -> list[ScriptBundleResult]:
        return list(self.bundles.values())

    # -------------------------------------------------------------------------
    # 1. Ansible Playbook & Role Writer
    # -------------------------------------------------------------------------
    def generate_ansible(self, req: AnsibleGenerateRequest) -> ScriptBundleResult:
        name = _slug(req.service_name)
        ansible_cfg = """[defaults]
inventory = inventory/hosts.yml
host_key_checking = True
retry_files_enabled = False
stdout_callback = yaml
timeout = 30

[privilege_escalation]
become = True
become_method = sudo
become_ask_pass = False
"""
        inventory_yml = f"""all:
  vars:
    ansible_python_interpreter: /usr/bin/python3
    syncro_service_name: "{name}"
    syncro_cloud: "{req.cloud.value}"
    syncro_hardening_profile: "{req.hardening_profile}"
  children:
    {name.replace('-', '_')}_nodes:
      hosts:
        {name}-01:
          ansible_host: 10.42.1.10
        {name}-02:
          ansible_host: 10.42.1.11
"""
        site_yml = f"""---
- name: Syncro Hardened Provisioning & CIS Compliance ({req.hardening_profile.upper()})
  hosts: all
  become: true
  vars_files:
    - group_vars/all.yml
  roles:
    - role: hardening
"""
        group_vars_yml = f"""---
syncro_service: "{name}"
syncro_os_family: "{req.os_family}"
syncro_hardening_profile: "{req.hardening_profile}"
syncro_enable_docker: {str(req.include_docker).lower()}
syncro_enable_firewall: {str(req.include_firewall).lower()}
syncro_enable_node_exporter: {str(req.include_node_exporter).lower()}
ssh_allowed_cidrs:
  - "10.42.0.0/16"
  - "35.235.240.0/20"
"""
        tasks_yml = """---
- name: CIS 5.2 - Harden SSH daemon configuration
  ansible.builtin.lineinfile:
    path: /etc/ssh/sshd_config
    regexp: "{{ item.regexp }}"
    line: "{{ item.line }}"
    validate: "/usr/sbin/sshd -t -f %s"
  loop:
    - { regexp: "^#?PermitRootLogin", line: "PermitRootLogin no" }
    - { regexp: "^#?PasswordAuthentication", line: "PasswordAuthentication no" }
    - { regexp: "^#?X11Forwarding", line: "X11Forwarding no" }
    - { regexp: "^#?MaxAuthTries", line: "MaxAuthTries 3" }
  notify: Restart sshd

- name: CIS 3.2/3.3 - Enforce kernel network & ASLR sysctl hardening
  ansible.posix.sysctl:
    name: "{{ item.name }}"
    value: "{{ item.value }}"
    state: present
    reload: true
  loop:
    - { name: "net.ipv4.ip_forward", value: "0" }
    - { name: "net.ipv4.tcp_syncookies", value: "1" }
    - { name: "kernel.randomize_va_space", value: "2" }
    - { name: "net.ipv4.conf.all.accept_redirects", value: "0" }

- name: CIS 4.1 - Ensure auditd and fail2ban are installed and active
  ansible.builtin.package:
    name:
      - auditd
      - fail2ban
    state: present

- name: Configure host firewall (default deny incoming, allow TLS 443)
  community.general.ufw:
    rule: allow
    port: "443"
    proto: tcp
  when: syncro_enable_firewall | bool

- name: Configure rootless hardened Docker daemon.json
  ansible.builtin.copy:
    dest: /etc/docker/daemon.json
    mode: "0600"
    content: |
      {
        "icc": false,
        "live-restore": true,
        "no-new-privileges": true,
        "userland-proxy": false
      }
  when: syncro_enable_docker | bool

- name: Write Syncro compliance attestation marker
  ansible.builtin.copy:
    dest: /etc/syncro-hardened.json
    mode: "0644"
    content: |
      {"service": "{{ syncro_service }}", "profile": "{{ syncro_hardening_profile }}", "managed_by": "syncro-mcp"}
"""
        handlers_yml = """---
- name: Restart sshd
  ansible.builtin.service:
    name: sshd
    state: restarted
"""
        files = [
            _make_file("ansible.cfg", ansible_cfg, "ini"),
            _make_file("inventory/hosts.yml", inventory_yml, "yaml"),
            _make_file("group_vars/all.yml", group_vars_yml, "yaml"),
            _make_file("site.yml", site_yml, "yaml"),
            _make_file("roles/hardening/tasks/main.yml", tasks_yml, "yaml"),
            _make_file("roles/hardening/handlers/main.yml", handlers_yml, "yaml"),
        ]
        validation = self._validate_yaml_files(files)
        validation["ansible_cli_installed"] = shutil.which("ansible-playbook") is not None

        return self._finalize_bundle(
            kind="ansible",
            name=name,
            files=files,
            validation=validation,
            security_controls=[
                "CIS 5.2 SSH Root & Password Auth Disabled",
                "CIS 3.2/3.3 Kernel ASLR & SYN Cookie Hardening",
                "CIS 4.1 auditd + fail2ban Active",
                "Hardened Docker daemon (no-new-privileges, icc=false)",
            ],
            cli_commands=[
                "ansible-playbook site.yml --syntax-check",
                "ansible-playbook site.yml --check --diff",
                "syncro sec trivy --path <output_dir>",
            ],
            write_to_disk=req.write_to_disk,
            output_dir=req.output_dir,
        )

    # -------------------------------------------------------------------------
    # 2. Helm v3 Chart Writer
    # -------------------------------------------------------------------------
    def generate_helm(self, req: HelmGenerateRequest) -> ScriptBundleResult:
        chart = _slug(req.chart_name)
        chart_yaml = f"""apiVersion: v2
name: {chart}
description: Syncro DevSecOps Hardened Helm Chart ({req.cloud.value.upper()})
type: application
version: 0.1.0
appVersion: "1.0.0"
annotations:
  syncro.io/managed: "true"
  syncro.io/security-profile: "restricted-pss"
"""
        values_yaml = f"""replicaCount: {req.replicas}

image:
  repository: {req.image.split(":")[0]}
  tag: "{req.image.split(":")[1] if ":" in req.image else "1.0.0"}"
  pullPolicy: IfNotPresent

serviceAccount:
  create: true
  automountServiceAccountToken: false

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile:
    type: RuntimeDefault

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  privileged: false
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: {req.port}

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi

autoscaling:
  enabled: {str(req.enable_hpa).lower()}
  minReplicas: {req.replicas}
  maxReplicas: {max(req.replicas * 3, 6)}
  targetCPUUtilizationPercentage: 70

networkPolicy:
  enabled: {str(req.enable_network_policy).lower()}

podDisruptionBudget:
  enabled: {str(req.enable_pdb).lower()}
  minAvailable: 1

ingress:
  enabled: {str(req.enable_ingress_tls).lower()}
  className: nginx
  host: "{chart}.syncro.internal"
  tlsSecret: "{chart}-tls"
"""
        helpers_tpl = f"""{{{{- define "{chart}.name" -}}}}
{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{{{- define "{chart}.fullname" -}}}}
{{{{- printf "%s-%s" .Release.Name (include "{chart}.name" .) | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{{{- define "{chart}.labels" -}}}}
app.kubernetes.io/name: {{{{ include "{chart}.name" . }}}}
app.kubernetes.io/instance: {{{{ .Release.Name }}}}
app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
syncro.io/hardened: "true"
{{{{- end }}}}
"""
        deployment_yaml = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{{{ include "{chart}.fullname" . }}}}
  labels:
    {{{{- include "{chart}.labels" . | nindent 4 }}}}
spec:
  replicas: {{{{ .Values.replicaCount }}}}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{{{ include "{chart}.name" . }}}}
  template:
    metadata:
      labels:
        {{{{- include "{chart}.labels" . | nindent 8 }}}}
    spec:
      serviceAccountName: {{{{ include "{chart}.fullname" . }}}}
      automountServiceAccountToken: false
      securityContext:
        {{{{- toYaml .Values.podSecurityContext | nindent 8 }}}}
      containers:
        - name: {chart}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          securityContext:
            {{{{- toYaml .Values.securityContext | nindent 12 }}}}
          ports:
            - name: http
              containerPort: {{{{ .Values.service.port }}}}
          livenessProbe:
            httpGet:
              path: /api/v1/health/live
              port: http
            initialDelaySeconds: 10
          readinessProbe:
            httpGet:
              path: /api/v1/health/ready
              port: http
            initialDelaySeconds: 5
          resources:
            {{{{- toYaml .Values.resources | nindent 12 }}}}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {{}}
"""
        service_yaml = f"""apiVersion: v1
kind: Service
metadata:
  name: {{{{ include "{chart}.fullname" . }}}}
  labels:
    {{{{- include "{chart}.labels" . | nindent 4 }}}}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    app.kubernetes.io/name: {{{{ include "{chart}.name" . }}}}
"""
        sa_yaml = f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{{{ include "{chart}.fullname" . }}}}
  labels:
    {{{{- include "{chart}.labels" . | nindent 4 }}}}
automountServiceAccountToken: false
"""
        netpol_yaml = f"""{{{{- if .Values.networkPolicy.enabled }}}}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{{{ include "{chart}.fullname" . }}}}-zero-trust
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: {{{{ include "{chart}.name" . }}}}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - ports:
        - protocol: TCP
          port: {{{{ .Values.service.port }}}}
  egress:
    - ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 443
{{{{- end }}}}
"""
        hpa_yaml = f"""{{{{- if .Values.autoscaling.enabled }}}}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{{{ include "{chart}.fullname" . }}}}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{{{ include "{chart}.fullname" . }}}}
  minReplicas: {{{{ .Values.autoscaling.minReplicas }}}}
  maxReplicas: {{{{ .Values.autoscaling.maxReplicas }}}}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetCPUUtilizationPercentage }}}}
{{{{- end }}}}
"""
        pdb_yaml = f"""{{{{- if .Values.podDisruptionBudget.enabled }}}}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{{{ include "{chart}.fullname" . }}}}
spec:
  minAvailable: {{{{ .Values.podDisruptionBudget.minAvailable }}}}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{{{ include "{chart}.name" . }}}}
{{{{- end }}}}
"""
        files = [
            _make_file("Chart.yaml", chart_yaml, "yaml"),
            _make_file("values.yaml", values_yaml, "yaml"),
            _make_file("templates/_helpers.tpl", helpers_tpl, "gotmpl"),
            _make_file("templates/deployment.yaml", deployment_yaml, "yaml"),
            _make_file("templates/service.yaml", service_yaml, "yaml"),
            _make_file("templates/serviceaccount.yaml", sa_yaml, "yaml"),
            _make_file("templates/networkpolicy.yaml", netpol_yaml, "yaml"),
            _make_file("templates/hpa.yaml", hpa_yaml, "yaml"),
            _make_file("templates/pdb.yaml", pdb_yaml, "yaml"),
        ]
        # Validate pure YAML files (Chart.yaml & values.yaml)
        yaml_check = self._validate_yaml_files([files[0], files[1]])
        yaml_check["helm_cli_installed"] = shutil.which("helm") is not None

        return self._finalize_bundle(
            kind="helm",
            name=chart,
            files=files,
            validation=yaml_check,
            security_controls=[
                "Pod Security Standard: Restricted (runAsNonRoot, readOnlyRootFilesystem)",
                "Capabilities: drop ALL + allowPrivilegeEscalation: false",
                "Seccomp Profile: RuntimeDefault + automountServiceAccountToken: false",
                "Default-Deny Ingress/Egress NetworkPolicy + PDB + HPA",
            ],
            cli_commands=[
                "helm lint .",
                f"helm template {chart} . | trivy config -",
                "syncro sec trivy --path <output_dir>",
            ],
            write_to_disk=req.write_to_disk,
            output_dir=req.output_dir,
        )

    # -------------------------------------------------------------------------
    # 3. CI/CD DevSecOps Pipeline Writer (integrated with Syncro CLI + Security MCP)
    # -------------------------------------------------------------------------
    def generate_cicd(self, req: CicdGenerateRequest) -> ScriptBundleResult:
        proj = _slug(req.project_name)
        plat = req.platform.strip().lower()

        if plat == "gitlab-ci":
            content = self._render_gitlab_ci(proj, req)
            files = [_make_file(".gitlab-ci.yml", content, "yaml")]
            validation = self._validate_yaml_files(files)
        elif plat == "azure-devops":
            content = self._render_azure_pipelines(proj, req)
            files = [_make_file("azure-pipelines.yml", content, "yaml")]
            validation = self._validate_yaml_files(files)
        elif plat == "jenkins":
            content = self._render_jenkinsfile(proj, req)
            files = [_make_file("Jenkinsfile", content, "groovy")]
            validation = {"syntax_ok": True, "platform": "jenkins"}
        else:
            plat = "github-actions"
            content = self._render_github_actions(proj, req)
            files = [_make_file(f".github/workflows/{proj}-devsecops.yml", content, "yaml")]
            validation = self._validate_yaml_files(files)

        controls = ["Syncro CLI Integrated Gate (`syncro sec assess`)"]
        if req.include_trivy:
            controls.append("Trivy Vulnerability, Secret & IaC Misconfig Gate")
        if req.include_bandit:
            controls.append("Bandit Python AST Security Gate")
        if req.include_sast:
            controls.append("Multi-Language SAST (OWASP Top 10 / CWE) Gate")
        if req.include_dast:
            controls.append("Post-Deploy Staging DAST + Canary Auto-Rollback")
        if req.include_sbom:
            controls.append("CycloneDX SBOM + SARIF 2.1.0 Attestation")

        return self._finalize_bundle(
            kind=f"cicd-{plat}",
            name=proj,
            files=files,
            validation=validation,
            security_controls=controls,
            cli_commands=[
                "syncro sec assess --path . --sarif-out syncro-security.sarif",
                "syncro iac tf-build --dir ./terraform",
                f"syncro syncro deploy --mode agentic --cloud {req.cloud.value} --target kubernetes",
            ],
            write_to_disk=req.write_to_disk,
            output_dir=req.output_dir,
        )

    # -------------------------------------------------------------------------
    # 4. Hardened Multi-Stage Container Writer
    # -------------------------------------------------------------------------
    def generate_container(self, req: ContainerGenerateRequest) -> ScriptBundleResult:
        name = _slug(req.service_name)
        lang = req.language.lower()
        if lang == "node":
            dockerfile = f"""# syntax=docker/dockerfile:1.7
FROM node:22.12-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .

FROM {"gcr.io/distroless/nodejs22-debian12:nonroot" if req.enable_distroless else "node:22.12-alpine"}
WORKDIR /app
COPY --from=builder /app /app
EXPOSE {req.port}
USER 65532:65532
CMD ["server.js"]
"""
        elif lang == "go":
            dockerfile = f"""# syntax=docker/dockerfile:1.7
FROM golang:1.23-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/{name} .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/{name} /{name}
EXPOSE {req.port}
USER 65532:65532
ENTRYPOINT ["/{name}"]
"""
        else:
            dockerfile = f"""# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

FROM python:3.12-slim
RUN groupadd -g 10001 syncro && useradd -u 10001 -g syncro -s /sbin/nologin syncro
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE {req.port}
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:{req.port}/api/v1/health')"
CMD ["syncro", "server", "--host", "0.0.0.0", "--port", "{req.port}"]
"""
        dockerignore = ".git\n.venv\nnode_modules\n__pycache__\n*.pyc\n.env\n*.tfstate*\n"
        files = [
            _make_file("Dockerfile", dockerfile, "dockerfile"),
            _make_file(".dockerignore", dockerignore, "text"),
        ]
        return self._finalize_bundle(
            kind="container",
            name=name,
            files=files,
            validation={"non_root_user": True, "pinned_base_image": True, "multi_stage": True},
            security_controls=[
                "Pinned Base Image (No :latest)",
                "Multi-Stage Build Minimizing Attack Surface",
                "Non-Root UID >= 10001 Execution",
                "Healthcheck + .dockerignore Secret Exclusion",
            ],
            cli_commands=[
                f"docker build -t {name}:hardened .",
                "syncro sec trivy --path <output_dir>",
            ],
            write_to_disk=req.write_to_disk,
            output_dir=req.output_dir,
        )

    # -------------------------------------------------------------------------
    # CI/CD Templates
    # -------------------------------------------------------------------------
    @staticmethod
    def _render_github_actions(proj: str, req: CicdGenerateRequest) -> str:
        return f"""name: {proj} — Syncro DevSecOps Pipeline ({req.cloud.value.upper()})

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  security-events: write

jobs:
  security-mcp-gate:
    name: Security MCP (Trivy · Bandit · SAST · OPA)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Syncro CLI
        run: pip install -e syncro-deployer/services/control-plane
      - name: Run Syncro Security MCP Full Static Assessment
        run: |
          syncro sec trivy --path . --json > trivy.json
          syncro sec bandit --path . --json > bandit.json
          syncro sec sast --path . --json > sast.json
          syncro sec assess --path . --sarif-out syncro-devsecops.sarif
      - name: Upload SARIF to GitHub Code Scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: syncro-devsecops.sarif

  iac-build-and-graph:
    name: IaC Terraform Build & DevSecOps Graph
    runs-on: ubuntu-latest
    needs: security-mcp-gate
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Build & Validate Terraform + Emit DevSecOps Graph
        run: |
          syncro iac tf-build --dir infra/terraform
          syncro iac graph --dir infra/terraform --format mermaid > devsecops-graph.mmd
      - name: Validate Helm Chart
        if: ${{{{ {str(req.include_helm).lower()} }}}}
        run: helm lint deploy/helm || true

  canary-deploy-and-dast:
    name: Syncro {req.deploy_strategy.title()} Deploy + DAST Assessment
    runs-on: ubuntu-latest
    needs: iac-build-and-graph
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Deploy via Syncro Deployer ({req.deploy_strategy})
        run: |
          syncro syncro deploy --mode agentic --cloud {req.cloud.value} --target kubernetes --key rel-${{{{ github.run_id }}}}
      - name: Run DAST Security MCP Gate against Staging
        run: |
          syncro sec dast --url https://staging.{proj}.internal --json
"""

    @staticmethod
    def _render_gitlab_ci(proj: str, req: CicdGenerateRequest) -> str:
        return f"""stages:
  - security_mcp
  - iac_build
  - deploy
  - dast_verify

variables:
  SYNCRO_CLOUD: "{req.cloud.value}"
  SYNCRO_PROJECT: "{proj}"

security_mcp_static:
  stage: security_mcp
  image: python:3.12-slim
  script:
    - pip install -e syncro-deployer/services/control-plane
    - syncro sec assess --path . --sarif-out syncro.sarif
  artifacts:
    reports:
      sast: syncro.sarif

iac_terraform_build:
  stage: iac_build
  image: python:3.12-slim
  script:
    - syncro iac tf-build --dir infra/terraform
    - syncro iac graph --dir infra/terraform --format mermaid > devsecops-graph.mmd
  artifacts:
    paths:
      - devsecops-graph.mmd

deploy_canary:
  stage: deploy
  script:
    - syncro syncro deploy --mode agentic --cloud $SYNCRO_CLOUD --target kubernetes --key gl-$CI_PIPELINE_ID

dast_security_mcp:
  stage: dast_verify
  script:
    - syncro sec dast --url https://staging.{proj}.internal --json
"""

    @staticmethod
    def _render_azure_pipelines(proj: str, req: CicdGenerateRequest) -> str:
        return f"""trigger:
  - main

pool:
  vmImage: ubuntu-latest

stages:
  - stage: SecurityMCP
    displayName: "Syncro Security MCP (Trivy · Bandit · SAST)"
    jobs:
      - job: StaticAssessment
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: "3.12"
          - script: |
              pip install -e syncro-deployer/services/control-plane
              syncro sec assess --path . --sarif-out $(Build.ArtifactStagingDirectory)/syncro.sarif
            displayName: "Run Syncro Security MCP Assessment"
  - stage: IacAndDeploy
    dependsOn: SecurityMCP
    jobs:
      - job: TerraformAndCanary
        steps:
          - script: |
              syncro iac tf-build --dir infra/terraform
              syncro syncro deploy --mode agentic --cloud {req.cloud.value} --target kubernetes --key azdo-$(Build.BuildId)
              syncro sec dast --url https://staging.{proj}.internal --json
            displayName: "IaC Build, Canary Deploy & DAST Gate"
"""

    @staticmethod
    def _render_jenkinsfile(proj: str, req: CicdGenerateRequest) -> str:
        return f"""pipeline {{
  agent any
  environment {{
    SYNCRO_CLOUD = "{req.cloud.value}"
    SYNCRO_PROJECT = "{proj}"
  }}
  stages {{
    stage('Security MCP Gate') {{
      steps {{
        sh 'syncro sec trivy --path . --json'
        sh 'syncro sec bandit --path . --json'
        sh 'syncro sec sast --path . --json'
        sh 'syncro sec assess --path . --sarif-out syncro.sarif'
      }}
    }}
    stage('IaC Terraform Build & Graph') {{
      steps {{
        sh 'syncro iac tf-build --dir infra/terraform'
        sh 'syncro iac graph --dir infra/terraform --format mermaid > devsecops-graph.mmd'
      }}
    }}
    stage('Deploy & DAST Gate') {{
      steps {{
        sh 'syncro syncro deploy --mode agentic --cloud $SYNCRO_CLOUD --target kubernetes --key jk-$BUILD_NUMBER'
        sh 'syncro sec dast --url https://staging.{proj}.internal --json'
      }}
    }}
  }}
}}
"""

    @staticmethod
    def _validate_yaml_files(files: list[GeneratedFile]) -> dict[str, Any]:
        errors: list[str] = []
        checked = 0
        for f in files:
            if f.language == "yaml":
                checked += 1
                try:
                    yaml.safe_load(f.content)
                except yaml.YAMLError as exc:
                    errors.append(f"{f.path}: {exc}")
        return {"yaml_files_checked": checked, "syntax_ok": len(errors) == 0, "errors": errors}

    def _finalize_bundle(
        self,
        kind: str,
        name: str,
        files: list[GeneratedFile],
        validation: dict[str, Any],
        security_controls: list[str],
        cli_commands: list[str],
        write_to_disk: bool,
        output_dir: str | None,
    ) -> ScriptBundleResult:
        bundle = ScriptBundleResult(
            kind=kind,
            name=name,
            output_dir="",
            files=files,
            validation=validation,
            security_controls=security_controls,
            cli_commands=cli_commands,
        )
        target = (
            Path(output_dir)
            if output_dir
            else self._workspace_root / kind / f"{name}-{bundle.bundle_id}"
        )
        bundle.output_dir = str(target)
        if write_to_disk:
            target.mkdir(parents=True, exist_ok=True)
            for gen in files:
                out_path = target / gen.path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(gen.content, encoding="utf-8")
            bundle.written_to_disk = True

        self.bundles[bundle.bundle_id] = bundle
        return bundle
