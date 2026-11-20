import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/syncro_theme.dart';
import '../../models/syncro_models.dart';
import '../../state/syncro_controller.dart';

/// Manual DevOps Mode workbench: Explicit operator stage gates (Canary 5% -> Promote -> 25% -> 100% / Rollback).
class ManualDevOpsPanel extends StatefulWidget {
  const ManualDevOpsPanel({super.key, required this.controller});

  final SyncroController controller;

  @override
  State<ManualDevOpsPanel> createState() => _ManualDevOpsPanelState();
}

class _ManualDevOpsPanelState extends State<ManualDevOpsPanel> {
  final TextEditingController _envCtrl = TextEditingController(text: 'prod-manual-stage');
  final TextEditingController _skuCtrl = TextEditingController(text: 'Standard_D4as_v5');
  final TextEditingController _imageCtrl =
      TextEditingController(text: 'ghcr.io/aegisops/edge-gateway:1.5.0');
  final TextEditingController _keyCtrl = TextEditingController(text: 'manual-chg-204');

  String _cloud = 'azure';
  String _targetType = 'kubernetes';
  String _strategy = 'canary';

  @override
  void dispose() {
    _envCtrl.dispose();
    _skuCtrl.dispose();
    _imageCtrl.dispose();
    _keyCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final heldDeployments = c.deployments.where((d) => d.canPromote).toList();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'MANUAL DEVOPS MODE · EXPLICIT STAGE-GATE CONTROL',
            style: TextStyle(
              fontSize: 12,
              letterSpacing: 1.1,
              fontWeight: FontWeight.w700,
              color: SyncroTheme.statusWarn,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Every rollout pauses at CANARY_5 (5% traffic) until an operator explicitly executes Promote or Instant Rollback.',
            style: TextStyle(fontSize: 13, color: SyncroTheme.textSecondary),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Row(
                    children: <Widget>[
                      Icon(Icons.tune, size: 18, color: SyncroTheme.statusWarn),
                      SizedBox(width: 8),
                      Text(
                        'Operator Release Plan (Idempotent & Lock-Safe)',
                        style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: <Widget>[
                      SizedBox(
                        width: 150,
                        child: DropdownButtonFormField<String>(
                          value: _cloud,
                          decoration: const InputDecoration(labelText: 'Cloud Provider'),
                          items: const <DropdownMenuItem<String>>[
                            DropdownMenuItem(value: 'azure', child: Text('Azure')),
                            DropdownMenuItem(value: 'aws', child: Text('AWS')),
                            DropdownMenuItem(value: 'gcp', child: Text('GCP')),
                          ],
                          onChanged: (v) {
                            if (v != null) {
                              setState(() => _cloud = v);
                            }
                          },
                        ),
                      ),
                      SizedBox(
                        width: 170,
                        child: DropdownButtonFormField<String>(
                          value: _targetType,
                          decoration: const InputDecoration(labelText: 'Target Runtime'),
                          items: const <DropdownMenuItem<String>>[
                            DropdownMenuItem(value: 'kubernetes', child: Text('Kubernetes')),
                            DropdownMenuItem(value: 'vm', child: Text('Cloud VM (IaC)')),
                            DropdownMenuItem(value: 'docker', child: Text('Docker Container')),
                          ],
                          onChanged: (v) {
                            if (v != null) {
                              setState(() => _targetType = v);
                            }
                          },
                        ),
                      ),
                      SizedBox(
                        width: 160,
                        child: DropdownButtonFormField<String>(
                          value: _strategy,
                          decoration: const InputDecoration(labelText: 'Strategy'),
                          items: const <DropdownMenuItem<String>>[
                            DropdownMenuItem(value: 'canary', child: Text('Canary')),
                            DropdownMenuItem(value: 'blue-green', child: Text('Blue-Green')),
                            DropdownMenuItem(value: 'rolling', child: Text('Rolling')),
                          ],
                          onChanged: (v) {
                            if (v != null) {
                              setState(() => _strategy = v);
                            }
                          },
                        ),
                      ),
                      SizedBox(
                        width: 200,
                        child: TextField(
                          controller: _envCtrl,
                          decoration: const InputDecoration(labelText: 'Environment Name'),
                        ),
                      ),
                      SizedBox(
                        width: 200,
                        child: TextField(
                          controller: _keyCtrl,
                          decoration: const InputDecoration(labelText: 'Idempotency-Key'),
                        ),
                      ),
                      SizedBox(
                        width: 210,
                        child: TextField(
                          controller: _skuCtrl,
                          decoration: const InputDecoration(labelText: 'VM SKU (IaC target)'),
                        ),
                      ),
                      SizedBox(
                        width: 280,
                        child: TextField(
                          controller: _imageCtrl,
                          decoration: const InputDecoration(labelText: 'Container Image'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 12,
                    runSpacing: 8,
                    children: <Widget>[
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: SyncroTheme.statusWarn,
                          foregroundColor: const Color(0xFF140D02),
                        ),
                        onPressed: c.busy
                            ? null
                            : () {
                                unawaited(
                                  c.deploy(
                                    projectId: 'edge-gateway',
                                    environmentName: _envCtrl.text.trim(),
                                    cloud: _cloud,
                                    targetType: _targetType,
                                    strategy: _strategy,
                                    idempotencyKey: _keyCtrl.text,
                                    overrideMode: SyncroMode.manual,
                                    vmSku: _skuCtrl.text.trim(),
                                    image: _imageCtrl.text.trim(),
                                  ),
                                );
                              },
                        icon: const Icon(Icons.pause_circle_outline, size: 16),
                        label: const Text('Stage Manual Deploy (Hold @ 5%)'),
                      ),
                      OutlinedButton.icon(
                        onPressed: () {
                          _keyCtrl.text = 'manual-chg-${DateTime.now().millisecondsSinceEpoch % 10000}';
                          setState(() {});
                        },
                        icon: const Icon(Icons.key, size: 16),
                        label: const Text('Rotate Idempotency-Key'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Awaiting Manual Operator Gate (${heldDeployments.length})',
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 12),
                  if (heldDeployments.isEmpty)
                    const Text(
                      'No deployments currently paused at a canary gate. Stage a manual deploy above to inspect promotion gates.',
                      style: TextStyle(fontSize: 12, color: SyncroTheme.textMuted),
                    )
                  else
                    ...heldDeployments.map(
                      (dep) => Container(
                        margin: const EdgeInsets.only(bottom: 10),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: SyncroTheme.well,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: SyncroTheme.hairline),
                        ),
                        child: Wrap(
                          spacing: 12,
                          runSpacing: 8,
                          alignment: WrapAlignment.spaceBetween,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: <Widget>[
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(
                                  '${dep.id} · ${dep.environmentName} (${dep.cloud.toUpperCase()} / ${dep.targetType})',
                                  style: const TextStyle(
                                    fontFamily: 'monospace',
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Stage: ${dep.stage.toUpperCase()} · Traffic Split: ${dep.stablePct}% stable / ${dep.canaryPct}% canary',
                                  style: const TextStyle(
                                    fontSize: 11,
                                    color: SyncroTheme.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                            Wrap(
                              spacing: 8,
                              children: <Widget>[
                                ElevatedButton.icon(
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: SyncroTheme.statusOk,
                                    foregroundColor: const Color(0xFF04140D),
                                  ),
                                  onPressed: c.busy
                                      ? null
                                      : () => unawaited(c.promoteDeployment(dep.id)),
                                  icon: const Icon(Icons.trending_up, size: 15),
                                  label: Text(
                                    dep.stage == 'canary_5' ? 'Promote -> 25%' : 'Promote -> 100%',
                                  ),
                                ),
                                OutlinedButton.icon(
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: SyncroTheme.statusDanger,
                                    side: const BorderSide(color: SyncroTheme.statusDanger),
                                  ),
                                  onPressed: c.busy
                                      ? null
                                      : () => unawaited(c.rollbackDeployment(dep.id)),
                                  icon: const Icon(Icons.undo, size: 15),
                                  label: const Text('Instant Rollback'),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
