import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

enum BreakerState { closed, open, halfOpen }

/// Client-side Circuit Breaker protecting the Flutter Desktop Agent from backend outages.
class SyncroCircuitBreaker {
  SyncroCircuitBreaker({
    this.failureThreshold = 3,
    this.recoveryTimeout = const Duration(seconds: 20),
  });

  final int failureThreshold;
  final Duration recoveryTimeout;

  BreakerState _state = BreakerState.closed;
  int _failures = 0;
  DateTime? _openedAt;

  BreakerState get state {
    if (_state == BreakerState.open &&
        _openedAt != null &&
        DateTime.now().difference(_openedAt!) >= recoveryTimeout) {
      _state = BreakerState.halfOpen;
    }
    return _state;
  }

  int get failureCount => _failures;

  Future<T> execute<T>(Future<T> Function() action) async {
    if (state == BreakerState.open) {
      throw StateError('Syncro desktop circuit breaker is OPEN');
    }
    try {
      final result = await action();
      _failures = 0;
      _state = BreakerState.closed;
      _openedAt = null;
      return result;
    } catch (_) {
      _failures += 1;
      if (_failures >= failureThreshold) {
        _state = BreakerState.open;
        _openedAt = DateTime.now();
      }
      rethrow;
    }
  }
}

/// Resilient HTTP JSON client with exponential backoff retries and Idempotency-Key propagation.
class ResilientHttpClient {
  ResilientHttpClient({
    http.Client? inner,
    SyncroCircuitBreaker? breaker,
    this.timeout = const Duration(seconds: 6),
    this.maxAttempts = 3,
  })  : _inner = inner ?? http.Client(),
        breaker = breaker ?? SyncroCircuitBreaker();

  final http.Client _inner;
  final SyncroCircuitBreaker breaker;
  final Duration timeout;
  final int maxAttempts;

  Future<dynamic> requestJson(
    String method,
    Uri uri, {
    Map<String, dynamic>? body,
    String? idempotencyKey,
  }) async {
    return breaker.execute(() async {
      Object? lastError;
      for (var attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          final headers = <String, String>{
            'Content-Type': 'application/json',
            if (idempotencyKey != null) 'Idempotency-Key': idempotencyKey,
          };
          late http.Response resp;
          if (method == 'GET') {
            resp = await _inner.get(uri, headers: headers).timeout(timeout);
          } else if (method == 'PUT') {
            resp = await _inner
                .put(uri, headers: headers, body: jsonEncode(body ?? {}))
                .timeout(timeout);
          } else {
            resp = await _inner
                .post(uri, headers: headers, body: jsonEncode(body ?? {}))
                .timeout(timeout);
          }

          if (resp.statusCode >= 200 && resp.statusCode < 300) {
            return resp.body.isEmpty ? <String, dynamic>{} : jsonDecode(resp.body);
          }
          if (resp.statusCode >= 400 && resp.statusCode < 500) {
            throw HttpException(resp.statusCode, resp.body);
          }
          throw HttpException(resp.statusCode, resp.body);
        } on HttpException catch (e) {
          // Do not retry 4xx policy/guardrail denials
          if (e.statusCode >= 400 && e.statusCode < 500) rethrow;
          lastError = e;
        } catch (e) {
          lastError = e;
        }
        if (attempt < maxAttempts - 1) {
          await Future<void>.delayed(Duration(milliseconds: 120 * (1 << attempt)));
        }
      }
      throw lastError ?? StateError('Request failed');
    });
  }

  void close() => _inner.close();
}

class HttpException implements Exception {
  const HttpException(this.statusCode, this.body);
  final int statusCode;
  final String body;

  @override
  String toString() => 'HTTP $statusCode: $body';
}
