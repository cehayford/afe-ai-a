import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';

String tenancyStatusLabel(String status) => switch (status) {
  'offered' => 'Offer waiting for the tenant',
  'funding' => 'Waiting for payment',
  'funded' => 'Money held until move-in',
  'disputed' => 'A reviewer is looking at a problem',
  'release_pending' => 'Release being checked',
  'releasing' => 'Paying the landlord',
  'released' => 'Landlord paid',
  'refunding' => 'Refund on its way',
  'refunded' => 'Refunded',
  'declined' => 'Declined',
  'withdrawn' => 'Offer withdrawn',
  'expired' => 'Expired',
  _ => status,
};

/// How far the money has got: paid, held, moved in, released (the canvas's four bars).
int tenancyReached(String status) => switch (status) {
  'funded' || 'disputed' => 2,
  'release_pending' || 'releasing' => 3,
  'released' => 4,
  'refunding' || 'refunded' => 2,
  _ => 0,
};

class TenanciesScreen extends StatelessWidget {
  const TenanciesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Payments')),
      body: Loader<List<Tenancy>>(
        load: () async => [for (final t in (await context.api.get<List>('/tenancies')).data) Tenancy(t as Json)],
        builder: (context, list, reload) => list.isEmpty
            ? ListView(
                children: const [
                  EmptyState(
                    title: 'No payments yet',
                    body: 'After a viewing, the landlord can offer you the home here. Your rent advance is held until you move in.',
                  ),
                ],
              )
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: list.length,
                separatorBuilder: (_, _) => const SizedBox(height: 12),
                itemBuilder: (context, i) {
                  final t = list[i];
                  return Pressable(
                    scale: 0.98,
                    child: Card(
                      child: InkWell(
                        onTap: () async {
                          await Navigator.of(context).push(MaterialPageRoute(builder: (_) => TenancyScreen(reference: t.reference)));
                          await reload();
                        },
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Expanded(
                                    child: Text('${t.listingTitle}, ${t.area}', style: AfeType.heading(17, color: a.ink, height: 1.15)),
                                  ),
                                  const SizedBox(width: 8),
                                  Text(cedis(t.role == 'tenant' ? t.charge : t.held), style: AfeType.heading(18, color: a.accent)),
                                ],
                              ),
                              const SizedBox(height: 14),
                              PayFlowBar(reached: tenancyReached(t.status)),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(tenancyStatusLabel(t.status), style: TextStyle(fontSize: 13.5, color: a.muted)),
                                  ),
                                  if (t.actions.isNotEmpty) const StatusPill('To do', tone: PillTone.warn),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
      ),
    );
  }
}

class TenancyScreen extends StatelessWidget {
  const TenancyScreen({super.key, required this.reference});
  final String reference;

  @override
  Widget build(BuildContext context) => Loader<Tenancy>(
    load: () async => Tenancy((await context.api.get<Json>('/tenancies/$reference')).data),
    builder: (context, t, reload) => _TenancyBody(t: t, reload: reload),
  );
}

class _TenancyBody extends StatefulWidget {
  const _TenancyBody({required this.t, required this.reload});
  final Tenancy t;
  final Future<void> Function() reload;

  @override
  State<_TenancyBody> createState() => _TenancyBodyState();
}

class _TenancyBodyState extends State<_TenancyBody> {
  final _ticks = [false, false, false];
  String? _photo;
  bool _busy = false;

  Tenancy get t => widget.t;

  Future<void> _post(String action, [Object? body, String? done]) async {
    if (await attempt(context, () => context.api.post('/tenancies/${t.reference}/$action', body), done: done)) await widget.reload();
  }

  /// Accept the offer (the API opens a checkout), then pay on the partner's page.
  Future<void> _pay() async {
    setState(() => _busy = true);
    var url = t.checkoutUrl;
    if (t.can('accept')) {
      try {
        final accepted = Tenancy((await context.api.post<Json>('/tenancies/${t.reference}/accept')).data);
        url = accepted.checkoutUrl;
      } on Exception catch (e) {
        if (mounted) toast(context, '$e');
      }
    }
    if (url.isNotEmpty) await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (mounted) {
      setState(() => _busy = false);
      toast(context, "When you've paid, pull down to refresh.");
      await widget.reload();
    }
  }

  Future<void> _takePhoto() async {
    final photo = await ImagePicker().pickImage(source: ImageSource.camera, maxWidth: 1600, imageQuality: 85).catchError((_) => null);
    if (photo != null && mounted) setState(() => _photo = photo.path);
  }

  Future<void> _release() async {
    setState(() => _busy = true);
    final done = await attempt(
      context,
      () => context.api.upload('/tenancies/${t.reference}/confirm-move-in', files: {'photo': ?_photo}),
      done: 'Move-in confirmed. The landlord will be paid.',
    );
    if (mounted) setState(() => _busy = false);
    if (done) await widget.reload();
  }

  Future<void> _dispute() async {
    const reasons = {
      'not_delivered': "The home wasn't handed over",
      'not_as_listed': "The home isn't what was listed",
      'tenant_no_show': "The tenant didn't move in",
      'access_refused': 'Access was refused on the move-in date',
      'other': 'Something else',
    };
    String reason = t.role == 'landlord' ? 'tenant_no_show' : 'not_delivered';
    final details = TextEditingController();
    final submit = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, set) => Padding(
          padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Keep my money held', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 4),
              const Text('Nothing is released while an Afe reviewer looks at it.'),
              RadioGroup<String>(
                groupValue: reason,
                onChanged: (v) => set(() => reason = v ?? reason),
                child: Column(
                  children: [
                    for (final e in reasons.entries)
                      if (t.role == 'landlord' ? e.key != 'not_delivered' && e.key != 'not_as_listed' : e.key != 'tenant_no_show')
                        RadioListTile<String>(contentPadding: EdgeInsets.zero, value: e.key, title: Text(e.value)),
                  ],
                ),
              ),
              TextField(
                controller: details,
                minLines: 3,
                maxLines: 6,
                decoration: const InputDecoration(hintText: 'What happened? A reviewer will read this.'),
              ),
              const SizedBox(height: 14),
              PrimaryButton(label: 'Send to Afe', onPressed: () => Navigator.pop(context, true)),
            ],
          ),
        ),
      ),
    );
    if (submit == true && mounted) {
      await _post('disputes', {'reason': reason, 'details': details.text}, 'Sent. We will call you within one working day.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final tenant = t.role == 'tenant';
    final paying = tenant && (t.can('accept') || t.can('pay'));
    final moving = t.can('confirm_move_in');
    final title = paying
        ? 'Pay safely'
        : moving
        ? 'Confirm move-in'
        : t.reference;

    Widget? bar;
    if (paying) {
      bar = BottomActionBar(
        label: 'Pay ${cedis(t.charge)}',
        onPressed: _pay,
        busy: _busy,
        price: cedis(t.charge),
        priceNote: 'held by Afe',
      );
    } else if (moving) {
      bar = BottomActionBar(label: 'Release payment', onPressed: _ticks.every((x) => x) ? _release : null, busy: _busy);
    }

    Widget row(String k, String v) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(k, style: TextStyle(color: a.muted, fontSize: 14)),
          ),
          Text(v, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
        ],
      ),
    );

    return Scaffold(
      appBar: AfeAppBar(title: Text(title)),
      bottomNavigationBar: bar,
      body: RefreshIndicator(
        onRefresh: widget.reload,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 24),
          children: [
            PayFlowBar(reached: tenancyReached(t.status)),
            const SizedBox(height: 16),
            Text('${t.listingTitle}, ${t.area}', style: AfeType.heading(20, color: a.ink, height: 1.15)),
            Text(
              tenant ? 'Landlord ${t.landlordName} · ${t.reference}' : 'Tenant ${t.tenantName} · ${t.reference}',
              style: TextStyle(color: a.muted, fontSize: 13.5),
            ),
            const SizedBox(height: 16),

            // Paying: months are set in the offer; the method is chosen on the partner's page.
            if (paying) ...[
              const SectionLabel('Months in advance'),
              const SizedBox(height: 8),
              Row(
                children: [AfeChip(label: '${t.advanceMonths} mo', selected: true, height: 44, onTap: () {})],
              ),
              const SizedBox(height: 6),
              Text('Set in the landlord\'s offer. Afe caps advance rent at 6 months.', style: TextStyle(fontSize: 12.5, color: a.muted)),
              const SizedBox(height: 16),
              const SectionLabel('Pay with'),
              const SizedBox(height: 8),
              Panel(
                children: [
                  for (final m in const ['MTN Mobile Money', 'Telecel Cash', 'Card'])
                    Padding(
                      padding: const EdgeInsets.all(14),
                      child: Row(
                        children: [
                          Container(
                            width: 20,
                            height: 20,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(color: a.line, width: 2),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Text(m, style: const TextStyle(fontSize: 15)),
                        ],
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 6),
              Text("You choose on our payment partner's secure page.", style: TextStyle(fontSize: 12.5, color: a.muted)),
              const SizedBox(height: 16),
              Panel(
                children: [
                  row('Rent × ${t.advanceMonths} months', cedis(t.held)),
                  row('Protection fee', t.fee.isEmpty || t.fee == 'GH₵0' ? 'Free' : cedis(t.fee)),
                  if (t.offerExpiresAt != null) row('Offer open until', dayTime(t.offerExpiresAt)),
                ],
              ),
              if (t.can('decline')) ...[
                const SizedBox(height: 8),
                TextButton(onPressed: () => _post('decline', null, 'Offer declined'), child: const Text('Decline the offer')),
              ],
            ],

            // Held: the money waits; tick the move-in checks to release it.
            if (tenant && (t.status == 'funded' || moving)) ...[
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(color: a.okSoft, borderRadius: BorderRadius.circular(a.cardRadius)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${cedis(t.held)} held by Afe', style: AfeType.heading(24, color: a.accent)),
                    const SizedBox(height: 6),
                    const Text(
                      "The landlord can see it but can't take it until you confirm move-in.",
                      style: TextStyle(fontSize: 14.5, height: 1.5),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 18),
            ],
            if (moving) ...[
              Text('Have you moved in?', style: AfeType.heading(26, color: a.ink)),
              const SizedBox(height: 6),
              Text('Tick each one that\'s true, then release ${cedis(t.held)}.', style: TextStyle(fontSize: 14.5, color: a.muted)),
              const SizedBox(height: 14),
              Panel(
                children: [
                  for (final (i, label) in [
                    'I have the keys',
                    'The home matches the listing',
                    'I met the verified landlord, ${t.landlordName}',
                  ].indexed)
                    InkWell(
                      onTap: () => setState(() => _ticks[i] = !_ticks[i]),
                      child: Semantics(
                        checked: _ticks[i],
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Row(
                            children: [
                              AnimatedContainer(
                                duration: Motion.reduced(context) ? Duration.zero : Motion.press,
                                width: 24,
                                height: 24,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                  color: _ticks[i] ? a.brand : Colors.transparent,
                                  shape: a.ios ? BoxShape.circle : BoxShape.rectangle,
                                  borderRadius: a.ios ? null : BorderRadius.circular(4),
                                  border: _ticks[i] ? null : Border.all(color: a.line, width: 2),
                                ),
                                child: _ticks[i]
                                    ? Text(
                                        '✓',
                                        style: TextStyle(color: a.onBrand, fontSize: 13, fontWeight: FontWeight.w700),
                                      )
                                    : null,
                              ),
                              const SizedBox(width: 12),
                              Expanded(child: Text(label, style: const TextStyle(fontSize: 15))),
                            ],
                          ),
                        ),
                      ),
                    ),
                  InkWell(
                    onTap: _takePhoto,
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Row(
                        children: [
                          Icon(_photo == null ? Icons.photo_camera_outlined : Icons.check_circle, color: _photo == null ? a.muted : a.ok),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              _photo == null ? 'Add a photo of the home today (optional, kept private)' : 'Photo added',
                              style: const TextStyle(fontSize: 14),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              if (t.can('dispute')) SecondaryButton(label: "Something's wrong. Keep it held.", danger: true, onPressed: _dispute),
              const SizedBox(height: 16),
            ],

            if (t.status == 'released' && tenant) ...[
              Text('Welcome home.', style: AfeType.heading(28, color: a.ink)),
              const SizedBox(height: 6),
              Text('${cedis(t.held)} released to ${t.landlordName}.', style: TextStyle(fontSize: 14.5, color: a.muted, height: 1.5)),
              const SizedBox(height: 16),
            ],
            if (t.status == 'disputed') ...[
              Text(tenant ? 'Your money stays with Afe.' : 'Payment on hold', style: AfeType.heading(26, color: a.ink)),
              const SizedBox(height: 6),
              const Text(
                "We'll call you within one working day. Nothing is released while the case is open.",
                style: TextStyle(fontSize: 14.5, height: 1.5),
              ),
              const SizedBox(height: 16),
            ],

            if (!paying) ...[
              const SizedBox(height: 4),
              Panel(
                title: 'Terms',
                children: [
                  row('Rent', '${cedis(t.rent)} / month'),
                  row('Advance', '${t.advanceMonths} months'),
                  row('Lease', '${t.leaseMonths} months'),
                  row('Move-in', day(t.moveInDate)),
                  if (tenant) row('You paid', cedis(t.charge)) else row('You receive', cedis(t.payout)),
                  row('Status', tenancyStatusLabel(t.status)),
                  if (t.closeReason.isNotEmpty) row('Note', t.closeReason),
                ],
              ),
              const SizedBox(height: 14),
            ],
            if (t.hasReceipt || t.hasAgreement || t.hasMoveInPhoto) ...[
              Panel(
                title: 'Documents',
                children: [
                  if (t.hasReceipt) DocumentRow(label: 'Receipt', sub: t.reference, kind: 'tenancy_receipt', docKey: t.reference),
                  if (t.hasAgreement) DocumentRow(label: 'Tenancy agreement', sub: t.reference, kind: 'tenancy_agreement', docKey: t.reference),
                  if (t.hasMoveInPhoto) DocumentRow(label: 'Move-in photo', sub: 'Kept private', kind: 'move_in_photo', docKey: t.reference, photo: true),
                ],
              ),
              const SizedBox(height: 14),
            ],
            if (t.can('record_move_in')) ...[
              SecondaryButton(
                label: 'Record the handover',
                onPressed: () => _post('move-in-evidence', {'note': 'Keys handed over on ${day(DateTime.now())}.'}, 'Handover recorded'),
              ),
              const SizedBox(height: 10),
            ],
            if (t.can('withdraw')) ...[
              SecondaryButton(label: 'Withdraw the offer', onPressed: () => _post('withdraw', null, 'Offer withdrawn')),
              const SizedBox(height: 10),
            ],
            if (t.can('dispute') && !moving) SecondaryButton(label: 'Raise a problem', danger: true, onPressed: _dispute),
            if (t.can('review'))
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text('You can review this landlord on the Afe website.', style: TextStyle(color: a.muted)),
              ),
          ],
        ),
      ),
    );
  }
}
