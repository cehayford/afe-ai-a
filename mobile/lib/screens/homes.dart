import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:intl/intl.dart';
import 'package:latlong2/latlong.dart';

import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'auth.dart';
import 'messages.dart';
import 'safety.dart';

class SearchFilters {
  String area = '';
  String bedrooms = '';
  String maxRent = '';

  Map<String, String> get query => {'area': area, 'bedrooms': bedrooms, 'max_rent_ghs': maxRent};
  bool get any => area.isNotEmpty || bedrooms.isNotEmpty || maxRent.isNotEmpty;
}

void openHome(BuildContext context, String reference) =>
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => HomeScreen(reference: reference)));

/// Find a home, from the App Screen canvas: a map of price pins on top, bedroom chips, then the
/// verified homes. Area and rent are in the filter sheet (the sliders icon).
class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _filters = SearchFilters();
  List<Area> _areas = [];
  Key _results = UniqueKey();

  @override
  void initState() {
    super.initState();
    context.api
        .get<List>('/properties/areas')
        .then((r) {
          if (mounted) setState(() => _areas = [for (final a in r.data) Area(a as Json)]);
        })
        .catchError((_) {});
  }

  void _apply() => setState(() => _results = UniqueKey());

  Future<void> _editFilters() async {
    final changed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _FilterSheet(filters: _filters, areas: _areas),
    );
    if (changed == true) _apply();
  }

  Future<void> _saveAlert() async {
    final session = context.session;
    if (session.me == null) {
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SignInScreen()));
      return;
    }
    final phone = session.me!.user.phone != null;
    final channel = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ListTile(title: Text('Tell me when a home like this is verified')),
            if (phone)
              ListTile(
                leading: const Icon(Icons.chat_outlined),
                title: const Text('On WhatsApp'),
                onTap: () => Navigator.pop(context, 'whatsapp'),
              ),
            if (phone)
              ListTile(leading: const Icon(Icons.sms_outlined), title: const Text('By SMS'), onTap: () => Navigator.pop(context, 'sms')),
            ListTile(
              leading: const Icon(Icons.inbox_outlined),
              title: const Text('In my Afe inbox'),
              onTap: () => Navigator.pop(context, 'in_app'),
            ),
          ],
        ),
      ),
    );
    if (channel == null || !mounted) return;
    await attempt(
      context,
      () => context.api.post('/me/searches', {
        'area_slug': _filters.area.isEmpty ? null : _filters.area,
        'bedrooms': int.tryParse(_filters.bedrooms),
        'max_rent_ghs': int.tryParse(_filters.maxRent),
        'channel': channel,
      }),
      done: "Alert saved. We'll tell you when a matching home is verified.",
    );
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final areaName = _areas.where((x) => x.slug == _filters.area).map((x) => x.name).firstOrNull;
    return Scaffold(
      appBar: AfeAppBar(
        title: const Text('Find a home'),
        actions: [
          IconButton(tooltip: 'Area and rent', icon: const Icon(Icons.tune), onPressed: _editFilters),
          if (_filters.any)
            IconButton(tooltip: 'Get alerts for this search', icon: const Icon(Icons.notifications_active_outlined), onPressed: _saveAlert),
        ],
      ),
      body: Loader<List<Listing>>(
        key: _results,
        load: () async => [
          for (final l in (await context.api.get<List>('/properties/search', query: _filters.query)).data) Listing(l as Json),
        ],
        builder: (context, homes, _) => ListView(
          padding: EdgeInsets.zero,
          children: [
            SizedBox(height: 250, child: _HomesMap(homes: homes)),
            ChipRow<String>(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              items: const [('', 'Any'), ('1', '1 bed'), ('2', '2 beds'), ('3', '3+ beds'), ('0', 'Room')],
              value: _filters.bedrooms,
              onChanged: (v) {
                _filters.bedrooms = v;
                _apply();
              },
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '${homes.length} verified ${homes.length == 1 ? 'home' : 'homes'} in ${areaName ?? 'Accra'}'
                    '${_filters.maxRent.isEmpty ? '' : ' up to GH₵ ${_filters.maxRent}'}',
                    style: TextStyle(fontSize: 13, color: a.muted),
                  ),
                  const SizedBox(height: 10),
                  if (homes.isEmpty)
                    EmptyState(
                      title: 'No verified homes match yet',
                      body: 'Try another area or a higher budget, or get an alert when one is verified.',
                      action: _filters.any ? FilledButton.tonal(onPressed: _saveAlert, child: const Text('Get an alert')) : null,
                    ),
                  for (final h in homes) ...[
                    ListingCard(listing: h, onTap: () => openHome(context, h.reference)),
                    const SizedBox(height: 10),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilterSheet extends StatefulWidget {
  const _FilterSheet({required this.filters, required this.areas});
  final SearchFilters filters;
  final List<Area> areas;

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  late String _area = widget.filters.area;
  late String _rent = widget.filters.maxRent;

  @override
  Widget build(BuildContext context) {
    const caps = {'': 'Any rent', '2500': 'Up to GH₵ 2,500', '4000': 'Up to GH₵ 4,000', '6500': 'Up to GH₵ 6,500'};
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Neighbourhood', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              AfeChip(label: 'Any neighbourhood', selected: _area.isEmpty, onTap: () => setState(() => _area = '')),
              for (final a in widget.areas) AfeChip(label: a.name, selected: _area == a.slug, onTap: () => setState(() => _area = a.slug)),
            ],
          ),
          const SizedBox(height: 16),
          const Text('Rent a month', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final e in caps.entries) AfeChip(label: e.value, selected: _rent == e.key, onTap: () => setState(() => _rent = e.key)),
            ],
          ),
          const SizedBox(height: 20),
          PrimaryButton(
            label: 'Show homes',
            onPressed: () {
              widget.filters
                ..area = _area
                ..maxRent = _rent;
              Navigator.pop(context, true);
            },
          ),
        ],
      ),
    );
  }
}

/// Grey Esri tiles (dark in dark mode) and a price pin per home ("3.5k"). Pins sit on each home's
/// approximate position; the API never sends the exact one.
class _HomesMap extends StatelessWidget {
  const _HomesMap({required this.homes});
  final List<Listing> homes;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final placed = homes.where((h) => h.lat != null && h.lng != null).toList();
    final points = [for (final h in placed) LatLng(h.lat!, h.lng!)];
    String k(Listing h) {
      final n = double.tryParse(h.rent.replaceAll(RegExp(r'[^0-9.]'), '')) ?? 0;
      return '${(n / 1000).toStringAsFixed(1)}k';
    }

    return FlutterMap(
      options: MapOptions(
        initialCameraFit: points.length > 1
            ? CameraFit.coordinates(coordinates: points, padding: const EdgeInsets.all(30), maxZoom: 15)
            : null,
        initialCenter: points.isEmpty ? const LatLng(5.6, -0.18) : points.first,
        initialZoom: 12,
        backgroundColor: a.tint,
      ),
      children: [
        TileLayer(
          urlTemplate:
              'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${a.dark ? 'Dark' : 'Light'}_Gray_Base/MapServer/tile/{z}/{y}/{x}',
          maxZoom: 16,
          userAgentPackageName: 'com.afe.app',
        ),
        MarkerLayer(
          markers: [
            for (final h in placed)
              Marker(
                point: LatLng(h.lat!, h.lng!),
                width: 64,
                height: 28,
                child: Semantics(
                  button: true,
                  label: '${h.title}, ${h.rent} a month',
                  child: GestureDetector(
                    onTap: () => openHome(context, h.reference),
                    child: Center(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: a.brand,
                          borderRadius: BorderRadius.circular(99),
                          boxShadow: const [BoxShadow(color: Color(0x4D000000), blurRadius: 6, offset: Offset(0, 2))],
                        ),
                        child: Text(
                          k(h),
                          style: TextStyle(color: a.onBrand, fontWeight: FontWeight.w600, fontSize: 12),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
        const RichAttributionWidget(attributions: [TextSourceAttribution('Tiles © Esri')]),
      ],
    );
  }
}

/// One home, from the canvas: Afe's photos with Save, reference and title, the facts, the
/// verification record, and a bar with the rent and Book a viewing.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, required this.reference});
  final String reference;

  @override
  Widget build(BuildContext context) => Loader<ListingDetail>(
    load: () async => ListingDetail((await context.api.get<Json>('/properties/$reference')).data),
    builder: (context, home, reload) => _HomeBody(home: home, reload: reload),
  );
}

class _HomeBody extends StatefulWidget {
  const _HomeBody({required this.home, required this.reload});
  final ListingDetail home;
  final Future<void> Function() reload;

  @override
  State<_HomeBody> createState() => _HomeBodyState();
}

class _HomeBodyState extends State<_HomeBody> {
  late bool _saved = widget.home.saved;
  int _photo = 0;

  Future<bool> _requireSignIn() async {
    if (context.session.me != null) return true;
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SignInScreen()));
    return mounted && context.session.me != null;
  }

  Future<void> _toggleSave() async {
    if (!await _requireSignIn() || !mounted) return;
    final ref = widget.home.reference;
    final ok = await attempt(
      context,
      () => _saved ? context.api.delete('/properties/$ref/save') : context.api.post('/properties/$ref/save'),
    );
    if (ok) setState(() => _saved = !_saved);
  }

  Future<void> _message() async {
    if (!await _requireSignIn() || !mounted) return;
    final body = await _ask(context, title: 'Message ${widget.home.listerName}', hint: 'Is it still available? When can I view it?');
    if (body == null || !mounted) return;
    try {
      final thread = Thread((await context.api.post<Json>('/properties/${widget.home.reference}/enquiries', {'body': body})).data);
      if (mounted) openThread(context, thread.id);
    } on Exception catch (e) {
      if (mounted) toast(context, '$e');
    }
  }

  Future<void> _book() async {
    if (!await _requireSignIn() || !mounted) return;
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => BookViewingScreen(home: widget.home)));
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final h = widget.home;
    final photos = h.photos;
    return Scaffold(
      appBar: AfeAppBar(title: Text(h.reference)),
      bottomNavigationBar: BottomActionBar(label: 'Book a viewing', onPressed: _book, price: cedis(h.rent), priceNote: 'per month'),
      body: ListView(
        padding: EdgeInsets.zero,
        children: [
          SizedBox(
            height: 220,
            child: Stack(
              fit: StackFit.expand,
              children: [
                photos.isEmpty
                    ? NetPhoto(h.coverUrl)
                    : PageView(
                        onPageChanged: (i) => setState(() => _photo = i),
                        children: [for (final p in photos) NetPhoto(p.url, semanticLabel: p.caption)],
                      ),
                Positioned(
                  left: 16,
                  right: 16,
                  bottom: 12,
                  child: Row(
                    children: [
                      Text(
                        'photo taken by Afe${photos.isEmpty ? '' : ' · ${_photo + 1} / ${photos.length}'}',
                        style: AfeType.mono(
                          11,
                          color: Colors.white,
                        ).copyWith(shadows: const [Shadow(color: Color(0x99000000), blurRadius: 3)]),
                      ),
                      const Spacer(),
                      Pressable(
                        child: Material(
                          color: a.surface,
                          shape: const StadiumBorder(),
                          child: InkWell(
                            customBorder: const StadiumBorder(),
                            onTap: _toggleSave,
                            child: Container(
                              height: 34,
                              padding: const EdgeInsets.symmetric(horizontal: 12),
                              alignment: Alignment.center,
                              child: Text(
                                _saved ? 'Saved' : 'Save',
                                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: a.ink),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(h.reference, style: AfeType.mono(11.5, color: a.muted)),
                const SizedBox(height: 2),
                Text(h.title, style: AfeType.heading(26, color: a.ink)),
                Text('${h.area}, Accra', style: TextStyle(fontSize: 15, color: a.muted)),
                const SizedBox(height: 14),
                FactsGrid([
                  ('Beds', h.bedrooms == 0 ? 'Room' : '${h.bedrooms}'),
                  ('Type', h.propertyType),
                  ('From', shortDay(h.availableFrom)),
                ]),
                const SizedBox(height: 14),
                Panel(
                  title: 'Verification record',
                  children: [
                    for (final line in h.verification) CheckLine(line.text, date: line.date),
                    Padding(
                      padding: const EdgeInsets.all(14),
                      child: Text(
                        'AI also watches this listing for warning signs, like reused photos. It adds to these checks and never replaces them.',
                        style: TextStyle(fontSize: 13, color: a.muted),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Text(h.description, style: const TextStyle(fontSize: 15.5, height: 1.55)),
                const SizedBox(height: 10),
                Text(
                  '${h.advanceMonths} months advance (${h.advanceTotal}) · at least ${h.minLease} months · listed by ${h.listerName} (${h.listerRole.toLowerCase()})',
                  style: TextStyle(fontSize: 13.5, color: a.muted),
                ),
                if (h.rating != null) ...[
                  const SizedBox(height: 14),
                  Panel(
                    title: 'From tenants who moved in',
                    trailing: StatusPill('★ ${h.rating!.toStringAsFixed(1)} · ${h.reviewCount}', tone: PillTone.warn),
                    padded: true,
                    children: [
                      for (final r in h.reviews.take(3))
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${'★' * r.rating}${'☆' * (5 - r.rating)}  ${r.author}',
                              style: TextStyle(color: a.amber, fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 4),
                            Text(r.body),
                          ],
                        ),
                    ],
                  ),
                ],
                const SizedBox(height: 14),
                SecondaryButton(label: 'Ask ${h.listerName} a question', onPressed: _message),
                const SizedBox(height: 14),
                const Note('Pay only through Afe. Your rent is held until you confirm move-in.', kind: NoteKind.warn),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Book a viewing, from the canvas: pick a day, pick a time, confirm in the bottom bar. The landlord
/// confirms the request.
class BookViewingScreen extends StatefulWidget {
  const BookViewingScreen({super.key, required this.home});
  final ListingDetail home;

  @override
  State<BookViewingScreen> createState() => _BookViewingScreenState();
}

class _BookViewingScreenState extends State<BookViewingScreen> {
  static const _times = ['09:00', '11:00', '14:00', '16:00'];
  final _days = [for (var i = 1; i <= 5; i++) DateTime.now().add(Duration(days: i))];
  int _day = 1;
  int _time = 1;
  bool _busy = false;
  bool _booked = false;

  DateTime get _when {
    final d = _days[_day];
    final parts = _times[_time].split(':');
    // Ghana is on UTC all year.
    return DateTime.utc(d.year, d.month, d.day, int.parse(parts[0]), int.parse(parts[1]));
  }

  String get _slot => '${DateFormat('EEE d').format(_days[_day])}, ${_times[_time]}';

  Future<void> _confirm() async {
    setState(() => _busy = true);
    final ok = await attempt(
      context,
      () => context.api.post('/properties/${widget.home.reference}/viewings', {'when': _when.toIso8601String()}),
    );
    if (mounted) {
      setState(() {
        _busy = false;
        _booked = ok;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final h = widget.home;
    if (_booked) {
      return Scaffold(
        appBar: const AfeAppBar(title: Text('Book a viewing')),
        bottomNavigationBar: BottomActionBar(
          label: 'My viewings',
          onPressed: () => Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const ViewingsScreen())),
        ),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 20),
          children: [
            const Align(alignment: Alignment.centerLeft, child: DoneMark()),
            const SizedBox(height: 16),
            Text('Requested for $_slot', style: AfeType.heading(26, color: a.ink, height: 1.15)),
            const SizedBox(height: 8),
            Text(
              '${h.listerName} will confirm the time. We send the exact address and a reminder the day before. '
              'You should meet ${h.listerName}, the verified ${h.listerRole.toLowerCase()}.',
              style: TextStyle(fontSize: 14.5, color: a.muted, height: 1.5),
            ),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Book a viewing')),
      bottomNavigationBar: BottomActionBar(label: 'Confirm $_slot', onPressed: _confirm, busy: _busy),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 20),
        children: [
          Text('${h.title}, ${h.area}', style: AfeType.heading(24, color: a.ink, height: 1.15)),
          const SizedBox(height: 16),
          const Text('Day', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          ChipRow<int>(
            items: [for (var i = 0; i < _days.length; i++) (i, DateFormat('EEE d').format(_days[i]))],
            value: _day,
            onChanged: (v) => setState(() => _day = v),
          ),
          const SizedBox(height: 16),
          const Text('Time', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            childAspectRatio: 3.6,
            children: [
              for (var i = 0; i < _times.length; i++)
                AfeChip(label: _times[i], selected: _time == i, height: 44, onTap: () => setState(() => _time = i)),
            ],
          ),
        ],
      ),
    );
  }
}

Future<String?> _ask(BuildContext context, {required String title, String hint = ''}) {
  final text = TextEditingController();
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          TextField(
            controller: text,
            autofocus: true,
            maxLines: 4,
            minLines: 2,
            decoration: InputDecoration(hintText: hint),
          ),
          const SizedBox(height: 14),
          PrimaryButton(label: 'Send', onPressed: () => Navigator.pop(context, text.text.trim().isEmpty ? null : text.text.trim())),
        ],
      ),
    ),
  );
}

class SavedScreen extends StatelessWidget {
  const SavedScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('Saved homes')),
    body: Loader<List<Listing>>(
      load: () async => [for (final l in (await context.api.get<List>('/me/saved')).data) Listing(l as Json)],
      builder: (context, homes, _) => homes.isEmpty
          ? ListView(
              children: const [EmptyState(title: 'Nothing saved yet', body: 'Tap Save on any home to keep it here.')],
            )
          : ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: homes.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) => ListingCard(listing: homes[i], onTap: () => openHome(context, homes[i].reference)),
            ),
    ),
  );
}

class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('Home alerts')),
    body: Loader<List<SavedSearch>>(
      load: () async => [for (final s in (await context.api.get<List>('/me/searches')).data) SavedSearch(s as Json)],
      builder: (context, searches, reload) => searches.isEmpty
          ? ListView(
              children: const [
                EmptyState(title: 'No alerts yet', body: 'Search for homes, then tap the bell to hear when one like it is verified.'),
              ],
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Panel(
                  children: [
                    for (final s in searches)
                      ListTile(
                        title: Text(s.description),
                        subtitle: Text(
                          '${switch (s.channel) {
                            'sms' => 'By SMS',
                            'whatsapp' => 'On WhatsApp',
                            _ => 'In your inbox',
                          }} · ${s.alertsSent} sent',
                        ),
                        trailing: IconButton(
                          tooltip: 'Stop this alert',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () async {
                            if (await attempt(context, () => context.api.delete('/me/searches/${s.id}'), done: 'Alert stopped')) {
                              await reload();
                            }
                          },
                        ),
                      ),
                  ],
                ),
              ],
            ),
    ),
  );
}

/// "Check before you pay", from the canvas: one field, Check, and a verdict card.
class CheckScreen extends StatefulWidget {
  const CheckScreen({super.key});

  @override
  State<CheckScreen> createState() => _CheckScreenState();
}

class _CheckScreenState extends State<CheckScreen> {
  final _q = TextEditingController();
  CheckResult? _result;
  String? _error;
  bool _busy = false;

  Future<void> _check() async {
    if (_q.text.trim().isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = CheckResult((await context.api.get<Json>('/check', query: {'q': _q.text.trim()})).data);
      setState(() => _result = r);
    } on Exception catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final r = _result;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Scam check')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 24),
        children: [
          const ScreenTitle('Check before you pay', lede: 'Paste the phone number or Afe reference someone sent you.'),
          const SizedBox(height: 14),
          TextField(
            controller: _q,
            maxLength: 20,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _check(),
            onChanged: (_) {
              if (_result != null) setState(() => _result = null);
            },
            style: const TextStyle(fontSize: 17),
            decoration: const InputDecoration(hintText: 'Phone number or reference', counterText: ''),
          ),
          const SizedBox(height: 14),
          PrimaryButton(label: 'Check', busy: _busy, onPressed: _check),
          const SizedBox(height: 14),
          if (_error != null) Note(_error!, kind: NoteKind.error),
          if (r != null)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: a.surface,
                borderRadius: BorderRadius.circular(a.cardRadius),
                border: Border.all(color: r.verified ? a.ok : a.warn, width: 2),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (r.verified) const VerifiedBadge() else const WarnTag('Not verified by Afe'),
                  const SizedBox(height: 8),
                  Text(r.headline, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                  for (final d in r.details)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(d, style: TextStyle(color: a.muted, fontSize: 14)),
                    ),
                  for (final advice in r.advice)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text('• $advice', style: const TextStyle(fontSize: 14.5, height: 1.5)),
                    ),
                  for (final l in r.listings) ...[
                    const SizedBox(height: 10),
                    SizedBox(
                      height: 40,
                      child: FilledButton(
                        onPressed: () => openHome(context, l.reference),
                        child: Text('See ${l.reference}', style: const TextStyle(fontSize: 14)),
                      ),
                    ),
                  ],
                  if (!r.verified) ...[
                    const SizedBox(height: 12),
                    SmallButton(
                      label: 'Report this number',
                      kind: SmallKind.danger,
                      onPressed: () {
                        final q = _q.text.trim();
                        final isRef = q.toUpperCase().startsWith('AFE');
                        Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => ReportScamScreen(phone: isRef ? '' : q, reference: isRef ? q : ''),
                        ));
                      },
                    ),
                  ],
                ],
              ),
            ),
          const SizedBox(height: 20),
          Panel(
            children: [
              ListTile(
                title: const Text('Report a scam', style: TextStyle(fontWeight: FontWeight.w600)),
                subtitle: const Text('Lost money, or asked to pay before a viewing?'),
                trailing: const Text('›', style: TextStyle(fontSize: 20)),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ReportScamScreen())),
              ),
              ListTile(
                title: const Text('Rent index', style: TextStyle(fontWeight: FontWeight.w600)),
                subtitle: const Text('What rent really costs, by neighbourhood'),
                trailing: const Text('›', style: TextStyle(fontSize: 20)),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const RentIndexScreen())),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
