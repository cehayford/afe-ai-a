import 'dart:convert';
import 'dart:io';

import 'package:afe/api/client.dart';
import 'package:afe/api/token_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response json(Object body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

void main() {
  test('reads data and meta from the envelope, and sends the device headers', () async {
    late http.Request sent;
    final tokens = MemoryTokenStore()..values[TokenStore.access] = 'access-1';
    final api = ApiClient(
      tokens: tokens,
      baseUrl: 'https://api.afe.test/',
      device: 'test-device',
      httpClient: MockClient((req) async {
        sent = req;
        return json({'data': [1, 2], 'meta': {'total': 2}, 'error': null});
      }),
    );
    final res = await api.get<List>('/properties/search', query: {'area': 'osu', 'bedrooms': ''});
    expect(res.data, [1, 2]);
    expect(res.meta['total'], 2);
    expect(sent.url.toString(), 'https://api.afe.test/api/v1/properties/search?area=osu');
    expect(sent.headers['Authorization'], 'Bearer access-1');
    expect(sent.headers['X-Client-Device'], 'test-device');
    expect(sent.headers['X-Afe-Device-Id'], matches(RegExp(r'^[0-9a-f]{32}$')));
    // The device ID is stable for this install.
    expect(await tokens.deviceId(), sent.headers['X-Afe-Device-Id']);
  });

  test('turns the error envelope into an ApiException with the API\'s message', () async {
    final api = ApiClient(
      tokens: MemoryTokenStore(),
      baseUrl: 'https://api.afe.test',
      httpClient: MockClient((_) async => json({
            'data': null,
            'error': {'code': 'rule_violation', 'message': 'Choose a time at least an hour from now.', 'reasons': ['when']},
          }, 409)),
    );
    await expectLater(
      api.post('/properties/AFE-1/viewings', {'when': 'x'}),
      throwsA(isA<ApiException>()
          .having((e) => e.message, 'message', 'Choose a time at least an hour from now.')
          .having((e) => e.code, 'code', 'rule_violation')
          .having((e) => e.reasons, 'reasons', ['when'])
          .having((e) => e.retryable, 'retryable', false)),
    );
  });

  test('refreshes an expired access token once, then retries the call', () async {
    final tokens = MemoryTokenStore()
      ..values[TokenStore.access] = 'old'
      ..values[TokenStore.refresh] = 'refresh-1';
    var refreshes = 0;
    final api = ApiClient(
      tokens: tokens,
      baseUrl: 'https://api.afe.test',
      httpClient: MockClient((req) async {
        if (req.url.path.endsWith('/auth/refresh')) {
          refreshes++;
          expect(jsonDecode(req.body), {'refresh_token': 'refresh-1'});
          return json({'data': {'status': 'signed_in', 'access_token': 'new', 'refresh_token': 'refresh-2'}});
        }
        return req.headers['Authorization'] == 'Bearer new'
            ? json({'data': {'ok': true}})
            : json({'error': {'code': 'unauthorized', 'message': 'Sign in again.'}}, 401);
      }),
    );
    final results = await Future.wait([api.get<Map>('/me'), api.get<Map>('/me/saved')]);
    expect(results.map((r) => r.data['ok']), [true, true]);
    expect(refreshes, 1, reason: 'two calls hitting an expired token share one refresh');
    expect(tokens.values[TokenStore.refresh], 'refresh-2');
  });

  test('a refused refresh signs the person out on this phone', () async {
    final tokens = MemoryTokenStore()
      ..values[TokenStore.access] = 'old'
      ..values[TokenStore.refresh] = 'revoked';
    var signedOut = false;
    final api = ApiClient(
      tokens: tokens,
      baseUrl: 'https://api.afe.test',
      httpClient: MockClient((req) async => json({'error': {'code': 'unauthorized', 'message': 'Sign in again.'}}, 401)),
    )..onSignedOut = () => signedOut = true;
    await expectLater(api.get('/me'), throwsA(isA<ApiException>().having((e) => e.status, 'status', 401)));
    expect(signedOut, isTrue);
    expect(tokens.values.containsKey(TokenStore.refresh), isFalse);
  });

  test('no connection is a retryable error with a plain message', () async {
    final api = ApiClient(
      tokens: MemoryTokenStore(),
      baseUrl: 'https://api.afe.test',
      httpClient: MockClient((_) async => throw const SocketException('no route')),
    );
    await expectLater(
      api.get('/verify/worklist'),
      throwsA(isA<ApiException>().having((e) => e.retryable, 'retryable', true).having((e) => e.status, 'status', 0)),
    );
  });
}
