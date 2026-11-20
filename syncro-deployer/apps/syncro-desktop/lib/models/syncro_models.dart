/// Typed immutable Dart models mirroring Syncro Deployer & MCP Bot API contracts.
enum SyncroMode {
  agentic('agentic', 'Agentic Mode'),
  manual('manual', 'Manual DevOps Mode');

  const SyncroMode(this.apiValue, this.label);
  final String apiValue;
  final String label;

  static SyncroMode fromApi(String? value) =>
      value == 'manual' ? SyncroMode.manual : SyncroMode.agentic;
}

class SyncroSuiteModule {
  const SyncroSuiteModule({
    required this.id,
    required this.name,
    required this.role,
    required this.status,
    required this.transport,
    required this.capabilities,
  });

  final String id;
  final String name;
  final String role;
  final String status;
  final String transport;
  final List<String> capabilities;

  factory SyncroSuiteModule.fromJson(Map<String, dynamic> json) {
    return SyncroSuiteModule(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      role: json['role']?.toString() ?? '',
      status: json['status']?.toString() ?? 'active',
      transport: json['transport']?.toString() ?? '',
      capabilities: (json['capabilities'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}

class DeploymentCheckpoint {
  const DeploymentCheckpoint({
    required this.stage,
    required this.message,
    required this.trafficCanaryPct,
    required this.errorRatePct,
  });

  final String stage;
  final String message;
  final int trafficCanaryPct;
  final double errorRatePct;

  factory DeploymentCheckpoint.fromJson(Map<String, dynamic> json) {
    return DeploymentCheckpoint(
      stage: json['stage']?.toString() ?? 'planned',
      message: json['message']?.toString() ?? '',
      trafficCanaryPct: (json['traffic_canary_pct'] as num?)?.toInt() ?? 0,
      errorRatePct: (json['error_rate_pct'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class SyncroDeployment {
  const SyncroDeployment({
    required this.id,
    required this.projectId,
    required this.environmentName,
    required this.cloud,
    required this.targetType,
    required this.strategy,
    required this.mode,
    required this.stage,
    required this.stablePct,
    required this.canaryPct,
    required this.autoRolledBack,
    required this.idempotentReplay,
    required this.checkpoints,
    this.rollbackReason,
    this.vmSku,
    this.image,
  });

  final String id;
  final String projectId;
  final String environmentName;
  final String cloud;
  final String targetType;
  final String strategy;
  final SyncroMode mode;
  final String stage;
  final int stablePct;
  final int canaryPct;
  final bool autoRolledBack;
  final bool idempotentReplay;
  final List<DeploymentCheckpoint> checkpoints;
  final String? rollbackReason;
  final String? vmSku;
  final String? image;

  bool get canPromote => stage == 'canary_5' || stage == 'canary_25';
  bool get canRollback => stage != 'rolled_back' && stage != 'blocked';

  factory SyncroDeployment.fromJson(Map<String, dynamic> json) {
    final split = json['traffic_split'] as Map<String, dynamic>? ?? const {};
    return SyncroDeployment(
      id: json['id']?.toString() ?? '',
      projectId: json['project_id']?.toString() ?? '',
      environmentName: json['environment_name']?.toString() ?? '',
      cloud: json['cloud']?.toString() ?? 'gcp',
      targetType: json['target_type']?.toString() ?? 'kubernetes',
      strategy: json['strategy']?.toString() ?? 'canary',
      mode: SyncroMode.fromApi(json['mode']?.toString()),
      stage: json['stage']?.toString() ?? 'planned',
      stablePct: (split['stable'] as num?)?.toInt() ?? 100,
      canaryPct: (split['canary'] as num?)?.toInt() ?? 0,
      autoRolledBack: json['auto_rolled_back'] == true,
      idempotentReplay: json['idempotent_replay'] == true,
      rollbackReason: json['rollback_reason']?.toString(),
      vmSku: json['vm_sku']?.toString(),
      image: json['image']?.toString(),
      checkpoints: (json['checkpoints'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .map(DeploymentCheckpoint.fromJson)
          .toList(),
    );
  }
}

class BillSummary {
  const BillSummary({
    required this.forecastEomUsd,
    required this.userTargetCapUsd,
    required this.hardBudgetCapUsd,
    required this.identifiableSavingsUsd,
    required this.egressMonthlyUsd,
    required this.spendByCloud,
  });

  final double forecastEomUsd;
  final double userTargetCapUsd;
  final double hardBudgetCapUsd;
  final double identifiableSavingsUsd;
  final double egressMonthlyUsd;
  final Map<String, double> spendByCloud;

  factory BillSummary.fromJson(Map<String, dynamic> json) {
    final rawMap = json['spend_by_cloud'] as Map<String, dynamic>? ?? const {};
    return BillSummary(
      forecastEomUsd: (json['forecasted_eom_usd'] as num?)?.toDouble() ?? 0.0,
      userTargetCapUsd: (json['user_target_cap_usd'] as num?)?.toDouble() ?? 9500.0,
      hardBudgetCapUsd: (json['hard_budget_cap_usd'] as num?)?.toDouble() ?? 22000.0,
      identifiableSavingsUsd:
          (json['total_identifiable_monthly_savings_usd'] as num?)?.toDouble() ?? 0.0,
      egressMonthlyUsd: (json['egress_monthly_usd'] as num?)?.toDouble() ?? 0.0,
      spendByCloud: rawMap.map((k, v) => MapEntry(k, (v as num).toDouble())),
    );
  }
}

class DesktopAgentProbe {
  const DesktopAgentProbe({
    required this.hostname,
    required this.osPlatform,
    required this.detectedTools,
    required this.probedAt,
  });

  final String hostname;
  final String osPlatform;
  final List<String> detectedTools;
  final DateTime probedAt;
}
