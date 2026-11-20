import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/syncro_theme.dart';
import '../../models/syncro_models.dart';
import '../../state/syncro_controller.dart';

/// Displays all persisted Syncro Deployer pipelines with traffic splits, checkpoints, and rollback controls.
class PipelineDeploymentsPanel extends StatelessWidget {
  const PipelineDeploymentsPanel({super.key, required this.controller});

  final SyncroController controller;

  @override
  Widget build(BuildContext context) {
    final deps = controller.deployments;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'SYNCRO DEPLOYER PIPELINES · WAL STATE JOURNAL',
            style: TextStyle(
              fontSize: 12,
              letterSpacing: 1.1,
              fontWeight: FontWeight.w700,
              color: SyncroTheme.accentSteel,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Tracking ${deps.length} idempotent release pipelines across AWS, GCP, Azure, Kubernetes & Docker.',
            style: const TextStyle(fontSize: 13, color: SyncroTheme.textSecondary),
          ),
          const SizedBox(height: 16),
          if (deps.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Text('No deployments recorded yet.'),
              ),
            )
          else
            ...deps.map((dep) => _deploymentCard(dep)),
        ],
      ),
    );
  }

  Widget _deploymentCard(SyncroDeployment dep) {
    final stageColor = _stageColor(dep.stage);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: <Widget>[
                  Text(
                    dep.id,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                    ),
                  ),
                  _badge(dep.stage.toUpperCase(), stageColor),
                  _badge(
                    dep.mode.label.toUpperCase(),
                    dep.mode == SyncroMode.agentic
                        ? SyncroTheme.accentSteel
                        : SyncroTheme.statusWarn,
                  ),
                  _badge('${dep.cloud.toUpperCase()} · ${dep.targetType}', SyncroTheme.textSecondary),
                  if (dep.idempotentReplay)
                    _badge('IDEMPOTENT REPLAY', SyncroTheme.accentSteel),
                  if (dep.autoRolledBack)
                    _badge('AUTO-ROLLED BACK', SyncroTheme.statusDanger),
                ],
              ),
              const SizedBox(height: 10),
              // Traffic Split Bar
              Row(
                children: <Widget>[
                  Text(
                    'Traffic Split: ${dep.stablePct}% Stable / ${dep.canaryPct}% Canary',
                    style: const TextStyle(
                      fontSize: 11,
                      fontFamily: 'monospace',
                      color: SyncroTheme.textSecondary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: SizedBox(
                  height: 8,
                  child: Row(
                    children: <Widget>[
                      if (dep.stablePct > 0)
                        Expanded(
                          flex: dep.stablePct,
                          child: Container(color: SyncroTheme.hairline),
                        ),
                      if (dep.canaryPct > 0)
                        Expanded(
                          flex: dep.canaryPct,
                          child: Container(color: stageColor),
                        ),
                    ],
                  ),
                ),
              ),
              if (dep.rollbackReason != null) ...<Widget>[
                const SizedBox(height: 8),
                Text(
                  'Rollback Reason: ${dep.rollbackReason}',
                  style: const TextStyle(fontSize: 12, color: SyncroTheme.statusDanger),
                ),
              ],
              const SizedBox(height: 12),
              // Checkpoint timeline
              ...dep.checkpoints.map(
                (cp) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      const Icon(Icons.chevron_right, size: 14, color: SyncroTheme.textMuted),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          '[${cp.stage}] ${cp.message} (canary ${cp.trafficCanaryPct}%, err ${cp.errorRatePct.toStringAsFixed(2)}%)',
                          style: const TextStyle(
                            fontSize: 11,
                            fontFamily: 'monospace',
                            color: SyncroTheme.textSecondary,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              if (dep.canPromote || dep.canRollback) ...<Widget>[
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  children: <Widget>[
                    if (dep.canPromote)
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: SyncroTheme.statusOk,
                          foregroundColor: const Color(0xFF04140D),
                        ),
                        onPressed: controller.busy
                            ? null
                            : () => unawaited(controller.promoteDeployment(dep.id)),
                        icon: const Icon(Icons.upgrade, size: 15),
                        label: const Text('Promote Stage'),
                      ),
                    if (dep.canRollback)
                      OutlinedButton.icon(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: SyncroTheme.statusDanger,
                          side: const BorderSide(color: SyncroTheme.statusDanger),
                        ),
                        onPressed: controller.busy
                            ? null
                            : () => unawaited(controller.rollbackDeployment(dep.id)),
                        icon: const Icon(Icons.history, size: 15),
                        label: const Text('Rollback'),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Color _stageColor(String stage) {
    switch (stage) {
      case 'promoted_100':
        return SyncroTheme.statusOk;
      case 'canary_5':
      case 'canary_25':
        return SyncroTheme.statusWarn;
      case 'rolled_back':
      case 'blocked':
        return SyncroTheme.statusDanger;
      default:
        return SyncroTheme.accentSteel;
    }
  }

  Widget _badge(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(32),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withAlpha(110)),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          fontFamily: 'monospace',
          color: color,
        ),
      ),
    );
  }
}
