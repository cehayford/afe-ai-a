import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'lister.dart';
import 'tenancies.dart';

// The landlord's side of protected payments and listings, from the "Afe Missing Features" canvas:
// offer a tenancy after a viewing, and edit or feature a listing.

/// Offer a tenancy after a completed viewing: move-in date and terms as chips; the amounts ticket
/// updates as they change (from the API's quote), and Send offer is pinned to the bottom.
class OfferScreen extends StatelessWidget {
  const OfferScreen({super.key, required this.viewing});
  final Viewing viewing;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('Offer a tenancy')),
    body: Loader<(TenancyConfig, Payee?)>(
      load: () async {
        final api = context.api;
        final config = TenancyConfig((await api.get<Json>('/tenancies/config')).data);
        final payee = (await api.get<Json?>('/me/payouts')).data;
        return (config, payee == null ? null : Payee(payee));
      },
      builder: (context, data, reload) {
        final (config, payee) = data;
        final a = context.afe;
        final head = Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: Row(
            children: [
              Initials(name: viewing.otherName, size: 40, soft: true),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(viewing.otherName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                    Text('${viewing.listingTitle} · viewed ${day(viewing.when)}', style: TextStyle(fontSize: 12.5, color: a.muted)),
                  ],
                ),
              ),
            ],
          ),
        );
        Widget gate(String lead, String text, [Widget? action]) => ListView(
          padding: const EdgeInsets.all(16),
          children: [head, Note(text, kind: NoteKind.warn, lead: lead), if (action != null) ...[const SizedBox(height: 12), action]],
        );
        if (!config.enabled) {
          return gate('Not open yet.', "Protected payments start once Afe's payment partner has its licence. You'll get an SMS when you can offer tenancies.");
        }
        if (viewing.status != 'completed') {
          return gate('After the viewing.', 'You can offer a tenancy once the viewing has happened and you marked that they came.');
        }
        if (payee == null) {
          return gate(
            'Add a payout account first,',
            'so Afe knows where to send the rent.',
            PrimaryButton(
              label: 'Add payout account',
              onPressed: () async {
                await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PayoutsScreen()));
                await reload();
              },
            ),
          );
        }
        return _OfferForm(viewing: viewing, config: config, payee: payee, head: head);
      },
    ),
  );
}

class _OfferForm extends StatefulWidget {
  const _OfferForm({required this.viewing, required this.config, required this.payee, required this.head});
  final Viewing viewing;
  final TenancyConfig config;
  final Payee payee;
  final Widget head;

  @override
  State<_OfferForm> createState() => _OfferFormState();
}

class _OfferFormState extends State<_OfferForm> {
  DateTime _moveIn = DateTime.now().add(const Duration(days: 7));
  int _lease = 12;
  int _advance = 6;
  int _deposit = 0;
  Quote? _quote;
  String? _error;
  bool _sending = false;
  Timer? _debounce;

  int get _cap => widget.config.capFor(_lease);

  Map<String, Object> get _terms => {
    'viewing_id': widget.viewing.id,
    'move_in_date': isoDay(_moveIn),
    'lease_months': _lease,
    'advance_months': _advance,
    'deposit_months': _deposit,
  };

  @override
  void initState() {
    super.initState();
    _advance = _advance.clamp(0, _cap);
    _requote();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _set(VoidCallback change) {
    setState(() {
      change();
      if (_advance > _cap) _advance = _cap;
    });
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 250), _requote);
  }

  Future<void> _requote() async {
    try {
      final q = Quote((await context.api.post<Json>('/tenancies/quote', _terms)).data);
      if (mounted) setState(() => (_quote = q, _error = null));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _send() async {
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final t = Tenancy((await context.api.post<Json>('/tenancies', _terms)).data);
      if (!mounted) return;
      toast(context, 'Offer sent to ${widget.viewing.otherName}.');
      await Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => TenancyScreen(reference: t.reference)));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.reasons.isEmpty ? e.message : '${e.message} ${e.reasons.join(' ')}');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final q = _quote;
    final free = q != null && q.feePesewas == 0;
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              widget.head,
              if (_error != null) ...[Note(_error!, kind: NoteKind.error), const SizedBox(height: 12)],
              const FieldLabel('Move-in date'),
              _DateField(
                value: _moveIn,
                onTap: () async {
                  final d = await showDatePicker(
                    context: context,
                    firstDate: DateTime.now(),
                    lastDate: DateTime.now().add(const Duration(days: 120)),
                    initialDate: _moveIn,
                  );
                  if (d != null) _set(() => _moveIn = d);
                },
              ),
              const SizedBox(height: 14),
              const FieldLabel('Lease'),
              ChipRow<int>(items: const [(6, '6 months'), (12, '12 months'), (24, '24 months')], value: _lease, onChanged: (v) => _set(() => _lease = v)),
              const SizedBox(height: 14),
              FieldLabel('Advance rent (the law caps it at $_cap months)'),
              ChipRow<int>(items: [for (var m = 0; m <= _cap; m++) (m, '$m')], value: _advance, onChanged: (v) => _set(() => _advance = v)),
              const SizedBox(height: 14),
              const FieldLabel('Deposit'),
              ChipRow<int>(
                items: [for (var m = 0; m <= widget.config.maxDeposit; m++) (m, m == 0 ? 'None' : '$m month${m > 1 ? 's' : ''}')],
                value: _deposit,
                onChanged: (v) => _set(() => _deposit = v),
              ),
              const SizedBox(height: 16),
              _Ticket(
                top: [
                  Text('AMOUNTS', style: AfeType.label(a.muted, size: 10.5)),
                  _line('Held until move-in', q == null ? '…' : cedis(q.held)),
                  _line(
                    'Protection fee',
                    q == null ? '…' : (free ? 'Free · launch offer' : '${cedis(q.fee)} · ${q.feePayer == 'landlord' ? 'you pay' : q.feePayer == 'split' ? 'split' : 'tenant pays'}'),
                    valueColor: free ? a.ok : null,
                  ),
                  _line('Tenant pays', q == null ? '…' : cedis(q.charge)),
                ],
                bottom: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      const Expanded(child: Text('You receive', style: TextStyle(fontWeight: FontWeight.w600))),
                      Text(q == null ? '…' : cedis(q.payout), style: AfeType.heading(26, color: a.accent)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'To ${widget.payee.masked}, after ${widget.viewing.otherName.split(' ').first} confirms they\'ve moved in.',
                    style: TextStyle(fontSize: 12.5, color: a.muted),
                  ),
                ],
              ),
            ],
          ),
        ),
        BottomActionBar(
          label: 'Send offer',
          busy: _sending,
          price: q == null ? null : cedis(q.charge),
          priceNote: 'paid into protection',
          onPressed: q == null ? null : _send,
        ),
      ],
    );
  }

  Widget _line(String label, String value, {Color? valueColor}) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Row(
      children: [
        Expanded(child: Text(label, style: const TextStyle(fontSize: 14.5))),
        Text(value, style: TextStyle(fontSize: 14.5, color: valueColor, fontWeight: valueColor == null ? FontWeight.w400 : FontWeight.w600)),
      ],
    ),
  );
}

/// A date shown like a field; tapping opens the date picker.
class _DateField extends StatelessWidget {
  const _DateField({required this.value, required this.onTap});
  final DateTime value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Material(
      color: a.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.inputRadius), side: BorderSide(color: a.line)),
      child: InkWell(
        customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.inputRadius)),
        onTap: onTap,
        child: SizedBox(
          height: 48,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Row(
              children: [
                Expanded(child: Text(day(value), style: const TextStyle(fontSize: 16))),
                Icon(Icons.calendar_today_outlined, size: 20, color: a.muted),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The amounts ticket: a white card torn across by a dashed line with punched notches.
class _Ticket extends StatelessWidget {
  const _Ticket({required this.top, required this.bottom});
  final List<Widget> top;
  final List<Widget> bottom;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      decoration: BoxDecoration(
        color: a.surface,
        borderRadius: BorderRadius.circular(a.cardRadius + 2),
        border: Border.all(color: a.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(padding: const EdgeInsets.fromLTRB(16, 14, 16, 14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: top)),
          SizedBox(
            height: 22,
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                Positioned.fill(left: 14, right: 14, child: CustomPaint(painter: _DashLine(a.line))),
                Positioned(left: -1, top: 0, child: _Notch(color: a.bg, line: a.line, left: true)),
                Positioned(right: -1, top: 0, child: _Notch(color: a.bg, line: a.line, left: false)),
              ],
            ),
          ),
          Padding(padding: const EdgeInsets.fromLTRB(16, 10, 16, 16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: bottom)),
        ],
      ),
    );
  }
}

class _Notch extends StatelessWidget {
  const _Notch({required this.color, required this.line, required this.left});
  final Color color, line;
  final bool left;

  @override
  Widget build(BuildContext context) => Container(
    width: 12,
    height: 22,
    decoration: BoxDecoration(
      color: color,
      border: Border(
        top: BorderSide(color: line),
        bottom: BorderSide(color: line),
        left: left ? BorderSide.none : BorderSide(color: line),
        right: left ? BorderSide(color: line) : BorderSide.none,
      ),
      borderRadius: left
          ? const BorderRadius.horizontal(right: Radius.circular(12))
          : const BorderRadius.horizontal(left: Radius.circular(12)),
    ),
  );
}

class _DashLine extends CustomPainter {
  _DashLine(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..color = color
      ..strokeWidth = 2;
    final y = size.height / 2;
    for (double x = 0; x < size.width; x += 10) {
      canvas.drawLine(Offset(x, y), Offset((x + 6).clamp(0, size.width), y), p);
    }
  }

  @override
  bool shouldRepaint(_DashLine old) => old.color != color;
}

const _listingStatus = {
  'draft': ('Draft', PillTone.warn),
  'pending_review': ('Waiting for Afe', PillTone.warn),
  'live': ('Live', PillTone.ok),
  'paused': ('Paused', PillTone.quiet),
  'let': ('Let', PillTone.quiet),
  'archived': ('Archived', PillTone.quiet),
};

/// Every listing on this account, newest first, from GET /me/listings: status, why Afe paused or
/// returned it, and a way into each one.
class MyListingsScreen extends StatefulWidget {
  const MyListingsScreen({super.key});

  @override
  State<MyListingsScreen> createState() => _MyListingsScreenState();
}

class _MyListingsScreenState extends State<MyListingsScreen> {
  String _show = 'all';

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('Listings')),
    body: Loader<List<Listing>>(
      load: () async => [for (final l in (await context.api.get<List>('/me/listings')).data) Listing(l as Json)],
      builder: (context, listings, reload) {
        final a = context.afe;
        bool shown(Listing l) => switch (_show) {
          'live' => l.status == 'live',
          'waiting' => l.status == 'draft' || l.status == 'pending_review',
          'other' => l.status != 'live' && l.status != 'draft' && l.status != 'pending_review',
          _ => true,
        };
        final rows = listings.where(shown).toList();
        return RefreshIndicator(
          onRefresh: reload,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const ScreenTitle('Listings', lede: 'Edit, feature or take down a listing. A live listing you edit goes back to Afe for a quick check.'),
              const SizedBox(height: 14),
              if (listings.isEmpty)
                EmptyState(
                  title: 'No listings yet',
                  body: "List a home once it's verified: add it, upload the ownership papers, and book the visit.",
                  action: SmallButton(
                    label: 'Your homes',
                    kind: SmallKind.primary,
                    onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ListerHomesScreen())),
                  ),
                )
              else ...[
                ChipRow<String>(
                  items: [
                    ('all', 'All ${listings.length}'),
                    ('live', 'Live'),
                    ('waiting', 'Drafts and checks'),
                    ('other', 'Paused or let'),
                  ],
                  value: _show,
                  onChanged: (v) => setState(() => _show = v),
                ),
                const SizedBox(height: 12),
                if (rows.isEmpty) Text('None here.', style: TextStyle(color: a.muted)),
                for (final l in rows) ...[
                  _MyListingCard(
                    listing: l,
                    onTap: () async {
                      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ListingEditScreen(listingId: l.id)));
                      await reload();
                    },
                  ),
                  const SizedBox(height: 10),
                ],
              ],
            ],
          ),
        );
      },
    ),
  );
}

class _MyListingCard extends StatelessWidget {
  const _MyListingCard({required this.listing, required this.onTap});
  final Listing listing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final l = listing;
    final (label, tone) = _listingStatus[l.status] ?? (l.status, PillTone.quiet);
    return Pressable(
      scale: 0.98,
      child: Card(
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(a.cardRadius - 4),
                  child: SizedBox.square(dimension: 72, child: NetPhoto(l.coverUrl, semanticLabel: l.title)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l.title, style: AfeType.heading(16, color: a.ink, height: 1.15)),
                      const SizedBox(height: 2),
                      Text('${l.reference} · ${cedis(l.rent)} / month', style: AfeType.mono(11.5, color: a.muted)),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          StatusPill(label, tone: tone),
                          if (l.featured) const StatusPill('Featured', tone: PillTone.brand),
                        ],
                      ),
                      if (l.statusReason.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(l.statusReason, style: TextStyle(fontSize: 12.5, color: a.muted)),
                      ],
                    ],
                  ),
                ),
                Icon(Icons.chevron_right, color: a.muted),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// One listing: feature it, edit it (a live listing goes back to Afe for a check), submit a
/// draft, or take it down.
class ListingEditScreen extends StatelessWidget {
  const ListingEditScreen({super.key, required this.listingId});
  final int listingId;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('Listing')),
    body: Loader<(ListingDetail, Json)>(
      load: () async {
        final api = context.api;
        final l = ListingDetail((await api.get<Json>('/properties/listings/$listingId')).data);
        final pricing = (await api.get<Json>('/pricing')).data;
        return (l, pricing);
      },
      builder: (context, data, reload) => _ListingForm(listing: data.$1, pricing: data.$2, reload: reload),
    ),
  );
}

class _ListingForm extends StatefulWidget {
  const _ListingForm({required this.listing, required this.pricing, required this.reload});
  final ListingDetail listing;
  final Json pricing;
  final Future<void> Function() reload;

  @override
  State<_ListingForm> createState() => _ListingFormState();
}

class _ListingFormState extends State<_ListingForm> {
  late final _title = TextEditingController(text: widget.listing.title);
  late final _description = TextEditingController(text: widget.listing.description);
  late final _rent = TextEditingController(text: '${widget.listing.rentPesewas ~/ 100}');
  late int _advance = widget.listing.advanceMonths;
  late int _minLease = widget.listing.minLease;
  late DateTime _from = widget.listing.availableFrom ?? DateTime.now();
  bool _dirty = false;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    for (final c in [_title, _description, _rent]) {
      c.addListener(() {
        if (!_dirty) setState(() => _dirty = true);
      });
    }
  }

  @override
  void dispose() {
    for (final c in [_title, _description, _rent]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action, String done) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      if (!mounted) return;
      toast(context, done);
      await widget.reload();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.reasons.isEmpty ? e.message : '${e.message} ${e.reasons.join(' ')}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() => _run(() async {
    final l = widget.listing;
    await context.api.patch('/properties/listings/${l.id}', {
      if (_title.text.trim() != l.title) 'title': _title.text.trim(),
      if (_description.text.trim() != l.description) 'description': _description.text.trim(),
      if (_rent.text.trim() != '${l.rentPesewas ~/ 100}') 'rent_ghs': _rent.text.trim(),
      if (_advance != l.advanceMonths) 'advance_months': _advance,
      if (_minLease != l.minLease) 'min_lease_months': _minLease,
      if (l.availableFrom == null || isoDay(_from) != isoDay(l.availableFrom!)) 'available_from': isoDay(_from),
    });
    _dirty = false;
  }, widget.listing.status == 'live' ? 'Saved. Afe checks the change before it shows again.' : 'Saved.');

  Future<void> _feature() => _run(() async {
    final pay = (await context.api.post<Json>('/properties/listings/${widget.listing.id}/feature')).data;
    final url = '${pay['checkout_url'] ?? ''}';
    // Waived during the launch offer; otherwise the partner's checkout opens.
    if (pay['status'] == 'pending' && url.isNotEmpty) await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  }, 'Featured listing started.');

  Future<void> _takeDown() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Take this listing down?'),
        content: const Text("Renters stop seeing it at once. You can't put the same listing back; you'd create a new one."),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep it')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Take down')),
        ],
      ),
    );
    if (yes == true) await _run(() => context.api.post('/properties/listings/${widget.listing.id}/archive'), 'Listing taken down.');
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final l = widget.listing;
    final (statusLabel, statusTone) = _listingStatus[l.status] ?? (l.status, PillTone.quiet);
    final featuredNow = l.featuredUntil != null && l.featuredUntil!.isAfter(DateTime.now());
    final featuredFee = (widget.pricing['featured_fee_pesewas'] as num?)?.toInt() ?? 0;
    final featuredDays = (widget.pricing['featured_days'] as num?)?.toInt() ?? 0;
    final editable = l.status != 'let' && l.status != 'archived';
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                          decoration: BoxDecoration(color: a.brand, borderRadius: BorderRadius.circular(4)),
                          child: Text(l.reference, style: AfeType.mono(11, color: a.onBrand)),
                        ),
                        const SizedBox(height: 6),
                        Text(l.title, style: AfeType.heading(22, color: a.ink, height: 1.15)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  StatusPill(statusLabel, tone: statusTone),
                ],
              ),
              if (l.statusReason.isNotEmpty) ...[const SizedBox(height: 6), Text(l.statusReason, style: TextStyle(fontSize: 13, color: a.muted))],
              const SizedBox(height: 14),
              if (_error != null) ...[Note(_error!, kind: NoteKind.error), const SizedBox(height: 12)],
              if (l.status == 'live')
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(color: a.amberSoft, borderRadius: BorderRadius.circular(a.cardRadius)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(color: a.amber, borderRadius: BorderRadius.circular(4)),
                            child: Text('FEATURED', style: AfeType.label(const Color(0xFF15211E), size: 11)),
                          ),
                          const SizedBox(width: 8),
                          Text(featuredNow ? 'Until ${day(l.featuredUntil)}' : 'Not featured', style: TextStyle(fontSize: 13, color: a.warn, fontWeight: FontWeight.w600)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Featured homes show first in search for $featuredDays days, with a Featured badge. '
                        '${featuredFee == 0 ? 'Free during the launch offer.' : 'It costs ${ghs(featuredFee)}.'}',
                        style: const TextStyle(fontSize: 14, height: 1.45),
                      ),
                      if (!featuredNow) ...[
                        const SizedBox(height: 10),
                        Pressable(
                          child: SizedBox(
                            width: double.infinity,
                            child: FilledButton(
                              style: FilledButton.styleFrom(backgroundColor: a.amber, foregroundColor: const Color(0xFF15211E)),
                              onPressed: _busy ? null : _feature,
                              child: const Text('Feature this listing'),
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              if (l.status == 'draft') ...[
                Note('Submit it when you are happy with it. Afe checks every listing before it goes live.', kind: NoteKind.info, lead: 'Draft.'),
                const SizedBox(height: 8),
                PrimaryButton(
                  label: 'Submit for review',
                  busy: _busy,
                  onPressed: () => _run(() => context.api.post('/properties/listings/${l.id}/submit'), 'Sent to Afe for a check.'),
                ),
              ],
              if (editable) ...[
                const SizedBox(height: 16),
                const FieldLabel('Title'),
                TextField(controller: _title, maxLength: 90, buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null),
                const SizedBox(height: 12),
                const FieldLabel('Description'),
                TextField(controller: _description, minLines: 3, maxLines: 8),
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const FieldLabel('Rent / month'),
                          TextField(controller: _rent, keyboardType: TextInputType.number, style: AfeType.heading(17), decoration: const InputDecoration(prefixText: 'GH₵ ')),
                        ],
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const FieldLabel('Available from'),
                          _DateField(
                            value: _from,
                            onTap: () async {
                              final d = await showDatePicker(
                                context: context,
                                firstDate: DateTime.now().subtract(const Duration(days: 1)),
                                lastDate: DateTime.now().add(const Duration(days: 365)),
                                initialDate: _from.isBefore(DateTime.now()) ? DateTime.now() : _from,
                              );
                              if (d != null) setState(() => (_from = d, _dirty = true));
                            },
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                const FieldLabel('Months in advance'),
                ChipRow<int>(items: [for (var m = 1; m <= 6; m++) (m, '$m')], value: _advance, onChanged: (v) => setState(() => (_advance = v, _dirty = true))),
                const SizedBox(height: 12),
                const FieldLabel('Shortest lease'),
                Segmented<int>(
                  items: const [(6, '6 months'), (12, '12 months'), (24, '24 months')],
                  value: _minLease,
                  onChanged: (v) => setState(() => (_minLease = v, _dirty = true)),
                ),
                if (l.status == 'live') ...[
                  const SizedBox(height: 10),
                  Text('Any change to a live listing sends it back to Afe for a check before it shows again.', style: TextStyle(fontSize: 12.5, color: a.muted)),
                ],
              ],
            ],
          ),
        ),
        if (editable)
          Container(
            decoration: BoxDecoration(color: a.bar, border: Border(top: BorderSide(color: a.line))),
            padding: EdgeInsets.fromLTRB(16, 12, 16, 12 + MediaQuery.paddingOf(context).bottom),
            child: Row(
              children: [
                SmallButton(label: 'Take down', kind: SmallKind.danger, onPressed: _busy ? null : _takeDown),
                const SizedBox(width: 10),
                Expanded(child: PrimaryButton(label: 'Save changes', busy: _busy, onPressed: _dirty ? _save : null)),
              ],
            ),
          ),
      ],
    );
  }
}
