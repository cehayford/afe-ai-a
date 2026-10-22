import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform, SocketException;

import 'package:http/http.dart' as http;

import '../config.dart';
import 'token_store.dart';

/// Something the API refused, with the message it gave (already written for people).
class ApiException implements Exception {
  ApiException(this.status, this.code, this.message, {this.reasons = const []});

  final int status;
  final String code;
  final String message;

  /// Extra detail, e.g. which fields were wrong.
  final List<String> reasons;

  /// No connection or a timeout: worth trying again, and the offline photo queue keeps waiting.
  bool get retryable => status == 0 || status >= 500 || status == 429;

  @override
  String toString() => message;
}

/// One API response: `data` and `meta` from Afe's {data, meta, error} envelope.
class ApiResult<T> {
  ApiResult(this.data, this.meta);
  final T data;
  final Map<String, dynamic> meta;
}

/// Talks to the Afe API: adds the access token, refreshes it once when it expires, and turns
/// the error envelope into [ApiException].
class ApiClient {
  ApiClient({required this.tokens, http.Client? httpClient, String? baseUrl, String? device})
      : _http = httpClient ?? http.Client(),
        baseUrl = (baseUrl ?? AppConfig.apiUrl).replaceAll(RegExp(r'/+$'), ''),
        _device = device ?? _defaultDevice();

  final TokenStore tokens;
  final http.Client _http;
  final String baseUrl;
  final String _device;
  Future<bool>? _refreshing;

  /// Called when the session can't be refreshed (signed out elsewhere, or expired).
  void Function()? onSignedOut;

  static String _defaultDevice() {
    try {
      return 'Afe app ${AppConfig.version} (${Platform.operatingSystem} ${Platform.operatingSystemVersion})';
    } catch (_) {
      return 'Afe app ${AppConfig.version}';
    }
  }

  Uri _uri(String path, [Map<String, String>? query]) {
    final uri = Uri.parse('$baseUrl/api/v1$path');
    final q = {...uri.queryParameters, ...?query}..removeWhere((_, v) => v.isEmpty);
    return q.isEmpty ? uri : uri.replace(queryParameters: q);
  }

  Future<Map<String, String>> _headers({bool json = false}) async {
    final token = await tokens.read(TokenStore.access);
    return {
      'Accept': 'application/json',
      'X-Client-Device': _device,
      'X-Afe-Device-Id': await tokens.deviceId(),
      if (json) 'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Future<ApiResult<T>> get<T>(String path, {Map<String, String>? query}) =>
      _send<T>(() async => _http.get(_uri(path, query), headers: await _headers()));

  Future<ApiResult<T>> post<T>(String path, [Object? body]) => _send<T>(() async =>
      _http.post(_uri(path), headers: await _headers(json: true), body: jsonEncode(body ?? const {})));

  Future<ApiResult<T>> patch<T>(String path, Object body) => _send<T>(
      () async => _http.patch(_uri(path), headers: await _headers(json: true), body: jsonEncode(body)));

  Future<ApiResult<T>> delete<T>(String path) =>
      _send<T>(() async => _http.delete(_uri(path), headers: await _headers()));

  /// Multipart upload (photos). [files] maps field name to (file path, filename).
  Future<ApiResult<T>> upload<T>(String path, {Map<String, String> fields = const {}, Map<String, String> files = const {}}) =>
      _send<T>(() async {
        final req = http.MultipartRequest('POST', _uri(path))
          ..headers.addAll(await _headers())
          ..fields.addAll(fields);
        for (final entry in files.entries) {
          req.files.add(await http.MultipartFile.fromPath(entry.key, entry.value));
        }
        return http.Response.fromStream(await _http.send(req));
      });

  Future<ApiResult<T>> _send<T>(Future<http.Response> Function() request, {bool retried = false}) async {
    http.Response res;
    try {
      res = await request().timeout(const Duration(seconds: 30));
    } on SocketException {
      throw ApiException(0, 'offline', 'No connection. Check your signal and try again.');
    } on TimeoutException {
      throw ApiException(0, 'timeout', 'Afe is taking too long to answer. Try again.');
    } on http.ClientException {
      throw ApiException(0, 'offline', 'No connection. Check your signal and try again.');
    }
    if (res.statusCode == 401 && !retried && await _refresh()) {
      return _send<T>(request, retried: true);
    }
    return _parse<T>(res);
  }

  ApiResult<T> _parse<T>(http.Response res) {
    Map<String, dynamic> body;
    try {
      body = res.body.isEmpty ? {} : jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException(res.statusCode, 'bad_response', 'Afe sent an answer the app couldn\'t read. Try again.');
    }
    final error = body['error'];
    if (res.statusCode >= 400 || error != null) {
      final e = (error as Map<String, dynamic>?) ?? {};
      throw ApiException(res.statusCode, '${e['code'] ?? 'error'}', '${e['message'] ?? 'Something went wrong. Try again.'}',
          reasons: [for (final r in (e['reasons'] as List? ?? const [])) '$r']);
    }
    return ApiResult<T>(body['data'] as T, (body['meta'] as Map<String, dynamic>?) ?? const {});
  }

  /// One refresh at a time, however many calls hit an expired token together.
  Future<bool> _refresh() {
    return _refreshing ??= () async {
      try {
        final refresh = await tokens.read(TokenStore.refresh);
        if (refresh == null) return false;
        final res = await _http.post(_uri('/auth/refresh'),
            headers: {'Content-Type': 'application/json', 'X-Client-Device': _device}, body: jsonEncode({'refresh_token': refresh}));
        if (res.statusCode != 200) {
          await clearSession();
          onSignedOut?.call();
          return false;
        }
        await saveSession(jsonDecode(res.body)['data'] as Map<String, dynamic>);
        return true;
      } catch (_) {
        return false;
      } finally {
        _refreshing = null;
      }
    }();
  }

  Future<void> saveSession(Map<String, dynamic> signIn) async {
    await tokens.write(TokenStore.access, signIn['access_token'] as String?);
    await tokens.write(TokenStore.refresh, signIn['refresh_token'] as String?);
  }

  Future<void> clearSession() async {
    await tokens.write(TokenStore.access, null);
    await tokens.write(TokenStore.refresh, null);
  }

  Future<bool> get hasSession async => (await tokens.read(TokenStore.refresh)) != null;
}
