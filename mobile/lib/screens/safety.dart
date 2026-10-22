import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'homes.dart';

// Staying safe, from the "Afe Missing Features" canvas: report a scam, the rent index, an area.

/// Report a scam: what happened, their number and any Afe reference, money lost, and how to reach
/// you. No account needed.
class ReportScamScreen extends StatefulWidget {
  const ReportScamScreen({super.key, this.phone = '', this.reference = ''});
  final String phone;
  final String reference;

  @override
  State<ReportScamScreen> createState() => _ReportScamScreenState();
}

class _ReportScamScreenState extends State<ReportScamScreen> {
  final _what = TextEditingController();
  late final _phone = TextEditingController(text: widget.phone);
  late final _reference = TextEditingController(text: widget.reference);
  final _lost = TextEditingController();
  final _contact = TextEditingController();
  bool _busy = false;
  bool _sent = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _what.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    for (final c in [_what, _phone, _reference, _lost, _contact]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final lost = _lost.text.replaceAll(RegExp(r'[^0-9.]'), '');
      await context.api.post('/check/reports', {
        'what_happened': _what.text.trim(),
        'reported_phone': _phone.text.trim().isEmpty ? '' : phoneE164(_phone.text),
        'reported_reference': _reference.text.trim().toUpperCase(),
        'amount_lost_ghs': lost.isEmpty ? null : lost,
        'reporter_contact': _contact.text.trim(),
      });
      if (mounted) setState(() => _sent = true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.reasons.isEmpty ? e.message : '${e.message} ${e.reasons.join(' ')}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final ok = _what.text.trim().length >= 10;
    if (_sent) {
      return Scaffold(
        appBar: const AfeAppBar(title: Text('Report sent')),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
          children: [
            const Align(alignment: Alignment.centerLeft, child: DoneMark()),
            const SizedBox(height: 14),
            Text('Thank you. An Afe reviewer reads every report.', style: AfeType.heading(26, color: a.ink, height: 1.15)),
            const SizedBox(height: 10),
            Text(
              'If the number or listing is on Afe, an upheld report flags it for our trust team.',
              style: TextStyle(fontSize: 14.5, color: a.muted, height: 1.5),
            ),
            const SizedBox(height: 20),
            SecondaryButton(label: 'Done', onPressed: () => Navigator.of(context).maybePop()),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Report a scam')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const ScreenTitle(
            'Tell us what happened',
            lede: "Lost money, or asked to pay before a viewing? Reports help us warn other renters. You don't need an account.",
          ),
          const SizedBox(height: 16),
          if (_error != null) ...[Note(_error!, kind: NoteKind.error), const SizedBox(height: 12)],
          const FieldLabel('What happened'),
          TextField(
            controller: _what,
            minLines: 4,
            maxLines: 8,
            maxLength: 4000,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(hintText: 'Someone on Facebook asked for a GH₵ 500 viewing fee by MoMo...'),
          ),
          const SizedBox(height: 8),
          const FieldLabel('Their phone number', optional: true),
          PhoneField(controller: _phone),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const FieldLabel('Afe reference'),
                    TextField(
                      controller: _reference,
                      textCapitalization: TextCapitalization.characters,
                      style: AfeType.mono(15),
                      decoration: const InputDecoration(hintText: 'AFE-0142'),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const FieldLabel('Money lost'),
                    TextField(
                      controller: _lost,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
                      decoration: const InputDecoration(hintText: '0', prefixText: 'GH₵ '),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          const FieldLabel('How we can reach you', optional: true),
          TextField(controller: _contact, decoration: const InputDecoration(hintText: 'Phone or email')),
          const SizedBox(height: 20),
          Pressable(
            child: SizedBox(
              width: double.infinity,
              child: FilledButton(
                style: FilledButton.styleFrom(backgroundColor: a.crit, foregroundColor: Colors.white),
                onPressed: ok && !_busy ? _send : null,
                child: _busy
                    ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
                    : const Text('Send report'),
              ),
            ),
          ),
          if (!ok) ...[
            const SizedBox(height: 6),
            Text('Say what happened in a sentence or two.', style: TextStyle(fontSize: 12.5, color: a.muted)),
          ],
        ],
      ),
    );
  }
}

const _sizes = [(0, 'Room'), (1, '1 bed'), (2, '2 beds'), (3, '3+')];

/// The rent index: median rent by neighbourhood for one home size, each area opening its page.
class RentIndexScreen extends StatefulWidget {
  const RentIndexScreen({super.key});

  @override
  State<RentIndexScreen> createState() => _RentIndexScreenState();
}

class _RentIndexScreenState extends State<RentIndexScreen> {
  int _size = 2;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Rent index')),
      body: Loader<RentIndex>(
        load: () async => RentIndex((await context.api.get<Json>('/properties/rent-index')).data),
        builder: (context, index, _) {
          final areas = index.areas;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('AS OF ${day(index.asOf).toUpperCase()}', style: AfeType.label(a.warn, size: 11)),
              const SizedBox(height: 6),
              ScreenTitle(
                'What rent really costs',
                lede: 'Median monthly rent from homes Afe visited, listed in the last ${index.periodDays} days. At least 3 homes behind every figure.',
              ),
              const SizedBox(height: 14),
              ChipRow<int>(items: _sizes, value: _size, onChanged: (v) => setState(() => _size = v)),
              const SizedBox(height: 12),
              if (areas.isEmpty)
                const EmptyState(title: 'Not enough homes yet', body: 'The index fills in as Afe verifies more homes.')
              else
                Panel(
                  children: [
                    for (final area in areas)
                      InkWell(
                        onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => AreaScreen(slug: area.slug))),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(area.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                                    Text(
                                      area.sizes[_size] == null ? 'Not enough homes yet' : '${area.sizes[_size]!.count} verified homes',
                                      style: AfeType.mono(11.5, color: a.muted),
                                    ),
                                  ],
                                ),
                              ),
                              Text(
                                area.sizes[_size] == null ? '—' : ghs(area.sizes[_size]!.median),
                                style: AfeType.heading(18, color: a.ink),
                              ),
                              const SizedBox(width: 6),
                              Text('›', style: TextStyle(color: a.muted, fontSize: 20)),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              const SizedBox(height: 14),
              const Note('A home far below these figures is a common scam. Check the number first.', kind: NoteKind.warn, lead: 'Careful.'),
            ],
          );
        },
      ),
    );
  }
}

/// One neighbourhood: its rent ranges by size, and the verified homes there now.
class AreaScreen extends StatelessWidget {
  const AreaScreen({super.key, required this.slug});
  final String slug;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Area')),
      body: Loader<AreaOverview>(
        load: () async => AreaOverview((await context.api.get<Json>('/properties/areas/$slug')).data),
        builder: (context, area, _) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            ScreenTitle('Renting in ${area.name}', lede: '${area.live} verified home${area.live == 1 ? '' : 's'} live now${area.city.isEmpty ? '' : ' · ${area.city}'}.'),
            const SizedBox(height: 14),
            if (area.ranges.isNotEmpty)
              Panel(
                title: 'Rent a month',
                children: [
                  for (final r in area.ranges)
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(bedroomsLabel(r.bedrooms), style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                                Text(
                                  '${ghs(r.low)} – ${ghs(r.high)} · ${r.source == 'afe' ? '${r.count} verified homes' : 'price survey'}',
                                  style: TextStyle(fontSize: 12.5, color: a.muted),
                                ),
                              ],
                            ),
                          ),
                          Text(ghs(r.median), style: AfeType.heading(18, color: a.ink)),
                        ],
                      ),
                    ),
                ],
              ),
            const SizedBox(height: 16),
            if (area.listings.isEmpty)
              const EmptyState(title: 'No homes live here yet', body: 'Save a search alert and we tell you when one is listed.')
            else ...[
              SectionLabel('Verified homes in ${area.name}'),
              const SizedBox(height: 8),
              for (final l in area.listings) ...[
                ListingCard(
                  listing: l,
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => HomeScreen(reference: l.reference))),
                ),
                const SizedBox(height: 10),
              ],
            ],
          ],
        ),
      ),
    );
  }
}
