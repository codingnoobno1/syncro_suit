import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/config/agent_config.dart';
import '../core/resilience/retry_client.dart';
import '../models/syncro_models.dart';
import '../services/local_agent_bridge.dart';
import '../services/syncro_api_client.dart';

/// Central state controller for the Syncro Desktop Flutter Agent.
///
/// Orchestrates dual-mode execution (Agentic Mode vs Manual DevOps Mode),
/// 7-module Syncro Suite navigation, native workstation probing, resilient
/// API + WebSocket telemetry, and deterministic local fallback when offline.
class SyncroController extends ChangeNotifier {
  SyncroController({
    AgentConfig? config,
    SyncroApiClient? apiClient,
    LocalAgentBridge? localBridge,
    this.startBackgroundTimers = true,
  })  : config = config ?? const AgentConfig(),
        _api = apiClient ?? SyncroApiClient(config: config ?? const AgentConfig()),
        _bridge = localBridge ?? LocalAgentBridge() {
    _suiteModules = _defaultSuiteModules();
    _deployments = _seedInitialDeployments();
    _bill = const BillSummary(
      forecastEomUsd: 18165.03,
      userTargetCapUsd: 9500.0,
      hardBudgetCapUsd: 22000.0,
      identifiableSavingsUsd: 5420.0,
      egressMonthlyUsd: 1640.0,
      spendByCloud: <String, double>{
        'aws': 7420.15,
        'gcp': 5890.44,
        'azure': 4854.44,
      },
    );
    _resilienceHealth = <String, dynamic>{
      'journal': <String, dynamic>{
        'engine': 'sqlite-wal',
        'deployments_persisted': _deployments.length,
        'agents_persisted': 1,
      },
      'circuit_breakers': <String, dynamic>{
        'cloud-provisioner': <String, dynamic>{'state': 'closed', 'failures': 0},
        'k8s-rollout': <String, dynamic>{'state': 'closed', 'failures': 0},
        'docker-runtime': <String, dynamic>{'state': 'closed', 'failures': 0},
      },
      'online_desktop_agents': 1,
    };
    _appendEvent('Syncro Desktop Agent booted (${this.config.agentId}) — mode: AGENTIC');
  }

  final AgentConfig config;
  final SyncroApiClient _api;
  final LocalAgentBridge _bridge;
  final bool startBackgroundTimers;

  SyncroMode _mode = SyncroMode.agentic;
  String _selectedModuleId = 'syncro-deployer';
  int _activeTabIndex = 0; // 0 = Mode Workbench, 1 = Pipelines, 2 = Agent & Suite
  bool _connected = false;
  bool _busy = false;
  String? _lastError;
  late List<SyncroSuiteModule> _suiteModules;
  late List<SyncroDeployment> _deployments;
  late BillSummary _bill;
  late Map<String, dynamic> _resilienceHealth;
  DesktopAgentProbe? _localProbe;
  String? _lastPromptOutput;
  String? _lastSelfPromptOutput;
  final List<String> _eventFeed = <String>[];
  final Map<String, SyncroDeployment> _idempotencyCache = <String, SyncroDeployment>{};

  Timer? _heartbeatTimer;
  StreamSubscription<Map<String, dynamic>>? _wsSub;
  int _seq = 100;

  SyncroMode get mode => _mode;
  String get selectedModuleId => _selectedModuleId;
  int get activeTabIndex => _activeTabIndex;
  bool get connected => _connected;
  bool get busy => _busy;
  String? get lastError => _lastError;
  List<SyncroSuiteModule> get suiteModules => List.unmodifiable(_suiteModules);
  List<SyncroDeployment> get deployments => List.unmodifiable(_deployments);
  BillSummary get bill => _bill;
  Map<String, dynamic> get resilienceHealth => _resilienceHealth;
  DesktopAgentProbe? get localProbe => _localProbe;
  String? get lastPromptOutput => _lastPromptOutput;
  String? get lastSelfPromptOutput => _lastSelfPromptOutput;
  List<String> get eventFeed => List.unmodifiable(_eventFeed);
  BreakerState get clientBreakerState => _api.transport.breaker.state;

  Future<void> bootstrap() async {
    _busy = true;
    _lastError = null;
    notifyListeners();

    try {
      _localProbe = await _bridge.inspectWorkstation();
      _appendEvent(
        'LocalAgentBridge probed ${_localProbe!.osPlatform} (${_localProbe!.detectedTools.length} CLIs detected)',
      );
    } catch (_) {
      _localProbe = DesktopAgentProbe(
        hostname: 'syncro-workstation',
        osPlatform: 'linux',
        detectedTools: const <String>['git', 'docker', 'kubectl', 'terraform', 'syncro'],
        probedAt: DateTime.now().toUtc(),
      );
    }

    await syncFromControlPlane();

    if (startBackgroundTimers) {
      _startHeartbeatLoop();
      if (_connected) {
        _connectWebSocket();
      }
    }

    _busy = false;
    notifyListeners();
  }

  Future<void> syncFromControlPlane() async {
    try {
      final modules = await _api.fetchSuiteModules();
      final deps = await _api.listDeployments();
      final billSummary = await _api.fetchBill();
      final health = await _api.fetchResilienceHealth();

      if (modules.isNotEmpty) {
        _suiteModules = modules;
      }
      _deployments = deps.isNotEmpty ? deps : _deployments;
      _bill = billSummary;
      _resilienceHealth = health;
      _connected = true;
      _lastError = null;

      if (_localProbe != null) {
        await _api.registerAgent(_localProbe!, _mode);
      }
      _appendEvent('Connected to Syncro Control Plane at ${config.apiBaseUrl}');
    } catch (_) {
      _connected = false;
      _lastError = 'Offline local-resilience mode active (${config.apiBaseUrl} unreachable)';
      _appendEvent('Control plane unreachable — running deterministic local desktop simulation');
    }
    notifyListeners();
  }

  void selectSuiteModule(String moduleId) {
    _selectedModuleId = moduleId;
    if (moduleId == 'syncro-desktop') {
      _activeTabIndex = 2;
    } else if (moduleId == 'syncro-deployer') {
      _activeTabIndex = 0;
    } else if (moduleId == 'syncro-git' || moduleId == 'syncro-tester') {
      _activeTabIndex = 1;
    } else {
      _activeTabIndex = 2;
    }
    _appendEvent('Suite rail switched to $moduleId');
    notifyListeners();
  }

  void selectWorkbenchTab(int index) {
    _activeTabIndex = index;
    notifyListeners();
  }

  Future<void> setMode(SyncroMode nextMode) async {
    if (_mode == nextMode) {
      return;
    }
    _mode = nextMode;
    _activeTabIndex = 0;
    _appendEvent('Switched Syncro Deployer to ${nextMode.label.toUpperCase()}');
    notifyListeners();

    if (_connected) {
      try {
        await _api.setMode(nextMode);
      } catch (e) {
        _appendEvent('Mode sync queued locally: $e');
      }
    }
  }

  Future<SyncroDeployment> deploy({
    required String projectId,
    required String environmentName,
    required String cloud,
    required String targetType,
    required String strategy,
    required String idempotencyKey,
    SyncroMode? overrideMode,
    String vmSku = 'n2d-standard-4',
    String image = 'ghcr.io/aegisops/edge-gateway:1.5.0',
    bool simulateCanaryFault = false,
  }) async {
    final effectiveMode = overrideMode ?? _mode;
    final cleanKey = idempotencyKey.trim().isEmpty
        ? 'sync-${DateTime.now().millisecondsSinceEpoch}'
        : idempotencyKey.trim();

    _busy = true;
    _lastError = null;
    notifyListeners();

    try {
      SyncroDeployment result;
      if (_connected) {
        result = await _api.deploy(
          projectId: projectId,
          environmentName: environmentName,
          cloud: cloud,
          targetType: targetType,
          strategy: strategy,
          mode: effectiveMode,
          idempotencyKey: cleanKey,
          vmSku: vmSku,
          image: image,
          simulateCanaryFault: simulateCanaryFault,
        );
      } else {
        result = _simulateLocalDeploy(
          projectId: projectId,
          environmentName: environmentName,
          cloud: cloud,
          targetType: targetType,
          strategy: strategy,
          mode: effectiveMode,
          idempotencyKey: cleanKey,
          vmSku: vmSku,
          image: image,
          simulateCanaryFault: simulateCanaryFault,
        );
      }

      _upsertDeployment(result);
      _appendEvent(
        'Deploy ${result.id} [${effectiveMode.apiValue}] $cloud/$targetType -> ${result.stage}'
        '${result.idempotentReplay ? ' (IDEMPOTENT REPLAY)' : ''}'
        '${result.autoRolledBack ? ' (AUTO-ROLLED BACK)' : ''}',
      );
      return result;
    } catch (e) {
      _lastError = e.toString();
      _appendEvent('Deployment blocked or failed: $e');
      rethrow;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<SyncroDeployment?> promoteDeployment(String deploymentId) async {
    _busy = true;
    notifyListeners();

    try {
      SyncroDeployment? updated;
      if (_connected) {
        updated = await _api.promote(deploymentId);
      } else {
        final idx = _deployments.indexWhere((d) => d.id == deploymentId);
        if (idx >= 0) {
          final current = _deployments[idx];
          if (current.stage == 'canary_5') {
            updated = _copyDeployment(
              current,
              stage: 'canary_25',
              stablePct: 75,
              canaryPct: 25,
              checkpoint: const DeploymentCheckpoint(
                stage: 'canary_25',
                message: 'Manual operator promoted canary traffic to 25% (SLO verified)',
                trafficCanaryPct: 25,
                errorRatePct: 0.14,
              ),
            );
          } else if (current.stage == 'canary_25') {
            updated = _copyDeployment(
              current,
              stage: 'promoted_100',
              stablePct: 0,
              canaryPct: 100,
              checkpoint: const DeploymentCheckpoint(
                stage: 'promoted_100',
                message: 'Manual operator finalized 100% production cutover',
                trafficCanaryPct: 100,
                errorRatePct: 0.08,
              ),
            );
          } else {
            updated = current;
          }
        }
      }

      if (updated != null) {
        _upsertDeployment(updated);
        _appendEvent('Promoted ${updated.id} -> ${updated.stage} (${updated.canaryPct}% canary)');
      }
      return updated;
    } catch (e) {
      _lastError = e.toString();
      _appendEvent('Promote failed for $deploymentId: $e');
      return null;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<SyncroDeployment?> rollbackDeployment(
    String deploymentId, {
    String reason = 'Operator-triggered instant rollback via Syncro Desktop',
  }) async {
    _busy = true;
    notifyListeners();

    try {
      SyncroDeployment? updated;
      if (_connected) {
        updated = await _api.rollback(deploymentId, reason);
      } else {
        final idx = _deployments.indexWhere((d) => d.id == deploymentId);
        if (idx >= 0) {
          final current = _deployments[idx];
          updated = _copyDeployment(
            current,
            stage: 'rolled_back',
            stablePct: 100,
            canaryPct: 0,
            rollbackReason: reason,
            checkpoint: DeploymentCheckpoint(
              stage: 'rolled_back',
              message: 'Instant rollback restored 100% stable traffic: $reason',
              trafficCanaryPct: 0,
              errorRatePct: 0.0,
            ),
          );
        }
      }

      if (updated != null) {
        _upsertDeployment(updated);
        _appendEvent('Rolled back ${updated.id} -> 100% stable ($reason)');
      }
      return updated;
    } catch (e) {
      _lastError = e.toString();
      _appendEvent('Rollback failed for $deploymentId: $e');
      return null;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<void> runNaturalPrompt(String prompt) async {
    final trimmed = prompt.trim();
    if (trimmed.isEmpty) {
      return;
    }
    _busy = true;
    notifyListeners();

    try {
      if (_connected) {
        final resp = await _api.sendNaturalPrompt(trimmed);
        _lastPromptOutput = resp.toString();
      } else {
        final lower = trimmed.toLowerCase();
        final blocked = lower.contains('ignore previous') ||
            lower.contains('disable guardrail') ||
            lower.contains('bypass opa') ||
            lower.contains('privileged') ||
            lower.contains('0.0.0.0/0');
        if (blocked) {
          _lastPromptOutput =
              'BLOCKED BY GUARDRAIL FIREWALL [PROMPT-INJECTION / OPA-DENY]:\n'
              'Adversarial override or insecure policy bypass detected in prompt "$trimmed".\n'
              'Action denied; immutable CloudEvent logged to aegis.security.findings.';
        } else {
          _lastPromptOutput =
              'GUARDRAIL ALLOW [score=100/100 · mode=${_mode.apiValue}]:\n'
              'Directive accepted: "$trimmed"\n'
              '• Cloud selector matched Spot Confidential SKU (up to 68% savings)\n'
              '• Traffic policy: Canary Weighted 5%->25%->100% + Edge CDN Cache + KEDA Scale-to-Zero\n'
              '• Ready for autonomous execution within \$${_bill.hardBudgetCapUsd.toStringAsFixed(0)}/mo cap.';
        }
      }
      _appendEvent('MCP Bot evaluated prompt (${trimmed.length} chars)');
    } catch (e) {
      _lastPromptOutput = 'Guardrail engine returned error: $e';
      _appendEvent('MCP prompt error: $e');
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<void> runBillSaverSelfPrompt(String customDirective) async {
    _busy = true;
    notifyListeners();

    try {
      if (_connected) {
        final resp = await _api.runSelfPromptBillSaver(customDirective);
        _lastSelfPromptOutput =
            'Self-Prompt Executed: ${resp['summary'] ?? resp.toString()}';
      } else {
        final directive = customDirective.trim().isEmpty
            ? 'Cut monthly spend below \$${_bill.userTargetCapUsd.toStringAsFixed(0)} using Spot VMs, KEDA scale-to-zero, and CDN egress offload.'
            : customDirective.trim();
        _lastSelfPromptOutput =
            'USER BILL-SAVING SELF-PROMPT INJECTED & EVALUATED:\n'
            'Directive: "$directive"\n'
            '1. Migrate non-prod AWS/GCP/Azure nodes to Spot + Graviton/EPYC -> -\$2,840/mo\n'
            '2. Enable KEDA Scale-to-Zero on preview namespaces -> -\$1,420/mo\n'
            '3. Route egress through Edge CDN + VPC Endpoints -> -\$1,160/mo\n'
            'Projected Post-Optimization Bill: \$${(_bill.forecastEomUsd - _bill.identifiableSavingsUsd).toStringAsFixed(2)}/mo '
            '(identifiable savings: \$${_bill.identifiableSavingsUsd.toStringAsFixed(2)}/mo).';
      }
      _appendEvent('Executed user-defined Bill-Saving Self-Prompt');
    } catch (e) {
      _lastSelfPromptOutput = 'Self-prompt run failed: $e';
      _appendEvent('Bill-saver self-prompt error: $e');
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<void> refreshLocalProbe() async {
    _localProbe = await _bridge.inspectWorkstation();
    _appendEvent(
      'Workstation re-probed: ${_localProbe!.detectedTools.length} DevOps CLIs available',
    );
    if (_connected && _localProbe != null) {
      try {
        await _api.sendHeartbeat(_localProbe!, _mode);
        _appendEvent('Heartbeat ACK received from Syncro Control Plane');
      } catch (e) {
        _appendEvent('Heartbeat warning: $e');
      }
    }
    notifyListeners();
  }

  SyncroDeployment _simulateLocalDeploy({
    required String projectId,
    required String environmentName,
    required String cloud,
    required String targetType,
    required String strategy,
    required SyncroMode mode,
    required String idempotencyKey,
    required String vmSku,
    required String image,
    required bool simulateCanaryFault,
  }) {
    final existing = _idempotencyCache[idempotencyKey];
    if (existing != null) {
      return SyncroDeployment(
        id: existing.id,
        projectId: existing.projectId,
        environmentName: existing.environmentName,
        cloud: existing.cloud,
        targetType: existing.targetType,
        strategy: existing.strategy,
        mode: existing.mode,
        stage: existing.stage,
        stablePct: existing.stablePct,
        canaryPct: existing.canaryPct,
        autoRolledBack: existing.autoRolledBack,
        idempotentReplay: true,
        rollbackReason: existing.rollbackReason,
        vmSku: existing.vmSku,
        image: existing.image,
        checkpoints: existing.checkpoints,
      );
    }

    _seq += 1;
    final id = 'sync-local-$_seq';
    final checkpoints = <DeploymentCheckpoint>[
      const DeploymentCheckpoint(
        stage: 'planned',
        message: 'Deployment plan registered in SQLite WAL journal + Redis lock acquired',
        trafficCanaryPct: 0,
        errorRatePct: 0.0,
      ),
      const DeploymentCheckpoint(
        stage: 'preflight_passed',
        message: 'Checkov / Trivy / OPA Guardrails passed (score 100/100)',
        trafficCanaryPct: 0,
        errorRatePct: 0.0,
      ),
    ];

    late SyncroDeployment dep;
    if (simulateCanaryFault) {
      checkpoints.addAll(const <DeploymentCheckpoint>[
        DeploymentCheckpoint(
          stage: 'canary_5',
          message: 'SLO BREACH at 5% canary: HTTP 5xx error rate 6.40% > 2.00% threshold',
          trafficCanaryPct: 5,
          errorRatePct: 6.4,
        ),
        DeploymentCheckpoint(
          stage: 'rolled_back',
          message: 'Automatic rollback restored 100% traffic to rev-1.4.2-stable',
          trafficCanaryPct: 0,
          errorRatePct: 0.0,
        ),
      ]);
      dep = SyncroDeployment(
        id: id,
        projectId: projectId,
        environmentName: environmentName,
        cloud: cloud,
        targetType: targetType,
        strategy: strategy,
        mode: mode,
        stage: 'rolled_back',
        stablePct: 100,
        canaryPct: 0,
        autoRolledBack: true,
        idempotentReplay: false,
        rollbackReason: 'Canary 5xx error rate 6.40% exceeded 2.00% SLO threshold',
        vmSku: vmSku,
        image: image,
        checkpoints: checkpoints,
      );
    } else if (mode == SyncroMode.agentic) {
      checkpoints.addAll(const <DeploymentCheckpoint>[
        DeploymentCheckpoint(
          stage: 'canary_5',
          message: 'Agentic canary shifted 5% traffic — p99 17.4ms, errors 0.12%',
          trafficCanaryPct: 5,
          errorRatePct: 0.12,
        ),
        DeploymentCheckpoint(
          stage: 'canary_25',
          message: 'Agentic autopilot promoted canary to 25% — SLO healthy',
          trafficCanaryPct: 25,
          errorRatePct: 0.09,
        ),
        DeploymentCheckpoint(
          stage: 'promoted_100',
          message: 'Agentic rollout promoted 100% production traffic autonomously',
          trafficCanaryPct: 100,
          errorRatePct: 0.05,
        ),
      ]);
      dep = SyncroDeployment(
        id: id,
        projectId: projectId,
        environmentName: environmentName,
        cloud: cloud,
        targetType: targetType,
        strategy: strategy,
        mode: mode,
        stage: 'promoted_100',
        stablePct: 0,
        canaryPct: 100,
        autoRolledBack: false,
        idempotentReplay: false,
        vmSku: vmSku,
        image: image,
        checkpoints: checkpoints,
      );
    } else {
      checkpoints.add(
        const DeploymentCheckpoint(
          stage: 'canary_5',
          message: 'Manual DevOps hold at 5% canary — awaiting operator Promote or Rollback',
          trafficCanaryPct: 5,
          errorRatePct: 0.11,
        ),
      );
      dep = SyncroDeployment(
        id: id,
        projectId: projectId,
        environmentName: environmentName,
        cloud: cloud,
        targetType: targetType,
        strategy: strategy,
        mode: mode,
        stage: 'canary_5',
        stablePct: 95,
        canaryPct: 5,
        autoRolledBack: false,
        idempotentReplay: false,
        vmSku: vmSku,
        image: image,
        checkpoints: checkpoints,
      );
    }

    _idempotencyCache[idempotencyKey] = dep;
    return dep;
  }

  SyncroDeployment _copyDeployment(
    SyncroDeployment d, {
    required String stage,
    required int stablePct,
    required int canaryPct,
    required DeploymentCheckpoint checkpoint,
    String? rollbackReason,
  }) {
    return SyncroDeployment(
      id: d.id,
      projectId: d.projectId,
      environmentName: d.environmentName,
      cloud: d.cloud,
      targetType: d.targetType,
      strategy: d.strategy,
      mode: d.mode,
      stage: stage,
      stablePct: stablePct,
      canaryPct: canaryPct,
      autoRolledBack: d.autoRolledBack,
      idempotentReplay: d.idempotentReplay,
      rollbackReason: rollbackReason ?? d.rollbackReason,
      vmSku: d.vmSku,
      image: d.image,
      checkpoints: <DeploymentCheckpoint>[...d.checkpoints, checkpoint],
    );
  }

  void _upsertDeployment(SyncroDeployment dep) {
    final idx = _deployments.indexWhere((d) => d.id == dep.id);
    if (idx >= 0) {
      _deployments = List<SyncroDeployment>.from(_deployments)..[idx] = dep;
    } else {
      _deployments = <SyncroDeployment>[dep, ..._deployments];
    }
    final journal = Map<String, dynamic>.from(
      _resilienceHealth['journal'] as Map<String, dynamic>? ?? <String, dynamic>{},
    );
    journal['deployments_persisted'] = _deployments.length;
    _resilienceHealth = <String, dynamic>{
      ..._resilienceHealth,
      'journal': journal,
    };
  }

  void _startHeartbeatLoop() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(config.heartbeatInterval, (_) {
      if (_connected && _localProbe != null) {
        unawaited(
          _api.sendHeartbeat(_localProbe!, _mode).catchError((Object _) {
            // Handled via circuit breaker state on next UI cycle
          }),
        );
      }
    });
  }

  void _connectWebSocket() {
    unawaited(_wsSub?.cancel());
    try {
      _wsSub = _api.connectLiveStream().listen(
        (evt) {
          final type = evt['type']?.toString() ?? 'event';
          _appendEvent('WS [$type] ${evt.toString()}');
          notifyListeners();
        },
        onError: (Object _) {
          _appendEvent('WebSocket stream disconnected — resilient polling active');
          notifyListeners();
        },
      );
    } catch (_) {
      // Ignore WS connection failures when offline
    }
  }

  void _appendEvent(String line) {
    final now = DateTime.now().toUtc();
    final hh = now.hour.toString().padLeft(2, '0');
    final mm = now.minute.toString().padLeft(2, '0');
    final ss = now.second.toString().padLeft(2, '0');
    _eventFeed.insert(0, '[$hh:$mm:$ss UTC] $line');
    if (_eventFeed.length > 80) {
      _eventFeed.removeRange(80, _eventFeed.length);
    }
  }

  static List<SyncroSuiteModule> _defaultSuiteModules() {
    return const <SyncroSuiteModule>[
      SyncroSuiteModule(
        id: 'syncro-desktop',
        name: 'Syncro Desktop',
        role: 'Cross-Platform Flutter Desktop Agent & Unified Suite Workbench',
        status: 'active',
        transport: 'flutter-desktop',
        capabilities: <String>['agentic-manual-toggle', 'local-cli-bridge', 'heartbeat-telemetry'],
      ),
      SyncroSuiteModule(
        id: 'syncro-deployer',
        name: 'Syncro Deployer',
        role: 'Multi-Cloud DevSecOps Deployer (AWS · GCP · Azure · K8s · Docker)',
        status: 'active',
        transport: 'rest+ws',
        capabilities: <String>['canary-rollout', 'auto-rollback', 'idempotency-keys'],
      ),
      SyncroSuiteModule(
        id: 'syncro-cli',
        name: 'Syncro CLI',
        role: 'Unified Terminal Automation (`syncro` / `aegis`) for CI/CD & Operators',
        status: 'active',
        transport: 'cli',
        capabilities: <String>['syncro-deploy', 'quick-destroy', 'vm-select'],
      ),
      SyncroSuiteModule(
        id: 'syncro-ide',
        name: 'Syncro IDE',
        role: 'AI Editor & Coding Agent Integration via Guardrailed MCP Server (29 Tools)',
        status: 'connected',
        transport: 'mcp',
        capabilities: <String>['mcp-stdio-http', 'guardrail-prompts', 'terraform-hcl-gen'],
      ),
      SyncroSuiteModule(
        id: 'syncro-db',
        name: 'Syncro DB',
        role: 'Durable SQLite WAL State Journal, Redis Locks & Kafka Audit Backbone',
        status: 'active',
        transport: 'sqlite-wal+redis',
        capabilities: <String>['wal-state-journal', 'distributed-locks', 'audit-cloudevents'],
      ),
      SyncroSuiteModule(
        id: 'syncro-git',
        name: 'Syncro Git',
        role: 'GitOps PR Policy Webhook (TypeScript Extension) & Ephemeral PR Envs',
        status: 'active',
        transport: 'gitops-webhook',
        capabilities: <String>['pr-admission-gate', 'ephemeral-pr-deploy', 'auto-destroy-on-close'],
      ),
      SyncroSuiteModule(
        id: 'syncro-tester',
        name: 'Syncro Tester',
        role: 'Automated Canary Load, Chaos & E2E Verification Gate (Roadmap Module)',
        status: 'planned',
        transport: 'contract-ready',
        capabilities: <String>['pre_promote_test_gate', 'slo-canary-probes', 'chaos-injection'],
      ),
    ];
  }

  static List<SyncroDeployment> _seedInitialDeployments() {
    return const <SyncroDeployment>[
      SyncroDeployment(
        id: 'sync-seed-001',
        projectId: 'edge-gateway',
        environmentName: 'prod-eu-canary',
        cloud: 'gcp',
        targetType: 'kubernetes',
        strategy: 'canary',
        mode: SyncroMode.manual,
        stage: 'canary_5',
        stablePct: 95,
        canaryPct: 5,
        autoRolledBack: false,
        idempotentReplay: false,
        vmSku: 'n2d-standard-4',
        image: 'ghcr.io/aegisops/edge-gateway:1.5.0',
        checkpoints: <DeploymentCheckpoint>[
          DeploymentCheckpoint(
            stage: 'planned',
            message: 'Persisted to SQLite WAL & locked in Redis',
            trafficCanaryPct: 0,
            errorRatePct: 0.0,
          ),
          DeploymentCheckpoint(
            stage: 'preflight_passed',
            message: 'Checkov / Trivy / OPA passed (score 100/100)',
            trafficCanaryPct: 0,
            errorRatePct: 0.0,
          ),
          DeploymentCheckpoint(
            stage: 'canary_5',
            message: 'Manual DevOps hold at 5% canary — ready to Promote or Rollback',
            trafficCanaryPct: 5,
            errorRatePct: 0.11,
          ),
        ],
      ),
    ];
  }

  @override
  void dispose() {
    _heartbeatTimer?.cancel();
    unawaited(_wsSub?.cancel());
    _api.dispose();
    super.dispose();
  }
}
