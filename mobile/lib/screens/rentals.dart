import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';

// Tenants and rent, from the "Afe Missing Features" canvas: the landlord's tenants with rent due,
// the tenant's "My home", and one rental's payments, repairs and agreement.

const _methods = {'momo': 'MoMo', 'bank': 'Bank', 'cash': 'Cash'};
const _methodLong = {'afe': 'Through Afe', 'momo': 'Mobile money', 'bank': 'Bank', 'cash': 'Cash'};

(String, PillTone) _due(Rental r) {
  if (!r.active) return ('Ended', PillTone.quiet);
  final due = r.nextDue;
  if (due == null) return ('Active', PillTone.ok);
  final today = DateTime.now();
  final start = DateTime(today.year, today.month, today.day);
  if (due.isBefore(start)) return ('Overdue since ${shortDay(due)}', PillTone.bad);
  if (due.isBefore(start.add(const Duration(days: 8)))) return ('Due ${day(due)}', PillTone.warn);
  return ('Due ${day(due)}', PillTone.quiet);
}

/// The landlord's tenants: three numbers, one card per tenant (tap to open), Add a tenant.
class TenantsScreen extends StatelessWidget {
  const TenantsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Tenants')),
      body: Loader<(List<Rental>, PlanInfo)>(
        load: () async {
          final api = context.api;
          final rentals = [for (final r in (await api.get<List>('/rentals')).data) Rental(r as Json)];
          return (rentals, PlanInfo((await api.get<Json>('/rentals/plan')).data));
        },
        builder: (context, data, reload) {
          final (rentals, plan) = data;
          final active = rentals.where((r) => r.active).toList();
          final today = DateTime.now();
          final start = DateTime(today.year, today.month, today.day);
          final overdue = active.where((r) => r.nextDue != null && r.nextDue!.isBefore(start)).length;
          final soon = active.where((r) => r.nextDue != null && !r.nextDue!.isBefore(start) && r.nextDue!.isBefore(start.add(const Duration(days: 8)))).length;
          Future<void> open(Widget w) async {
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => w));
            await reload();
          }

          Widget stat(String v, String l, {Color? color}) => Expanded(
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: a.surface,
                borderRadius: BorderRadius.circular(a.cardRadius),
                border: Border.all(color: a.line),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(v, style: AfeType.heading(22, color: color ?? a.accent)),
                  Text(l, style: TextStyle(fontSize: 12, color: a.muted)),
                ],
              ),
            ),
          );

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const ScreenTitle('Tenants and rent', lede: 'Record rent, and Afe makes the receipt. Tenants on Afe see it and can ask for repairs.'),
              const SizedBox(height: 14),
              Row(
                children: [
                  stat('${active.length}', 'Active'),
                  const SizedBox(width: 8),
                  stat('$soon', 'Due this week'),
                  const SizedBox(width: 8),
                  stat('$overdue', 'Overdue', color: overdue > 0 ? a.crit : null),
                ],
              ),
              const SizedBox(height: 12),
              if (rentals.isEmpty)
                const EmptyState(title: 'No tenants yet', body: 'Add one, or offer a tenancy after a viewing. Tenants who pay through Afe are added for you.'),
              for (final r in rentals) ...[
                _TenantCard(
                  rental: r,
                  onTap: () => open(RentalScreen(rentalId: r.id)),
                ),
                const SizedBox(height: 10),
              ],
              SecondaryButton(
                label: 'Add a tenant',
                icon: Icons.person_add_alt_outlined,
                onPressed: plan.full ? null : () => open(const AddTenantScreen()),
              ),
              if (plan.full) ...[
                const SizedBox(height: 6),
                Text('Your plan is full. Choose a bigger plan to add more tenants.', textAlign: TextAlign.center, style: TextStyle(fontSize: 12.5, color: a.muted)),
              ],
              const SizedBox(height: 16),
              _PlanCard(plan: plan, reload: reload),
            ],
          );
        },
      ),
    );
  }
}

/// The landlord's plan, as on the website's tenants page: how full it is, and Standard or Pro. A
/// paid plan opens the payment partner's checkout; during the launch offer it starts free.
class _PlanCard extends StatefulWidget {
  const _PlanCard({required this.plan, required this.reload});
  final PlanInfo plan;
  final Future<void> Function() reload;

  @override
  State<_PlanCard> createState() => _PlanCardState();
}

class _PlanCardState extends State<_PlanCard> {
  String? _busy;

  Future<void> _choose(String name) async {
    setState(() => _busy = name);
    try {
      final res = (await context.api.post<Json>('/rentals/plan/$name')).data;
      final checkout = '${res['checkout_url'] ?? ''}';
      if (checkout.isNotEmpty) {
        await launchUrl(Uri.parse(checkout), mode: LaunchMode.externalApplication);
      } else if (mounted) {
        toast(context, 'Plan active. You can add up to ${name == 'pro' ? 50 : 10} tenants.');
      }
      await widget.reload();
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final p = widget.plan;
    String price(String k) => p.launchOffer ? 'Free' : '${ghs(p.price(k))} / month';
    Widget option(String k, String name) {
      final on = p.plan == k;
      final shape = RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(a.cardRadius),
        side: BorderSide(color: on ? a.brand : a.line, width: on ? 2 : 1),
      );
      return Expanded(
        child: Semantics(
          button: true,
          selected: on,
          child: Pressable(
            child: Material(
              color: on ? a.tint : a.surface,
              shape: shape,
              child: InkWell(
                customBorder: shape,
                onTap: _busy == null ? () => _choose(k) : null,
                child: Padding(
                  padding: EdgeInsets.all(on ? 11 : 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(child: Text(name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15))),
                          if (_busy == k) SizedBox.square(dimension: 14, child: CircularProgressIndicator(strokeWidth: 2, color: a.brand)),
                        ],
                      ),
                      Text(price(k), style: TextStyle(fontSize: 13, color: a.muted)),
                      Text(k == 'pro' ? 'Up to 50 tenants' : 'Up to 10 tenants', style: TextStyle(fontSize: 12, color: a.muted)),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: a.surface, borderRadius: BorderRadius.circular(a.cardRadius), border: Border.all(color: a.line)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text('YOUR PLAN', style: AfeType.label(a.muted, size: 10.5))),
              if (p.launchOffer) StatusPill('Launch offer', tone: PillTone.ok),
            ],
          ),
          const SizedBox(height: 6),
          Text(p.label, style: AfeType.heading(18, color: a.ink)),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(99),
            child: LinearProgressIndicator(
              value: p.limit == 0 ? 0 : (p.used / p.limit).clamp(0, 1).toDouble(),
              minHeight: 6,
              backgroundColor: a.tint,
              color: p.full ? a.amber : a.brand,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '${p.used} of ${p.limit} tenants${p.periodEnd == null ? '' : ' · until ${day(p.periodEnd)}'}',
            style: TextStyle(fontSize: 12.5, color: a.muted),
          ),
          const SizedBox(height: 12),
          Row(children: [option('standard', 'Standard'), const SizedBox(width: 8), option('pro', 'Pro')]),
          const SizedBox(height: 8),
          Text(
            p.launchOffer ? 'Plans are free during the launch offer.' : "You pay on our payment partner's secure page. Afe never asks you to pay a personal number.",
            style: TextStyle(fontSize: 12, color: a.muted),
          ),
        ],
      ),
    );
  }
}

class _TenantCard extends StatelessWidget {
  const _TenantCard({required this.rental, required this.onTap});
  final Rental rental;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final r = rental;
    final (label, tone) = _due(r);
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(a.cardRadius),
      side: BorderSide(color: a.line),
    );
    return Pressable(
      scale: 0.98,
      child: Material(
        color: a.surface,
        shape: shape,
        child: InkWell(
          customBorder: shape,
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Initials(name: r.tenantName, size: 40, soft: true),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Text(r.tenantName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                          ),
                          StatusPill(label, tone: tone),
                        ],
                      ),
                      const SizedBox(height: 3),
                      Text('${r.home.isEmpty ? 'Home not on Afe' : r.home}${r.fromAfe ? ' · via Afe' : ''}', style: TextStyle(fontSize: 13, color: a.muted)),
                      Text('${ghs(r.rentPesewas)} / month · until ${shortDay(r.end)} ${r.end?.year ?? ''}', style: TextStyle(fontSize: 13, color: a.muted)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A tenant's "My home": homes where the landlord keeps the rent on Afe.
class MyHomesScreen extends StatelessWidget {
  const MyHomesScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('My home')),
    body: Loader<List<Rental>>(
      load: () async => [for (final r in (await context.api.get<List>('/rentals/my-homes')).data) Rental(r as Json)],
      builder: (context, homes, reload) {
        if (homes.length == 1) return RentalBody(rentalId: homes.first.id);
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const ScreenTitle('My home', lede: 'Homes where your landlord keeps your rent on Afe: receipts, repairs, agreements and renewals.'),
            const SizedBox(height: 14),
            if (homes.isEmpty)
              const EmptyState(title: 'Nothing here yet', body: 'When your landlord adds you on Afe with this phone number, your home appears here.'),
            for (final h in homes) ...[
              _HomeCard(
                rental: h,
                onTap: () async {
                  await Navigator.of(context).push(MaterialPageRoute(builder: (_) => RentalScreen(rentalId: h.id)));
                  await reload();
                },
              ),
              const SizedBox(height: 10),
            ],
          ],
        );
      },
    ),
  );
}

class _HomeCard extends StatelessWidget {
  const _HomeCard({required this.rental, required this.onTap});
  final Rental rental;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final (label, tone) = _due(rental);
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(a.cardRadius),
      side: BorderSide(color: a.line),
    );
    return Material(
      color: a.surface,
      shape: shape,
      child: InkWell(
        customBorder: shape,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(rental.home.isEmpty ? 'Home let by ${rental.landlordName}' : rental.home, style: AfeType.heading(18, color: a.ink)),
                  ),
                  StatusPill(label, tone: tone),
                ],
              ),
              const SizedBox(height: 4),
              Text('${ghs(rental.rentPesewas)} / month · landlord ${rental.landlordName}', style: TextStyle(fontSize: 13.5, color: a.muted)),
            ],
          ),
        ),
      ),
    );
  }
}

/// One rental, for the landlord or the tenant.
class RentalScreen extends StatelessWidget {
  const RentalScreen({super.key, required this.rentalId});
  final int rentalId;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('Rent')),
    body: RentalBody(rentalId: rentalId),
  );
}

/// The rental's header and facts, then segmented Payments / Repairs / Agreement / Renewals; the
/// landlord records payments from the bottom bar.
class RentalBody extends StatefulWidget {
  const RentalBody({super.key, required this.rentalId});
  final int rentalId;

  @override
  State<RentalBody> createState() => _RentalBodyState();
}

class _RentalBodyState extends State<RentalBody> {
  String _tab = 'payments';

  @override
  Widget build(BuildContext context) => Loader<RentalDetail>(
    load: () async => RentalDetail((await context.api.get<Json>('/rentals/${widget.rentalId}')).data),
    builder: (context, d, reload) {
      final a = context.afe;
      final r = d.rental;
      final (dueLabel, dueTone) = _due(r);
      final openRepairs = d.repairs.where((m) => m.status != 'done').length;
      final toSign = d.agreements.where((x) => d.landlord ? x.landlordSignedAt == null : x.tenantSignedAt == null).length;
      final body = switch (_tab) {
        'repairs' => _Repairs(d: d, reload: reload),
        'agreement' => _Agreements(d: d, reload: reload),
        'renewals' => _Renewals(d: d, reload: reload),
        _ => _Payments(d: d),
      };
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
                          Text(
                            d.landlord ? r.tenantName : (r.home.isEmpty ? 'Home let by ${r.landlordName}' : r.home),
                            style: AfeType.heading(24, color: a.ink),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            d.landlord ? (r.home.isEmpty ? 'Home not on Afe' : r.home) : 'Landlord ${r.landlordName}',
                            style: TextStyle(fontSize: 13.5, color: a.muted),
                          ),
                        ],
                      ),
                    ),
                    StatusPill(dueLabel, tone: dueTone),
                  ],
                ),
                const SizedBox(height: 12),
                FactsGrid([
                  ('Rent', ghs(r.rentPesewas)),
                  ('Paid', r.payEveryMonths == 1 ? 'Monthly' : 'Every ${r.payEveryMonths} mo'),
                  ('Until', '${shortDay(r.end)} ${r.end?.year ?? ''}'),
                ]),
                if (r.active && r.nextDue != null) ...[
                  const SizedBox(height: 10),
                  Panel(
                    children: [
                      DocumentRow(
                        label: 'Rent invoice for ${day(r.nextDue)}',
                        sub: d.landlord ? 'Send it to ${r.tenantName}' : 'The next rent due',
                        kind: 'rent_invoice',
                        docKey: '${r.id}',
                      ),
                    ],
                  ),
                ],
                if (d.landlord && !r.tenantOnAfe) ...[
                  const SizedBox(height: 10),
                  const Note("The tenant isn't on Afe with this number, so only you see this record.", kind: NoteKind.info, lead: 'Only you see this.'),
                ],
                const SizedBox(height: 14),
                Segmented<String>(
                  items: [
                    ('payments', 'Payments'),
                    ('repairs', openRepairs > 0 ? 'Repairs ($openRepairs)' : 'Repairs'),
                    ('agreement', toSign > 0 ? 'Sign ($toSign)' : 'Agreement'),
                    if (d.landlord || d.renewals.isNotEmpty) ('renewals', 'Renewals'),
                  ],
                  value: _tab,
                  onChanged: (v) => setState(() => _tab = v),
                ),
                const SizedBox(height: 14),
                body,
                if (d.landlord && r.active) ...[
                  const SizedBox(height: 20),
                  SecondaryButton(
                    label: 'Mark tenancy ended',
                    danger: true,
                    onPressed: () async {
                      final yes = await showDialog<bool>(
                        context: context,
                        builder: (context) => AlertDialog(
                          title: const Text('Mark this tenancy ended?'),
                          content: const Text('Reminders stop, and the record stays with its receipts.'),
                          actions: [
                            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep it')),
                            TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Mark ended')),
                          ],
                        ),
                      );
                      if (yes == true &&
                          context.mounted &&
                          await attempt(context, () => context.api.post('/rentals/${r.id}/end'), done: 'Tenancy marked as ended.')) {
                        await reload();
                      }
                    },
                  ),
                ],
              ],
            ),
          ),
          if (d.landlord && r.active)
            BottomActionBar(
              label: 'Record a payment',
              onPressed: () async {
                final saved = await showModalBottomSheet<bool>(
                  context: context,
                  isScrollControlled: true,
                  showDragHandle: true,
                  builder: (_) => _PaymentSheet(rental: r),
                );
                if (saved == true) {
                  await reload();
                  if (mounted) setState(() => _tab = 'payments');
                }
              },
            ),
        ],
      );
    },
  );
}

class _Payments extends StatelessWidget {
  const _Payments({required this.d});
  final RentalDetail d;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    if (d.payments.isEmpty) {
      return EmptyState(
        title: 'No payments recorded yet',
        body: d.landlord ? 'Record one and Afe makes the receipt.' : '${d.rental.landlordName} records each payment here.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Panel(
          children: [
            for (final p in d.payments)
              InkWell(
                onTap: () => openDocument(context, 'rent_receipt', '${d.rental.id}:${p.id}'),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(ghs(p.amountPesewas), style: AfeType.heading(17, color: a.ink)),
                            Text(
                              '${day(p.paidOn)} · ${_methodLong[p.method] ?? p.method} · ${p.coversMonths} month${p.coversMonths == 1 ? '' : 's'}${p.note.isEmpty ? '' : ' · ${p.note}'}',
                              style: TextStyle(fontSize: 12.5, color: a.muted),
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(p.receiptNo, style: AfeType.mono(11.5, color: a.accent)),
                          Text('RECEIPT PDF', style: AfeType.label(a.muted, size: 9.5)),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Text('Tap a payment to open its receipt.', style: TextStyle(fontSize: 12.5, color: a.muted)),
      ],
    );
  }
}

class _Repairs extends StatefulWidget {
  const _Repairs({required this.d, required this.reload});
  final RentalDetail d;
  final Future<void> Function() reload;

  @override
  State<_Repairs> createState() => _RepairsState();
}

class _RepairsState extends State<_Repairs> {
  final _title = TextEditingController();
  final _details = TextEditingController();
  XFile? _photo;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _title.addListener(() => setState(() {}));
    _details.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _title.dispose();
    _details.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() => _busy = true);
    final ok = await attempt(
      context,
      () => context.api.upload(
        '/rentals/${widget.d.rental.id}/maintenance',
        fields: {'title': _title.text.trim(), 'details': _details.text.trim()},
        files: {if (_photo != null) 'photo': _photo!.path},
      ),
      done: 'Repair request sent.',
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) {
      _title.clear();
      _details.clear();
      _photo = null;
      await widget.reload();
    }
  }

  Future<void> _status(Repair m, String status) async {
    final note = TextEditingController();
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(status == 'done' ? 'Mark "${m.title}" done' : 'Mark "${m.title}" in progress'),
        content: TextField(
          controller: note,
          decoration: const InputDecoration(hintText: 'Note for the tenant (optional)'),
          maxLength: 500,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Save')),
        ],
      ),
    );
    if (yes == true && mounted) {
      if (await attempt(
        context,
        () => context.api.post('/rentals/maintenance/${m.id}', {'status': status, 'note': note.text.trim()}),
        done: 'Repair updated.',
      )) {
        await widget.reload();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final d = widget.d;
    final ok = _title.text.trim().length >= 3 && _details.text.trim().length >= 10;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (d.repairs.isEmpty) Text('No repair requests.', style: TextStyle(color: a.muted)),
        for (final m in d.repairs) ...[
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: a.surface,
              borderRadius: BorderRadius.circular(a.cardRadius),
              border: Border.all(color: a.line),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(m.title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                    ),
                    StatusPill(
                      switch (m.status) {
                        'done' => 'Done',
                        'in_progress' => 'In progress',
                        _ => 'Open',
                      },
                      tone: switch (m.status) {
                        'done' => PillTone.ok,
                        'in_progress' => PillTone.brand,
                        _ => PillTone.warn,
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(m.details, style: const TextStyle(fontSize: 14, height: 1.4)),
                Text(dayTime(m.at), style: AfeType.mono(11, color: a.muted)),
                if (m.landlordNote.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(color: a.bg, borderRadius: BorderRadius.circular(a.inputRadius)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('LANDLORD', style: AfeType.label(a.muted)),
                        Text(m.landlordNote, style: const TextStyle(fontSize: 13.5)),
                      ],
                    ),
                  ),
                ],
                if (d.landlord && m.status != 'done') ...[
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      if (m.status == 'open') SmallButton(label: 'In progress', onPressed: () => _status(m, 'in_progress')),
                      SmallButton(label: 'Mark done', kind: SmallKind.primary, onPressed: () => _status(m, 'done')),
                    ],
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 10),
        ],
        const SizedBox(height: 6),
        SectionLabel(d.landlord ? 'Log a repair' : 'Ask for a repair'),
        const SizedBox(height: 8),
        const FieldLabel('What needs fixing'),
        TextField(
          controller: _title,
          maxLength: 120,
          buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
          decoration: const InputDecoration(hintText: 'Bathroom light'),
        ),
        const SizedBox(height: 10),
        const FieldLabel("Where and what's wrong"),
        TextField(controller: _details, minLines: 2, maxLines: 5),
        const SizedBox(height: 10),
        UploadTile(
          title: _photo == null ? 'Add a photo' : '✓ Photo added',
          note: _photo == null ? 'optional' : 'tap to change',
          done: _photo != null,
          height: 84,
          onTap: () async {
            final shot = await ImagePicker().pickImage(source: ImageSource.camera, maxWidth: 1600, imageQuality: 85);
            if (shot != null) setState(() => _photo = shot);
          },
        ),
        const SizedBox(height: 12),
        PrimaryButton(label: 'Send', busy: _busy, onPressed: ok ? _send : null),
      ],
    );
  }
}

class _Agreements extends StatefulWidget {
  const _Agreements({required this.d, required this.reload});
  final RentalDetail d;
  final Future<void> Function() reload;

  @override
  State<_Agreements> createState() => _AgreementsState();
}

class _AgreementsState extends State<_Agreements> {
  final _names = <int, TextEditingController>{};

  @override
  void dispose() {
    for (final c in _names.values) {
      c.dispose();
    }
    super.dispose();
  }

  TextEditingController _name(int id) => _names.putIfAbsent(id, () => TextEditingController()..addListener(() => setState(() {})));

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final d = widget.d;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (d.agreements.isEmpty)
          Text(
            d.landlord && d.rental.tenantOnAfe ? 'No agreement yet. Prepare one from these terms and you both sign it here.' : 'No agreement yet.',
            style: TextStyle(color: a.muted),
          ),
        for (final x in d.agreements) ...[
          Container(
            constraints: const BoxConstraints(maxHeight: 220),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: a.surface,
              borderRadius: BorderRadius.circular(a.cardRadius),
              border: Border.all(color: a.line),
            ),
            child: SingleChildScrollView(child: Text(x.body, style: const TextStyle(fontSize: 13.5, height: 1.55))),
          ),
          const SizedBox(height: 8),
          Panel(
            children: [DocumentRow(label: 'Agreement', sub: 'With the signatures so far', kind: 'rent_agreement', docKey: '${x.id}')],
          ),
          const SizedBox(height: 10),
          CheckLine(
            x.landlordSignedAt == null ? 'Landlord: not signed yet' : 'Landlord signed · ${x.landlordSignedName}',
            date: shortDay(x.landlordSignedAt),
            state: x.landlordSignedAt == null ? null : true,
          ),
          CheckLine(
            x.tenantSignedAt == null ? 'Tenant: not signed yet' : 'Tenant signed · ${x.tenantSignedName}',
            date: shortDay(x.tenantSignedAt),
            state: x.tenantSignedAt == null ? null : true,
          ),
          if ((d.landlord && x.landlordSignedAt == null) || (!d.landlord && x.tenantSignedAt == null)) ...[
            const SizedBox(height: 10),
            const FieldLabel('Type your full name to sign'),
            TextField(
              controller: _name(x.id),
              textCapitalization: TextCapitalization.words,
              decoration: InputDecoration(hintText: context.session.me?.user.name ?? ''),
            ),
            const SizedBox(height: 10),
            PrimaryButton(
              label: 'Sign the agreement',
              onPressed: _name(x.id).text.trim().length < 2
                  ? null
                  : () async {
                      if (await attempt(
                        context,
                        () => context.api.post('/rentals/agreements/${x.id}/sign', {'typed_name': _name(x.id).text.trim()}),
                        done: 'Signed.',
                      )) {
                        await widget.reload();
                      }
                    },
            ),
          ],
          const SizedBox(height: 14),
        ],
        if (d.landlord && d.rental.active && d.rental.tenantOnAfe)
          SecondaryButton(
            label: 'Prepare an agreement from these terms',
            onPressed: () async {
              if (await attempt(context, () => context.api.post('/rentals/${d.rental.id}/agreements'), done: 'Agreement prepared and sent to the tenant.')) {
                await widget.reload();
              }
            },
          ),
      ],
    );
  }
}

class _Renewals extends StatefulWidget {
  const _Renewals({required this.d, required this.reload});
  final RentalDetail d;
  final Future<void> Function() reload;

  @override
  State<_Renewals> createState() => _RenewalsState();
}

class _RenewalsState extends State<_Renewals> {
  late DateTime _end = (widget.d.rental.end ?? DateTime.now()).add(const Duration(days: 365));
  late final _rent = TextEditingController(text: '${widget.d.rental.rentPesewas ~/ 100}');
  int _advance = 6;
  bool _busy = false;

  @override
  void dispose() {
    _rent.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final d = widget.d;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (d.renewals.isEmpty) Text('No renewal offers.', style: TextStyle(color: a.muted)),
        if (d.renewals.isNotEmpty)
          Panel(
            children: [
              for (final rn in d.renewals)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text('Until ${day(rn.newEnd)} ${rn.newEnd?.year ?? ''}', style: const TextStyle(fontWeight: FontWeight.w600)),
                          ),
                          StatusPill(
                            switch (rn.status) {
                              'accepted' => 'Accepted',
                              'declined' => 'Declined',
                              _ => d.landlord ? 'Waiting for tenant' : 'For you to answer',
                            },
                            tone: switch (rn.status) {
                              'accepted' => PillTone.ok,
                              'declined' => PillTone.quiet,
                              _ => PillTone.warn,
                            },
                          ),
                        ],
                      ),
                      Text('${ghs(rn.newRentPesewas)} / month · ${rn.advanceMonths} months in advance', style: TextStyle(fontSize: 13, color: a.muted)),
                      if (!d.landlord && rn.status == 'offered') ...[
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 8,
                          children: [
                            SmallButton(
                              label: 'Accept',
                              kind: SmallKind.primary,
                              onPressed: () async {
                                if (await attempt(context, () => context.api.post('/rentals/renewals/${rn.id}/accept'), done: 'Renewal accepted.')) {
                                  await widget.reload();
                                }
                              },
                            ),
                            SmallButton(
                              label: 'Decline',
                              onPressed: () async {
                                if (await attempt(context, () => context.api.post('/rentals/renewals/${rn.id}/decline'), done: 'Renewal declined.')) {
                                  await widget.reload();
                                }
                              },
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
            ],
          ),
        if (d.landlord && d.rental.active) ...[
          const SizedBox(height: 16),
          const SectionLabel('Offer a renewal'),
          const SizedBox(height: 8),
          const FieldLabel('New end date'),
          Material(
            color: a.surface,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(a.inputRadius),
              side: BorderSide(color: a.line),
            ),
            child: InkWell(
              onTap: () async {
                final first = d.rental.end ?? DateTime.now();
                final picked = await showDatePicker(
                  context: context,
                  firstDate: first,
                  lastDate: first.add(const Duration(days: 365 * 5)),
                  initialDate: _end,
                );
                if (picked != null) setState(() => _end = picked);
              },
              child: SizedBox(
                height: 48,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14),
                  child: Row(
                    children: [
                      Expanded(child: Text('${day(_end)} ${_end.year}', style: const TextStyle(fontSize: 16))),
                      Icon(Icons.calendar_today_outlined, size: 20, color: a.muted),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 10),
          const FieldLabel('Rent a month'),
          TextField(
            controller: _rent,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: const InputDecoration(prefixText: 'GH₵ '),
          ),
          const SizedBox(height: 10),
          const FieldLabel('Months in advance'),
          ChipRow<int>(items: [for (var m = 0; m <= 6; m++) (m, '$m')], value: _advance, onChanged: (v) => setState(() => _advance = v)),
          const SizedBox(height: 6),
          Text('The law caps advance rent at 6 months for a renewal over 6 months.', style: TextStyle(fontSize: 12.5, color: a.muted)),
          const SizedBox(height: 12),
          PrimaryButton(
            label: 'Send renewal offer',
            busy: _busy,
            onPressed: () async {
              setState(() => _busy = true);
              final ok = await attempt(
                context,
                () => context.api.post('/rentals/${d.rental.id}/renewals', {
                  'new_end_date': isoDay(_end),
                  'new_rent_ghs': int.tryParse(_rent.text) ?? 0,
                  'advance_months': _advance,
                }),
                done: 'Renewal offer sent.',
              );
              if (!mounted) return;
              setState(() => _busy = false);
              if (ok) await widget.reload();
            },
          ),
        ],
      ],
    );
  }
}

/// Record a payment (bottom sheet): amount, months it covers, when, and how; Afe makes the receipt.
class _PaymentSheet extends StatefulWidget {
  const _PaymentSheet({required this.rental});
  final Rental rental;

  @override
  State<_PaymentSheet> createState() => _PaymentSheetState();
}

class _PaymentSheetState extends State<_PaymentSheet> {
  late final _amount = TextEditingController(text: '${widget.rental.rentPesewas * widget.rental.payEveryMonths ~/ 100}');
  late int _months = widget.rental.payEveryMonths;
  DateTime _paidOn = DateTime.now();
  String _method = 'momo';
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.api.post('/rentals/${widget.rental.id}/payments', {
        'amount_ghs': double.tryParse(_amount.text.replaceAll(',', '')) ?? 0,
        'covers_months': _months,
        'paid_on': isoDay(_paidOn),
        'method': _method,
        'note': '',
      });
      if (!mounted) return;
      toast(context, 'Payment recorded. The receipt is ready.');
      Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 0, 16, 16 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Record a payment · ${widget.rental.tenantName}', style: AfeType.heading(21, color: a.ink)),
          const SizedBox(height: 12),
          if (_error != null) ...[Note(_error!, kind: NoteKind.error), const SizedBox(height: 10)],
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const FieldLabel('Amount'),
                    TextField(
                      controller: _amount,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      style: AfeType.heading(17),
                      decoration: const InputDecoration(prefixText: 'GH₵ '),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const FieldLabel('Paid on'),
                    Material(
                      color: a.surface,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(a.inputRadius),
                        side: BorderSide(color: a.line),
                      ),
                      child: InkWell(
                        onTap: () async {
                          final d = await showDatePicker(
                            context: context,
                            firstDate: DateTime.now().subtract(const Duration(days: 365)),
                            lastDate: DateTime.now(),
                            initialDate: _paidOn,
                          );
                          if (d != null) setState(() => _paidOn = d);
                        },
                        child: SizedBox(
                          height: 48,
                          child: Center(child: Text(day(_paidOn), style: const TextStyle(fontSize: 15.5))),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          const FieldLabel('Months it covers'),
          ChipRow<int>(
            items: [
              for (final m in [1, 2, 3, 6, 12]) (m, '$m'),
            ],
            value: _months,
            onChanged: (v) => setState(() => _months = v),
          ),
          const SizedBox(height: 12),
          const FieldLabel('How'),
          ChipRow<String>(items: [for (final e in _methods.entries) (e.key, e.value)], value: _method, onChanged: (v) => setState(() => _method = v)),
          const SizedBox(height: 16),
          PrimaryButton(label: 'Record and make receipt', busy: _busy, onPressed: _save),
        ],
      ),
    );
  }
}

/// Add a tenant who pays outside Afe, so their rent, receipts and repairs are kept here.
class AddTenantScreen extends StatefulWidget {
  const AddTenantScreen({super.key});

  @override
  State<AddTenantScreen> createState() => _AddTenantScreenState();
}

class _AddTenantScreenState extends State<AddTenantScreen> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _rent = TextEditingController();
  int _every = 1;
  DateTime _start = DateTime.now();
  DateTime _end = DateTime.now().add(const Duration(days: 365));
  int? _unit;
  bool _busy = false;
  String? _error;
  Future<List<MyUnit>>? _units;

  @override
  void initState() {
    super.initState();
    _units = context.api.get<List>('/me/units').then((r) => [for (final u in r.data) MyUnit(u as Json)]);
    for (final c in [_name, _rent]) {
      c.addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    for (final c in [_name, _phone, _rent]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = Rental(
        (await context.api.post<Json>('/rentals', {
          'tenant_name': _name.text.trim(),
          'tenant_phone': _phone.text.trim().isEmpty ? '' : phoneE164(_phone.text),
          'rent_ghs': int.tryParse(_rent.text) ?? 0,
          'pay_every_months': _every,
          'start_date': isoDay(_start),
          'end_date': isoDay(_end),
          'unit_id': _unit,
        })).data,
      );
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => RentalScreen(rentalId: r.id)));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.reasons.isEmpty ? e.message : '${e.message} ${e.reasons.join(' ')}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _date(DateTime value, ValueChanged<DateTime> set, {required DateTime first}) {
    final a = context.afe;
    return Material(
      color: a.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(a.inputRadius),
        side: BorderSide(color: a.line),
      ),
      child: InkWell(
        onTap: () async {
          final d = await showDatePicker(
            context: context,
            firstDate: first,
            lastDate: DateTime.now().add(const Duration(days: 365 * 5)),
            initialDate: value,
          );
          if (d != null) set(d);
        },
        child: SizedBox(
          height: 48,
          child: Center(child: Text('${shortDay(value)} ${value.year}', style: const TextStyle(fontSize: 15.5))),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ok = _name.text.trim().length >= 2 && (int.tryParse(_rent.text) ?? 0) > 0;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Add a tenant')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const ScreenTitle('Add a tenant', lede: 'If they have an Afe account on this number, they see their receipts and can ask for repairs.'),
          const SizedBox(height: 16),
          if (_error != null) ...[Note(_error!, kind: NoteKind.error), const SizedBox(height: 12)],
          const FieldLabel("Tenant's name"),
          TextField(controller: _name, textCapitalization: TextCapitalization.words),
          const SizedBox(height: 12),
          const FieldLabel("Tenant's phone", optional: true),
          PhoneField(controller: _phone),
          const SizedBox(height: 12),
          const FieldLabel('Home'),
          FutureBuilder<List<MyUnit>>(
            future: _units,
            builder: (context, snap) => DropdownButtonFormField<int?>(
              initialValue: _unit,
              items: [
                const DropdownMenuItem<int?>(value: null, child: Text('Not on Afe')),
                for (final u in snap.data ?? const <MyUnit>[])
                  DropdownMenuItem<int?>(value: u.unit.id, child: Text('${u.unit.digitalAddress}${u.unit.label.isEmpty ? '' : ' · ${u.unit.label}'}')),
              ],
              onChanged: (v) => setState(() => _unit = v),
            ),
          ),
          const SizedBox(height: 12),
          const FieldLabel('Rent a month'),
          TextField(
            controller: _rent,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: const InputDecoration(prefixText: 'GH₵ '),
          ),
          const SizedBox(height: 12),
          const FieldLabel('Paid every'),
          ChipRow<int>(
            items: const [(1, '1 month'), (3, '3 months'), (6, '6 months'), (12, '12 months')],
            value: _every,
            onChanged: (v) => setState(() => _every = v),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const FieldLabel('Start'),
                    _date(_start, (d) => setState(() => _start = d), first: DateTime.now().subtract(const Duration(days: 365 * 2))),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const FieldLabel('End'),
                    _date(_end, (d) => setState(() => _end = d), first: _start),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          PrimaryButton(label: 'Add tenant', busy: _busy, onPressed: ok ? _save : null),
        ],
      ),
    );
  }
}
