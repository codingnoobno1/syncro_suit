import 'dart:async';

import 'package:flutter/material.dart';

import '../core/theme/syncro_theme.dart';
import '../models/syncro_models.dart';
import '../state/syncro_controller.dart';
import 'panels/agentic_mode_panel.dart';
import 'panels/desktop_agent_panel.dart';
import 'panels/manual_devops_panel.dart';
import 'panels/pipeline_deployments_panel.dart';

/// Native desktop shell uniting the 7-module Syncro Suite rail, Agentic/Manual mode switcher,
/// workbench views, and live Kafka/Audit telemetry drawer.
class SyncroShell extends StatefulWidget {
  const SyncroShell({super.key, required this.controller});

  final SyncroController controller;

  @override
  State<SyncroShell> createState() => _SyncroShellState();
}

class _SyncroShellState extends State<SyncroShell> {
  bool _drawerExpanded = true;

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return AnimatedBuilder(
      animation: c,
      builder: (context, _) {
        return Scaffold(
          body: Row(
            children: <Widget>[
              _buildSuiteRail(c),
              const VerticalDivider(width: 1),
              Expanded(
                child: Column(
                  children: <Widget>[
                    _buildTopBar(c),
                    const Divider(height: 1),
                    Expanded(child: _buildActivePanel(c)),
                    const Divider(height: 1),
                    _buildAuditDrawer(c),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildSuiteRail(SyncroController c) {
    return Container(
      width: 215,
      color: SyncroTheme.well,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
            child: Row(
              children: <Widget>[
                Container(
                  width: 26,
                  height: 26,
                  decoration: BoxDecoration(
                    color: SyncroTheme.accentSteel,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  alignment: Alignment.center,
                  child: const Text(
                    'S',
                    style: TextStyle(
                      color: Color(0xFF071216),
                      fontWeight: FontWeight.w800,
                      fontSize: 15,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        'SYNCRO SUITE',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1.0,
                        ),
                      ),
                      Text(
                        'Desktop Agent v0.1',
                        style: TextStyle(fontSize: 10, color: SyncroTheme.textMuted),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
              children: c.suiteModules.map((mod) {
                final selected = mod.id == c.selectedModuleId;
                final isPlanned = mod.status == 'planned';
                return Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(6),
                    onTap: () => c.selectSuiteModule(mod.id),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                      decoration: BoxDecoration(
                        color: selected ? SyncroTheme.surfaceElevated : Colors.transparent,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: selected ? SyncroTheme.accentSteel : Colors.transparent,
                        ),
                      ),
                      child: Row(
                        children: <Widget>[
                          Icon(
                            _iconForModule(mod.id),
                            size: 16,
                            color: selected
                                ? SyncroTheme.accentSteel
                                : SyncroTheme.textSecondary,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              mod.name,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                                color: selected
                                    ? SyncroTheme.textPrimary
                                    : SyncroTheme.textSecondary,
                              ),
                            ),
                          ),
                          if (isPlanned)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                              decoration: BoxDecoration(
                                color: SyncroTheme.statusWarn.withAlpha(32),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: const Text(
                                'SOON',
                                style: TextStyle(
                                  fontSize: 8,
                                  fontFamily: 'monospace',
                                  fontWeight: FontWeight.w700,
                                  color: SyncroTheme.statusWarn,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              c.connected ? 'CONTROL PLANE: ONLINE' : 'RESILIENT LOCAL MODE',
              style: TextStyle(
                fontSize: 10,
                fontFamily: 'monospace',
                fontWeight: FontWeight.w700,
                color: c.connected ? SyncroTheme.statusOk : SyncroTheme.statusWarn,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTopBar(SyncroController c) {
    return Container(
      width: double.infinity,
      color: SyncroTheme.surface,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Wrap(
        spacing: 14,
        runSpacing: 10,
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          // Dual-Mode Switcher: Agentic Mode vs Manual DevOps Mode
          Container(
            decoration: BoxDecoration(
              color: SyncroTheme.well,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: SyncroTheme.hairline),
            ),
            padding: const EdgeInsets.all(3),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                _modeToggleButton(
                  label: 'AGENTIC MODE',
                  selected: c.mode == SyncroMode.agentic,
                  activeColor: SyncroTheme.accentSteel,
                  onTap: () => unawaited(c.setMode(SyncroMode.agentic)),
                ),
                const SizedBox(width: 4),
                _modeToggleButton(
                  label: 'MANUAL DEVOPS MODE',
                  selected: c.mode == SyncroMode.manual,
                  activeColor: SyncroTheme.statusWarn,
                  onTap: () => unawaited(c.setMode(SyncroMode.manual)),
                ),
              ],
            ),
          ),
          // Center Workbench View Tabs
          Wrap(
            spacing: 6,
            children: <Widget>[
              _tabButton('Workbench', 0, c),
              _tabButton('Pipelines (${c.deployments.length})', 1, c),
              _tabButton('Agent & Suite', 2, c),
            ],
          ),
          // Resilience & Sync controls
          Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                'CB:${c.clientBreakerState.name.toUpperCase()}',
                style: TextStyle(
                  fontSize: 11,
                  fontFamily: 'monospace',
                  fontWeight: FontWeight.w700,
                  color: c.clientBreakerState.name == 'closed'
                      ? SyncroTheme.statusOk
                      : SyncroTheme.statusDanger,
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'Sync with Syncro Control Plane',
                icon: const Icon(Icons.sync, size: 18),
                onPressed: c.busy ? null : () => unawaited(c.syncFromControlPlane()),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _modeToggleButton({
    required String label,
    required bool selected,
    required Color activeColor,
    required VoidCallback onTap,
  }) {
    return InkWell(
      borderRadius: BorderRadius.circular(4),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          color: selected ? activeColor : Colors.transparent,
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.6,
            color: selected ? const Color(0xFF071216) : SyncroTheme.textSecondary,
          ),
        ),
      ),
    );
  }

  Widget _tabButton(String label, int index, SyncroController c) {
    final active = c.activeTabIndex == index;
    return TextButton(
      style: TextButton.styleFrom(
        backgroundColor: active ? SyncroTheme.surfaceElevated : Colors.transparent,
        foregroundColor: active ? SyncroTheme.textPrimary : SyncroTheme.textSecondary,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),
      onPressed: () => c.selectWorkbenchTab(index),
      child: Text(label, style: const TextStyle(fontSize: 12)),
    );
  }

  Widget _buildActivePanel(SyncroController c) {
    if (c.activeTabIndex == 1) {
      return PipelineDeploymentsPanel(controller: c);
    }
    if (c.activeTabIndex == 2) {
      return DesktopAgentPanel(controller: c);
    }
    if (c.mode == SyncroMode.manual) {
      return ManualDevOpsPanel(controller: c);
    }
    return AgenticModePanel(controller: c);
  }

  Widget _buildAuditDrawer(SyncroController c) {
    return Container(
      color: SyncroTheme.well,
      height: _drawerExpanded ? 118 : 34,
      child: Column(
        children: <Widget>[
          InkWell(
            onTap: () => setState(() => _drawerExpanded = !_drawerExpanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              child: Row(
                children: <Widget>[
                  const Icon(Icons.terminal, size: 14, color: SyncroTheme.accentSteel),
                  const SizedBox(width: 8),
                  Text(
                    'LIVE KAFKA / AGENT AUDIT STREAM (${c.eventFeed.length})',
                    style: const TextStyle(
                      fontSize: 10,
                      fontFamily: 'monospace',
                      fontWeight: FontWeight.w700,
                      color: SyncroTheme.textSecondary,
                    ),
                  ),
                  const Spacer(),
                  Icon(
                    _drawerExpanded ? Icons.expand_more : Icons.expand_less,
                    size: 16,
                    color: SyncroTheme.textMuted,
                  ),
                ],
              ),
            ),
          ),
          if (_drawerExpanded)
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
                itemCount: c.eventFeed.length,
                itemBuilder: (_, idx) => Text(
                  c.eventFeed[idx],
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 11,
                    color: SyncroTheme.textSecondary,
                    height: 1.4,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  IconData _iconForModule(String moduleId) {
    switch (moduleId) {
      case 'syncro-desktop':
        return Icons.desktop_windows_outlined;
      case 'syncro-deployer':
        return Icons.rocket_launch_outlined;
      case 'syncro-cli':
        return Icons.terminal;
      case 'syncro-ide':
        return Icons.code;
      case 'syncro-db':
        return Icons.storage_outlined;
      case 'syncro-git':
        return Icons.merge_type;
      case 'syncro-tester':
        return Icons.science_outlined;
      default:
        return Icons.extension_outlined;
    }
  }
}
