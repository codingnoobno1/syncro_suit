import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/config/agent_config.dart';
import '../core/resilience/retry_client.dart';
import '../models/syncro_models.dart';

/// Typed API + WebSocket client connecting Syncro Desktop to the Syncro Deployer Control Plane.
class SyncroApiClient {
  SyncroApiClient({
    required this.config,
    ResilientHttpClient? httpClient,
  }) : _http = httpClient ?? ResilientHttpClient(timeout: config.requestTimeout);

  final AgentConfig config;
  final ResilientHttpClient _http;

  ResilientHttpClient get transport => _http;

  Uri _u(String path) => Uri.parse('${config.apiBaseUrl}$path');

  Future<List<SyncroSuiteModule>> fetchSuiteModules() async {
    final data = await _http.requestJson('GET', _u('/api/v1/syncro/suite'))
        as Map<String, dynamic>;
    final list = data['modules'] as List<dynamic>? ?? [];
    return list
        .whereType<Map<String, dynamic>>()
        .map(SyncroSuiteModule.fromJson)
        .toList();
  }

  Future<void> setMode(SyncroMode mode) async {
    await _http.requestJson(
      'POST',
      _u('/api/v1/syncro/mode'),
      body: {'mode': mode.apiValue},
    );
  }

  Future<List<SyncroDeployment>> listDeployments() async {
    final list = await _http.requestJson('GET', _u('/api/v1/syncro/deployments'))
        as List<dynamic>;
    return list
        .whereType<Map<String, dynamic>>()
        .map(SyncroDeployment.fromJson)
        .toList();
  }

  Future<SyncroDeployment> deploy({
    required String projectId,
    required String environmentName,
    required String cloud,
    required String targetType,
    required String strategy,
    required SyncroMode mode,
    required String idempotencyKey,
    String vmSku = 'n2d-standard-4',
    String image = 'ghcr.io/aegisops/edge-gateway:1.5.0',
    bool simulateCanaryFault = false,
  }) async {
    final data = await _http.requestJson(
      'POST',
      _u('/api/v1/syncro/deploy'),
      idempotencyKey: idempotencyKey,
      body: {
        'project_id': projectId,
        'environment_name': environmentName,
        'cloud': cloud,
        'target_type': targetType,
        'strategy': strategy,
        'mode': mode.apiValue,
        'vm_sku': vmSku,
        'image': image,
        'idempotency_key': idempotencyKey,
        'simulate_canary_fault': simulateCanaryFault,
        'requested_by': config.agentId,
      },
    ) as Map<String, dynamic>;
    return SyncroDeployment.fromJson(data);
  }

  Future<SyncroDeployment> promote(String deploymentId) async {
    final data = await _http.requestJson(
      'POST',
      _u('/api/v1/syncro/deployments/$deploymentId/promote'),
      body: {'actor': config.agentId},
    ) as Map<String, dynamic>;
    return SyncroDeployment.fromJson(data);
  }

  Future<SyncroDeployment> rollback(String deploymentId, String reason) async {
    final data = await _http.requestJson(
      'POST',
      _u('/api/v1/syncro/deployments/$deploymentId/rollback'),
      body: {'actor': config.agentId, 'reason': reason},
    ) as Map<String, dynamic>;
    return SyncroDeployment.fromJson(data);
  }

  Future<BillSummary> fetchBill() async {
    final data = await _http.requestJson('GET', _u('/api/v1/bot/bill'))
        as Map<String, dynamic>;
    return BillSummary.fromJson(data);
  }

  Future<Map<String, dynamic>> runSelfPromptBillSaver(String customPrompt) async {
    return await _http.requestJson(
      'POST',
      _u('/api/v1/bot/self-prompt/run'),
      body: {'custom_user_prompt': customPrompt},
    ) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> sendNaturalPrompt(String prompt) async {
    return await _http.requestJson(
      'POST',
      _u('/api/v1/bot/prompt'),
      body: {'prompt': prompt},
    ) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> fetchResilienceHealth() async {
    return await _http.requestJson('GET', _u('/api/v1/syncro/resilience/health'))
        as Map<String, dynamic>;
  }

  Future<void> registerAgent(DesktopAgentProbe probe, SyncroMode mode) async {
    await _http.requestJson(
      'POST',
      _u('/api/v1/syncro/agents/register'),
      body: {
        'agent_id': config.agentId,
        'hostname': probe.hostname,
        'os_platform': probe.osPlatform,
        'app_version': '0.1.0',
        'active_mode': mode.apiValue,
        'local_tools_detected': probe.detectedTools,
      },
    );
  }

  Future<void> sendHeartbeat(DesktopAgentProbe probe, SyncroMode mode) async {
    await _http.requestJson(
      'POST',
      _u('/api/v1/syncro/agents/${config.agentId}/heartbeat'),
      body: {
        'active_mode': mode.apiValue,
        'local_tools_detected': probe.detectedTools,
        'metadata': {'hostname': probe.hostname, 'os': probe.osPlatform},
      },
    );
  }

  Stream<Map<String, dynamic>> connectLiveStream() {
    final channel = WebSocketChannel.connect(Uri.parse(config.wsUrl));
    return channel.stream.map((raw) {
      final decoded = jsonDecode(raw.toString());
      return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{'raw': raw};
    });
  }

  void dispose() => _http.close();
}
