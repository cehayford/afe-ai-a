import 'dart:io';

import 'package:afe/field/queue.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory tmp;

  setUp(() async => tmp = await Directory.systemTemp.createTemp('afe-queue-'));
  tearDown(() async => tmp.delete(recursive: true));

  test('photos survive a restart and leave once uploaded', () async {
    final shot = File('${tmp.path}/camera.jpg')..writeAsBytesSync([1, 2, 3]);
    final queue = PhotoQueue(Directory('${tmp.path}/queue'));
    final a = await queue.add(visitId: 7, sourcePath: shot.path, lat: 5.6, lng: -0.18, caption: 'Kitchen');
    await queue.add(visitId: 8, sourcePath: shot.path, lat: 5.6, lng: -0.18, caption: 'Front');

    // A new queue object reads the same files, as after the app restarts.
    final reopened = PhotoQueue(Directory('${tmp.path}/queue'));
    final waiting = await reopened.forVisit(7);
    expect(waiting.single.caption, 'Kitchen');
    expect(waiting.single.ref, a.ref);
    expect(File(waiting.single.path).existsSync(), isTrue, reason: 'the queue keeps its own copy of the photo');

    waiting.single.error = 'Not a photo';
    await reopened.update(waiting.single);
    expect((await queue.forVisit(7)).single.error, 'Not a photo');

    await reopened.remove(a.ref);
    expect(await queue.forVisit(7), isEmpty);
    expect(File(a.path).existsSync(), isFalse);
    expect(await queue.forVisit(8), hasLength(1));
  });

  test('refs are unique and distance is in metres', () {
    expect({for (var i = 0; i < 200; i++) QueuedPhoto.newRef()}, hasLength(200));
    // About 111 m per 0.001 degree of latitude.
    expect(distanceM(5.600, -0.18, 5.601, -0.18), closeTo(111, 1));
    expect(distanceM(5.6, -0.18, 5.6, -0.18), 0);
  });
}
