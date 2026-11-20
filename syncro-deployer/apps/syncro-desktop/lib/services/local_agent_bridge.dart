import 'dart:io';

import '../models/syncro_models.dart';

/// Native desktop bridge probing local DevOps CLIs across Windows, macOS, and Linux.
class LocalAgentBridge {
  static const List<String> trackedBinaries = [
    'az',
    'aws',
    'gcloud',
    'docker',
    'kubectl',
    'terraform',
    'ansible-playbook',
    'pwsh',
    'git',
    'syncro',
  ];

  Future<DesktopAgentProbe> inspectWorkstation() async {
    final detected = <String>[];
    final locator = Platform.isWindows ? 'where' : 'which';

    for (final bin in trackedBinaries) {
      try {
        final res = await Process.run(locator, [bin]);
        if (res.exitCode == 0) {
          detected.add(bin);
        }
      } catch (_) {
        // Ignore unavailable binary in sandboxed/test runtime
      }
    }

    return DesktopAgentProbe(
      hostname: Platform.localHostname,
      osPlatform: Platform.operatingSystem,
      detectedTools: detected,
      probedAt: DateTime.now().toUtc(),
    );
  }
}
