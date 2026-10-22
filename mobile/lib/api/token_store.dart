import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Sign-in tokens and this install's device ID. On a phone they live in the Keychain (iOS) or
/// encrypted storage (Android); tests use [MemoryTokenStore].
abstract class TokenStore {
  Future<String?> read(String key);
  Future<void> write(String key, String? value);

  static const access = 'afe_access';
  static const refresh = 'afe_refresh';
  static const device = 'afe_device';

  /// A random ID for this install, sent as X-Afe-Device-Id. Accounts used on the same device are
  /// linked in the fraud graph, exactly as the website's afe_dev cookie does.
  Future<String> deviceId() async {
    final existing = await read(device);
    if (existing != null && existing.length >= 16) return existing;
    final rng = Random.secure();
    final id = List.generate(16, (_) => rng.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
    await write(device, id);
    return id;
  }
}

class SecureTokenStore extends TokenStore {
  final _storage = const FlutterSecureStorage();

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String? value) =>
      value == null ? _storage.delete(key: key) : _storage.write(key: key, value: value);
}

class MemoryTokenStore extends TokenStore {
  final values = <String, String>{};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String? value) async =>
      value == null ? values.remove(key) : values[key] = value;
}
