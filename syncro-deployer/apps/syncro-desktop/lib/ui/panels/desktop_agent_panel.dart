import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/syncro_theme.dart';
import '../../state/syncro_controller.dart';

/// Displays workstation CLI bridge probe, Circuit Breakers, SQLite WAL telemetry, and the 7-module Syncro Suite.
class DesktopAgentPanel extends StatelessWidget {
  const DesktopAgentPanel({super.key, required this.controller});

  final SyncroController controller;

  @override
  Widget build(BuildContext context) {
    final probe = controller.localProbe;
    final health = controller.resilienceHealth;
    final journal = health['journal'] as Map<String, dynamic>? ?? const <String, dynamic>{};
    final breakers =
        health['circuit_breakers'] as Map<String, dynamic>? ?? const <String, dynamic>{};

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'SYNCRO DESKTOP AGENT BRIDGE · SUITE TOPOLOGY',
            style: TextStyle(
              fontSize: 12,
              letterSpacing: 1.1,
              fontWeight: FontWeight.w700,
              color: SyncroTheme.accentSteel,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Native workstation inspector, resilient transport & unified Syncro Suite (${controller.config.suiteReferenceUrl}).',
            style: const TextStyle(fontSize: 13, color: SyncroTheme.textSecondary),
          ),
          const SizedBox(height: 16),
          // Local Workstation CLI Bridge
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: <Widget>[
                      const Text(
                        'Workstation LocalAgentBridge (dart:io)',
                        style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                      ),
                      OutlinedButton.icon(
                        onPressed: () => unawaited(controller.refreshLocalProbe()),
                        icon: const Icon(Icons.refresh, size: 15),
                        label: const Text('Re-Probe & Heartbeat'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    probe == null
                        ? 'Probing host workstation...'
                        : 'Host: ${probe.hostname} · OS: ${probe.osPlatform.toUpperCase()} · Agent ID: ${controller.config.agentId}',
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 12,
                      color: SyncroTheme.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: (probe?.detectedTools ?? const <String>[]).isEmpty
                        ? const <Widget>[
                            Chip(label: Text('No local CLIs detected in sandbox')),
                          ]
                        : probe!.detectedTools
                            .map(
                              (tool) => Chip(
                                avatar: const Icon(
                                  Icons.check_circle,
                                  size: 14,
                                  color: SyncroTheme.statusOk,
                                ),
                                label: Text(
                                  tool,
                                  style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
                                ),
                                backgroundColor: SyncroTheme.well,
                              ),
                            )
                            .toList(),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          // Resilience & SQLite WAL Telemetry
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Text(
                    'Resilience Telemetry (Circuit Breakers & SQLite WAL Journal)',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: <Widget>[
                      _telemetryChip(
                        'Desktop HTTP Breaker',
                        controller.clientBreakerState.name.toUpperCase(),
                        controller.clientBreakerState.name == 'closed'
                            ? SyncroTheme.statusOk
                            : SyncroTheme.statusDanger,
                      ),
                      _telemetryChip(
                        'WAL Deployments',
                        '${journal['deployments_persisted'] ?? controller.deployments.length}',
                        SyncroTheme.accentSteel,
                      ),
                      ...breakers.entries.map((entry) {
                        final map = entry.value as Map<String, dynamic>? ?? const <String, dynamic>{};
                        final st = (map['state']?.toString() ?? 'closed').toUpperCase();
                        return _telemetryChip(
                          entry.key,
                          st,
                          st == 'CLOSED' ? SyncroTheme.statusOk : SyncroTheme.statusDanger,
                        );
                      }),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          // 7-Module Syncro Suite Topology
          const Text(
            'UNIFIED SYNCRO SUITE (7 MODULES)',
            style: TextStyle(
              fontSize: 11,
              letterSpacing: 1.0,
              fontWeight: FontWeight.w700,
              color: SyncroTheme.textMuted,
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: controller.suiteModules.map((m) {
              final isPlanned = m.status == 'planned';
              final statusColor = isPlanned ? SyncroTheme.statusWarn : SyncroTheme.statusOk;
              return Container(
                width: 280,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: SyncroTheme.surface,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: m.id == controller.selectedModuleId
                        ? SyncroTheme.accentSteel
                        : SyncroTheme.hairline,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: <Widget>[
                        Text(
                          m.name,
                          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: statusColor.withAlpha(32),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            m.status.toUpperCase(),
                            style: TextStyle(
                              fontSize: 9,
                              fontFamily: 'monospace',
                              fontWeight: FontWeight.w700,
                              color: statusColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      m.role,
                      style: const TextStyle(fontSize: 11, color: SyncroTheme.textSecondary),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Transport: ${m.transport}',
                      style: const TextStyle(
                        fontSize: 10,
                        fontFamily: 'monospace',
                        color: SyncroTheme.textMuted,
                      ),
                    ),
                  ],
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _telemetryChip(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: SyncroTheme.well,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: SyncroTheme.hairline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            label,
            style: const TextStyle(fontSize: 10, color: SyncroTheme.textMuted),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
              fontSize: 12,
              fontFamily: 'monospace',
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
