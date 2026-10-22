import 'dart:convert';
import 'dart:io';
import 'dart:math';

/// A visit photo waiting to upload. It survives no signal, the app closing and the phone
/// restarting: the file and this record live in the app's own storage until the API has it.
class QueuedPhoto {
  QueuedPhoto({
    required this.ref,
    required this.visitId,
    required this.path,
    required this.lat,
    required this.lng,
    required this.takenAt,
    required this.caption,
    this.error,
  });

  /// Unique per photo. The API uses it (client_ref) so a retried upload is never stored twice.
  final String ref;
  final int visitId;
  final String path;
  final double lat;
  final double lng;
  final DateTime takenAt;
  final String caption;

  /// Set when the API refused the photo for good (not a connection problem).
  String? error;

  Map<String, dynamic> toJson() => {
        'ref': ref,
        'visitId': visitId,
        'path': path,
        'lat': lat,
        'lng': lng,
        'takenAt': takenAt.toUtc().toIso8601String(),
        'caption': caption,
        'error': error,
      };

  factory QueuedPhoto.fromJson(Map<String, dynamic> j) => QueuedPhoto(
        ref: j['ref'] as String,
        visitId: j['visitId'] as int,
        path: j['path'] as String,
        lat: (j['lat'] as num).toDouble(),
        lng: (j['lng'] as num).toDouble(),
        takenAt: DateTime.parse(j['takenAt'] as String),
        caption: j['caption'] as String? ?? '',
        error: j['error'] as String?,
      );

  static String newRef() {
    final rng = Random.secure();
    return List.generate(16, (_) => rng.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  }
}

/// The upload queue: one JSON file listing the photos, next to the photo files.
class PhotoQueue {
  PhotoQueue(this.dir);
  final Directory dir;

  File get _index => File('${dir.path}/queue.json');

  Future<List<QueuedPhoto>> all() async {
    if (!await _index.exists()) return [];
    try {
      final list = jsonDecode(await _index.readAsString()) as List;
      return [for (final j in list) QueuedPhoto.fromJson(j as Map<String, dynamic>)];
    } on FormatException {
      return [];
    }
  }

  Future<List<QueuedPhoto>> forVisit(int visitId) async => [for (final p in await all()) if (p.visitId == visitId) p];

  Future<void> _save(List<QueuedPhoto> items) async {
    await dir.create(recursive: true);
    final tmp = File('${_index.path}.tmp');
    await tmp.writeAsString(jsonEncode([for (final p in items) p.toJson()]));
    await tmp.rename(_index.path);
  }

  /// Copies the camera's file into the queue folder (the camera's copy can be cleared by the OS).
  Future<QueuedPhoto> add({
    required int visitId,
    required String sourcePath,
    required double lat,
    required double lng,
    required String caption,
    DateTime? takenAt,
  }) async {
    await dir.create(recursive: true);
    final ref = QueuedPhoto.newRef();
    final kept = await File(sourcePath).copy('${dir.path}/$ref.jpg');
    final item = QueuedPhoto(
        ref: ref, visitId: visitId, path: kept.path, lat: lat, lng: lng, takenAt: takenAt ?? DateTime.now(), caption: caption);
    await _save([...await all(), item]);
    return item;
  }

  Future<void> update(QueuedPhoto item) async =>
      _save([for (final p in await all()) p.ref == item.ref ? item : p]);

  Future<void> remove(String ref) async {
    final items = await all();
    for (final p in items.where((p) => p.ref == ref)) {
      final f = File(p.path);
      if (await f.exists()) await f.delete();
    }
    await _save([for (final p in items) if (p.ref != ref) p]);
  }
}

/// Straight-line distance in metres (haversine). Photos must be taken at the home: the app
/// checks before queuing, and the API checks again.
double distanceM(double lat1, double lng1, double lat2, double lng2) {
  const r = 6371000.0;
  double rad(double d) => d * pi / 180;
  final dLat = rad(lat2 - lat1);
  final dLng = rad(lng2 - lng1);
  final a = sin(dLat / 2) * sin(dLat / 2) + cos(rad(lat1)) * cos(rad(lat2)) * sin(dLng / 2) * sin(dLng / 2);
  return 2 * r * asin(sqrt(a));
}
