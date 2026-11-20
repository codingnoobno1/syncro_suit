import 'dart:async';

import 'package:flutter/material.dart';

import 'core/config/agent_config.dart';
import 'core/theme/syncro_theme.dart';
import 'state/syncro_controller.dart';
import 'ui/syncro_shell.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SyncroDesktopApp());
}

/// Root Flutter Desktop application for Syncro Desktop & Syncro Deployer.
class SyncroDesktopApp extends StatefulWidget {
  const SyncroDesktopApp({
    super.key,
    this.controller,
    this.autoBootstrap = true,
  });

  final SyncroController? controller;
  final bool autoBootstrap;

  @override
  State<SyncroDesktopApp> createState() => _SyncroDesktopAppState();
}

class _SyncroDesktopAppState extends State<SyncroDesktopApp> {
  late final SyncroController _controller;
  late final bool _ownsController;

  @override
  void initState() {
    super.initState();
    if (widget.controller != null) {
      _controller = widget.controller!;
      _ownsController = false;
    } else {
      _controller = SyncroController(config: const AgentConfig());
      _ownsController = true;
    }
    if (widget.autoBootstrap) {
      unawaited(_controller.bootstrap());
    }
  }

  @override
  void dispose() {
    if (_ownsController) {
      _controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Syncro Desktop · Syncro Deployer Agent',
      debugShowCheckedModeBanner: false,
      theme: SyncroTheme.buildDarkTheme(),
      home: SyncroShell(controller: _controller),
    );
  }
}
