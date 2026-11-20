/// Runtime configuration injected via `--dart-define` or desktop defaults.
class AgentConfig {
  const AgentConfig({
    this.apiBaseUrl = const String.fromEnvironment(
      'SYNCRO_API_URL',
      defaultValue: 'http://127.0.0.1:8080',
    ),
    this.agentId = const String.fromEnvironment(
      'SYNCRO_AGENT_ID',
      defaultValue: 'desk-syncro-flutter-01',
    ),
    this.suiteReferenceUrl = 'https://project-syncroo.netlify.app',
    this.heartbeatInterval = const Duration(seconds: 20),
    this.requestTimeout = const Duration(seconds: 6),
  });

  final String apiBaseUrl;
  final String agentId;
  final String suiteReferenceUrl;
  final Duration heartbeatInterval;
  final Duration requestTimeout;

  String get wsUrl {
    final uri = Uri.parse(apiBaseUrl);
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    final port = uri.hasPort ? uri.port : (scheme == 'wss' ? 443 : 80);
    return '$scheme://${uri.host}:$port/ws/events';
  }
}
