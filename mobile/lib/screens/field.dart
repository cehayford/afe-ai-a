import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../field/queue.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';

/// A GPS fix, or a message the verifier can act on.
Future<Position> locate() async {
  if (!await Geolocator.isLocationServiceEnabled()) {
    throw ApiException(-1, 'location_off', 'Turn on location (GPS) to check in and take photos.');
  }
  var permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) permission = await Geolocator.requestPermission();
  if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
    throw ApiException(-1, 'location_denied', 'Afe needs your location to prove the visit happened at the home. Allow it in Settings.');
  }
  return Geolocator.getCurrentPosition(
    locationSettings: const LocationSettings(accuracy: LocationAccuracy.best, timeLimit: Duration(seconds: 25)),
  );
}

/// Today's visits, from the verifier canvas: one card per visit, the next one outlined in brand.
class WorklistScreen extends StatelessWidget {
  const WorklistScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text("Today's visits")),
      body: Loader<Worklist>(
        load: () async => Worklist((await context.api.get<Json>('/verify/worklist')).data),
        builder: (context, w, reload) {
          final open = w.assignments.where((x) => x.status == 'open').toList();
          final next = w.inProgress.isEmpty && open.isNotEmpty ? open.first.id : null;
          Future<void> go(Widget screen) async {
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
            await reload();
          }

          Widget card({required bool isNext, required String time, required String status, required PillTone tone, required String title, required String sub, Widget? extra, required VoidCallback onTap}) =>
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Pressable(
                  scale: 0.98,
                  child: Material(
                    color: a.surface,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(a.cardRadius),
                      side: BorderSide(color: isNext ? a.brand : a.line, width: isNext ? 2 : 1),
                    ),
                    child: InkWell(
                      customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.cardRadius)),
                      onTap: onTap,
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Expanded(child: Text(time, style: AfeType.mono(13, color: a.ink))),
                            StatusPill(status, tone: tone),
                          ]),
                          const SizedBox(height: 4),
                          Text(title, style: AfeType.heading(17, color: a.ink)),
                          const SizedBox(height: 2),
                          Text(sub, style: TextStyle(fontSize: 13, color: a.muted)),
                          if (extra != null) ...[const SizedBox(height: 6), extra],
                        ]),
                      ),
                    ),
                  ),
                ),
              );

          return ListView(padding: const EdgeInsets.all(16), children: [
            Text('${day(DateTime.now())} · ${open.length} to do', style: TextStyle(fontSize: 13, color: a.muted)),
            const SizedBox(height: 10),
            for (final v in w.inProgress)
              card(
                isNext: true,
                time: 'Started ${dayTime(v.startedAt)}',
                status: 'In progress',
                tone: PillTone.next,
                title: 'Visit in progress',
                sub: 'Continue: checks and photos',
                onTap: () => go(VisitScreen(visitId: v.id)),
              ),
            if (w.assignments.isEmpty && w.inProgress.isEmpty)
              const EmptyState(title: 'No visits assigned', body: 'New visits appear here when a reviewer plans them.'),
            for (final x in w.assignments)
              card(
                isNext: x.id == next,
                time: day(x.scheduledFor),
                status: x.status != 'open' ? 'Sent' : x.id == next ? 'Next' : 'Later',
                tone: x.status != 'open' ? PillTone.ok : x.id == next ? PillTone.next : PillTone.quiet,
                title: x.unit.label.isEmpty ? '${bedroomsLabel(x.unit.bedrooms)} · ${x.unit.propertyType}' : '${x.unit.label} · ${x.unit.propertyType}',
                sub: '${x.unit.digitalAddress}, ${x.unit.area} · Owner: ${x.landlordName}',
                extra: x.purpose == 'qa_recheck'
                    ? Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(color: a.amberSoft, borderRadius: BorderRadius.circular(99)),
                        child: Text("Second check · re-verify another verifier's pass", style: AfeType.mono(11, color: a.warn)),
                      )
                    : null,
                onTap: () => go(AssignmentScreen(assignment: x, radiusM: w.radiusM)),
              ),
          ]);
        },
      ),
    );
  }
}

class AssignmentScreen extends StatefulWidget {
  const AssignmentScreen({super.key, required this.assignment, required this.radiusM});
  final Assignment assignment;
  final int radiusM;

  @override
  State<AssignmentScreen> createState() => _AssignmentScreenState();
}

class _AssignmentScreenState extends State<AssignmentScreen> {
  bool _busy = false;
  String? _status;

  Future<void> _checkIn() async {
    final unit = widget.assignment.unit;
    setState(() {
      _busy = true;
      _status = 'Finding your location…';
    });
    try {
      final fix = await locate();
      final far = distanceM(fix.latitude, fix.longitude, unit.lat, unit.lng).round();
      if (far > widget.radiusM) {
        setState(() => _status =
            'You are about $far m from the home\'s pin (GPS accurate to ${fix.accuracy.round()} m). Go to the property and try again.');
        return;
      }
      if (!mounted) return;
      final visit = Visit((await context.api.post<Json>('/verify/visits', {
        'unit_id': unit.id,
        'lat': fix.latitude,
        'lng': fix.longitude,
      }))
          .data);
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => VisitScreen(visitId: visit.id)));
    } on ApiException catch (e) {
      setState(() => _status = e.message);
    } catch (e) {
      setState(() => _status = 'Couldn\'t get your location. Step outside or wait a moment, then try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = widget.assignment;
    final u = a.unit;
    final c = context.afe;
    return Scaffold(
      appBar: AfeAppBar(title: Text(u.label.isEmpty ? u.propertyType : '${u.label} · ${u.propertyType}')),
      bottomNavigationBar: BottomActionBar(label: 'Check in', busy: _busy, onPressed: _checkIn),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Panel(padded: true, children: [
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(day(a.scheduledFor), style: AfeType.mono(13, color: c.ink)),
            const SizedBox(height: 4),
            Text('${bedroomsLabel(u.bedrooms)} · ${u.bathrooms} bath${u.bathrooms == 1 ? '' : 's'} declared', style: AfeType.heading(18, color: c.ink)),
            const SizedBox(height: 4),
            Text('${u.digitalAddress}, ${u.area}${u.landmark.isEmpty ? '' : ' · near ${u.landmark}'}', style: TextStyle(color: c.muted, fontSize: 14)),
            Text('Owner: ${a.landlordName}', style: TextStyle(color: c.muted, fontSize: 14)),
            if (a.note.isNotEmpty) ...[const SizedBox(height: 8), Note(a.note)],
          ]),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: SecondaryButton(
              label: 'Directions',
              icon: Icons.directions_outlined,
              onPressed: () => launchUrl(Uri.parse('https://www.google.com/maps/dir/?api=1&destination=${u.lat},${u.lng}'),
                  mode: LaunchMode.externalApplication),
            ),
          ),
          if (a.landlordPhone != null) ...[
            const SizedBox(width: 10),
            Expanded(child: SecondaryButton(label: 'Call', icon: Icons.call_outlined, onPressed: () => launchUrl(Uri.parse('tel:${a.landlordPhone}')))),
          ],
        ]),
        const SizedBox(height: 12),
        Panel(padded: true, children: [
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Check in at the address', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
            const SizedBox(height: 4),
            Text('Uses your phone GPS. Must be within ${widget.radiusM} m of the pin.', style: TextStyle(fontSize: 13, color: c.muted)),
            if (_status != null) ...[const SizedBox(height: 10), Note(_status!, kind: _busy ? NoteKind.info : NoteKind.warn)],
          ]),
        ]),
      ]),
    );
  }
}

/// The visit: photos (queued on the phone until they upload), the checklist, then submit.
class VisitScreen extends StatefulWidget {
  const VisitScreen({super.key, required this.visitId});
  final int visitId;

  @override
  State<VisitScreen> createState() => _VisitScreenState();
}

class _VisitScreenState extends State<VisitScreen> with WidgetsBindingObserver {
  VisitDetail? _visit;
  PhotoQueue? _queue;
  List<QueuedPhoto> _queued = [];
  final List<Photo> _uploaded = [];
  final Map<String, bool?> _answers = {};
  String? _result;
  String _failReason = '';
  bool _sent = false;
  final _notes = TextEditingController();
  final _minutes = TextEditingController();
  final _fares = TextEditingController();
  String _caption = '';
  String? _status;
  bool _statusBad = false;
  bool _pumping = false;
  bool _submitting = false;
  String? _loadError;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _pump());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _pump();
  }

  Future<void> _load() async {
    try {
      final dir = await getApplicationSupportDirectory();
      _queue = PhotoQueue(Directory('${dir.path}/visit-photos'));
      if (!mounted) return;
      final v = VisitDetail((await context.api.get<Json>('/verify/visits/${widget.visitId}')).data);
      setState(() {
        _visit = v;
        _uploaded
          ..clear()
          ..addAll(v.photos);
        _caption = v.captions.isEmpty ? '' : v.captions.first;
      });
      await _refreshQueue();
      unawaited(_pump());
    } on ApiException catch (e) {
      setState(() => _loadError = e.message);
    }
  }

  Future<void> _refreshQueue() async {
    final q = await _queue!.forVisit(widget.visitId);
    if (mounted) setState(() => _queued = q);
  }

  void _say(String text, {bool bad = false}) => setState(() {
        _status = text;
        _statusBad = bad;
      });

  /// Upload what's waiting, oldest first. Stops at the first connection problem and tries
  /// again in 30 seconds, when the app comes back, or after the next photo.
  Future<void> _pump() async {
    if (_pumping || _queue == null || !mounted) return;
    _pumping = true;
    try {
      for (final item in (await _queue!.forVisit(widget.visitId)).where((p) => p.error == null)) {
        if (!mounted) return;
        try {
          final res = await context.api.upload<Json>('/verify/visits/${widget.visitId}/photos', fields: {
            'lat': '${item.lat}',
            'lng': '${item.lng}',
            'taken_at': item.takenAt.toUtc().toIso8601String(),
            'caption': item.caption,
            'client_ref': item.ref,
          }, files: {
            'photo': item.path,
          });
          await _queue!.remove(item.ref);
          final photo = Photo(res.data);
          if (!_uploaded.any((p) => p.id == photo.id)) _uploaded.add(photo);
          if (res.meta['duplicate'] == true) {
            _say('One photo matches a photo of another home. The reviewer will check it.', bad: true);
          } else {
            _say('Uploaded.');
          }
        } on ApiException catch (e) {
          if (e.retryable) {
            _say('Upload paused: no connection. Photos are saved on this phone and will retry.');
            break;
          }
          item.error = e.message;
          await _queue!.update(item);
        }
        await _refreshQueue();
      }
    } finally {
      _pumping = false;
      if (mounted) await _refreshQueue();
    }
  }

  Future<void> _takePhoto() async {
    final visit = _visit!;
    final shot = await ImagePicker().pickImage(source: ImageSource.camera, maxWidth: 1600, maxHeight: 1600, imageQuality: 85);
    if (shot == null) return;
    _say('Checking your location…');
    Position fix;
    try {
      fix = await locate();
    } on ApiException catch (e) {
      _say('Photo not kept: ${e.message}', bad: true);
      return;
    } catch (_) {
      _say('Photo not kept: couldn\'t get your location. Try again.', bad: true);
      return;
    }
    final far = distanceM(fix.latitude, fix.longitude, visit.unit.lat, visit.unit.lng).round();
    if (far > visit.radiusM) {
      _say('Photo not kept: you are about $far m from the home. Photos must be taken at the property.', bad: true);
      return;
    }
    await _queue!.add(visitId: visit.id, sourcePath: shot.path, lat: fix.latitude, lng: fix.longitude, caption: _caption);
    _say('Saved on this phone. Uploading…');
    await _refreshQueue();
    unawaited(_pump());
  }

  static const _reasons = {
    'ID_MISMATCH': 'Person is not the card holder',
    'DOCS_MISSING': 'No original document shown',
    'DOCS_SUSPECT': 'Document looks altered',
    'OWNER_UNREACHABLE': 'Owner could not be reached',
    'UNIT_NOT_FOUND': 'Address not found',
    'UNIT_OCCUPIED': 'Home is occupied',
    'UNIT_MISMATCH': "Home doesn't match the listing",
    'OTHER': 'Something else (explain in notes)',
  };

  bool get _allAnswered => _visit!.checklistItems.keys.every((k) => _answers[k] != null);
  bool get _allYes => _visit!.checklistItems.keys.every((k) => _answers[k] == true);
  int get _waiting => _queued.where((p) => p.error == null).length;
  bool get _ready =>
      _allAnswered && _result != null && _waiting == 0 && (_result == 'fail' || (_allYes && _uploaded.length >= _visit!.minPhotos));

  String get _submitLabel => !_allAnswered
      ? 'Answer every check'
      : _result == null
          ? 'Choose pass or fail'
          : _result == 'pass' && _uploaded.length + _waiting < _visit!.minPhotos
              ? 'Take at least ${_visit!.minPhotos} photos'
              : _waiting > 0
                  ? 'Wait for photos to upload'
                  : 'Send report';

  Future<void> _submit() async {
    final visit = _visit!;
    if (!_ready) return;
    setState(() => _submitting = true);
    final ok = await attempt(
      context,
      () => context.api.post('/verify/visits/${visit.id}/complete', {
        'checklist': {for (final k in visit.checklistItems.keys) k: _answers[k] == true},
        'notes': _notes.text,
        'travel_minutes': int.tryParse(_minutes.text),
        'transport_ghs': double.tryParse(_fares.text),
        'result': _result,
        'fail_reason': _result == 'fail' && _failReason.isNotEmpty ? _failReason : null,
      }),
    );
    if (!mounted) return;
    setState(() {
      _submitting = false;
      _sent = ok;
    });
  }

  @override
  Widget build(BuildContext context) {
    final v = _visit;
    final a = context.afe;
    if (v == null) {
      return Scaffold(
        appBar: const AfeAppBar(title: Text('Visit')),
        body: _loadError == null
            ? const Center(child: CircularProgressIndicator())
            : Padding(padding: const EdgeInsets.all(20), child: Note(_loadError!, kind: NoteKind.error)),
      );
    }
    final title = Text('${v.unit.label.isEmpty ? v.unit.propertyType : v.unit.label} · ${v.unit.area}');
    if (_sent) {
      return Scaffold(
        appBar: AfeAppBar(title: title),
        bottomNavigationBar: BottomActionBar(label: 'Back to route', onPressed: () => Navigator.of(context).pop()),
        body: ListView(padding: const EdgeInsets.fromLTRB(16, 24, 16, 16), children: [
          const Align(alignment: Alignment.centerLeft, child: DoneMark()),
          const SizedBox(height: 12),
          Text('Report sent', style: AfeType.heading(26, color: a.ink)),
          const SizedBox(height: 6),
          Text("A reviewer makes the final decision. You can't edit this report now; add notes by calling the review desk.",
              style: TextStyle(fontSize: 14.5, color: a.muted, height: 1.5)),
        ]),
      );
    }
    Widget card(List<Widget> children) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Panel(padded: true, children: [Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children)]),
        );
    final items = v.checklistItems.entries.toList();
    return Scaffold(
      appBar: AfeAppBar(title: title),
      bottomNavigationBar: BottomActionBar(label: _submitting ? 'Sending…' : _submitLabel, busy: _submitting, onPressed: _ready ? _submit : null),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (_status != null) ...[Note(_status!, kind: _statusBad ? NoteKind.warn : NoteKind.info), const SizedBox(height: 10)],
        card([
          const Text('Check in at the address', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
          const SizedBox(height: 8),
          YesNo(value: true, yesLabel: '✓ ${v.checkinDistanceM.round()} m away', onChanged: (_) {}),
        ]),
        for (final e in items)
          card([
            Text(e.value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
            const SizedBox(height: 8),
            YesNo(
              value: _answers[e.key],
              onChanged: (x) => setState(() {
                _answers[e.key] = x;
                if (!x && _result == 'pass') _result = null;
              }),
            ),
          ]),
        card([
          Row(children: [
            const Expanded(child: Text('Photos', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5))),
            Text('${_uploaded.length} / ${v.minPhotos}', style: AfeType.mono(12, color: a.muted)),
          ]),
          if (v.captions.isNotEmpty) ...[
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              initialValue: _caption,
              decoration: const InputDecoration(labelText: 'What is this photo of?'),
              items: [for (final c in v.captions) DropdownMenuItem(value: c, child: Text(c))],
              onChanged: (c) => setState(() => _caption = c ?? _caption),
            ),
          ],
          const SizedBox(height: 8),
          GridView.count(
            crossAxisCount: 4,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 6,
            crossAxisSpacing: 6,
            children: [
              for (final p in _uploaded)
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Stack(fit: StackFit.expand, children: [
                    NetPhoto(p.url, semanticLabel: p.caption),
                    Center(child: Text('✓', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700, shadows: const [Shadow(blurRadius: 3)]))),
                  ]),
                ),
              for (final q in _queued)
                Stack(fit: StackFit.expand, children: [
                  ClipRRect(borderRadius: BorderRadius.circular(8), child: Image.file(File(q.path), fit: BoxFit.cover)),
                  Container(
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: Colors.black38,
                      borderRadius: BorderRadius.circular(8),
                      border: q.error == null ? null : Border.all(color: a.crit, width: 2),
                    ),
                    child: q.error == null
                        ? const Icon(Icons.cloud_upload_outlined, color: Colors.white, size: 18)
                        : IconButton(
                            tooltip: 'Remove: ${q.error}',
                            icon: const Icon(Icons.close, color: Colors.white, size: 18),
                            onPressed: () async {
                              await _queue!.remove(q.ref);
                              await _refreshQueue();
                            },
                          ),
                  ),
                ]),
              for (var i = 0; i < (v.minPhotos - _uploaded.length - _queued.length).clamp(1, 8); i++)
                Semantics(
                  button: true,
                  label: 'Take a photo',
                  child: InkWell(
                    borderRadius: BorderRadius.circular(8),
                    onTap: _takePhoto,
                    child: DottedBox(color: a.line, child: Text('+', style: TextStyle(color: a.muted, fontSize: 16, fontWeight: FontWeight.w700))),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text('Camera only. Photos are stamped with time and GPS.', style: TextStyle(fontSize: 12.5, color: a.muted)),
        ]),
        card([
          const Text('Result', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
          const SizedBox(height: 8),
          YesNo(
            value: _result == null ? null : _result == 'pass',
            yesLabel: 'Pass',
            noLabel: 'Fail',
            yesEnabled: !_allAnswered || _allYes,
            onChanged: (x) => setState(() => _result = x ? 'pass' : 'fail'),
          ),
          if (_allAnswered && !_allYes) ...[
            const SizedBox(height: 6),
            Text('A "No" answer means the visit fails.', style: TextStyle(fontSize: 12.5, color: a.muted)),
          ],
          if (_result == 'fail') ...[
            const SizedBox(height: 10),
            DropdownButtonFormField<String>(
              initialValue: _failReason,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Why it failed'),
              items: [
                const DropdownMenuItem(value: '', child: Text('Reason (optional)')),
                for (final e in _reasons.entries) DropdownMenuItem(value: e.key, child: Text('${e.key} · ${e.value}', overflow: TextOverflow.ellipsis)),
              ],
              onChanged: (x) => setState(() => _failReason = x ?? ''),
            ),
          ],
          const SizedBox(height: 10),
          TextField(controller: _notes, minLines: 2, maxLines: 5, decoration: const InputDecoration(hintText: 'Notes for the reviewer')),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: TextField(controller: _minutes, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Travel (minutes)'))),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                controller: _fares,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Fares (GH₵)'),
              ),
            ),
          ]),
        ]),
      ]),
    );
  }
}

/// A dashed square: an empty photo slot.
class DottedBox extends StatelessWidget {
  const DottedBox({super.key, required this.color, required this.child});
  final Color color;
  final Widget child;

  @override
  Widget build(BuildContext context) => CustomPaint(painter: _DashPainter(color), child: Center(child: child));
}

class _DashPainter extends CustomPainter {
  _DashPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    final path = Path()..addRRect(RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(8)));
    for (final metric in path.computeMetrics()) {
      for (double d = 0; d < metric.length; d += 9) {
        canvas.drawPath(metric.extractPath(d, d + 5), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashPainter old) => old.color != color;
}
