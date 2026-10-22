import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'lister_forms.dart';
import 'messages.dart';
import 'offer.dart';

const _listingStatus = {
  'draft': 'Draft',
  'pending_review': 'Waiting for Afe',
  'live': 'Live',
  'paused': 'Paused',
  'let': 'Let',
  'archived': 'Archived',
};

const _stagePills = {
  'documents': ('Upload documents', PillTone.warn),
  'fee': ('Pay the fee', PillTone.warn),
  'visit': ('Awaiting visit', PillTone.warn),
  'review': ('Afe is reviewing', PillTone.brand),
  'verified': ('Verified', PillTone.ok),
  'rejected': ('Not verified', PillTone.bad),
};

/// The landlord dashboard from the App Screen canvas: four numbers, the listings, the homes in
/// verification, and the latest enquiry.
class ListerHomesScreen extends StatelessWidget {
  const ListerHomesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final me = SessionScope.of(context).me!;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Dashboard')),
      body: Loader<(List<MyUnit>, List<Tenancy>, List<Thread>, List<Viewing>)>(
        load: () async {
          final api = context.api;
          final units = [for (final u in (await api.get<List>('/me/units')).data) MyUnit(u as Json)];
          final tenancies = [for (final t in (await api.get<List>('/tenancies')).data) Tenancy(t as Json)];
          final threads = [for (final t in (await api.get<List>('/messages')).data) Thread(t as Json)];
          final viewings = [for (final v in (await api.get<List>('/viewings')).data) Viewing(v as Json)];
          return (units, tenancies, threads, viewings);
        },
        builder: (context, data, reload) {
          final (units, tenancies, threads, viewings) = data;
          Future<void> go(Widget screen) async {
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
            await reload();
          }

          final listings = [for (final u in units) for (final l in u.listings) (u, l)];
          final weekAgo = DateTime.now().subtract(const Duration(days: 7));
          final held = tenancies
              .where((t) => t.role == 'landlord' && const ['funded', 'disputed', 'release_pending', 'releasing'].contains(t.status))
              .fold<int>(0, (sum, t) => sum + t.payoutPesewas);
          final stats = [
            ('${listings.where((x) => x.$2.status == 'live').length}', 'Live listings'),
            ('${threads.where((t) => (t.lastMessageAt ?? DateTime(2000)).isAfter(weekAgo)).length}', 'Enquiries this week'),
            ('${viewings.where((v) => v.role == 'lister' && v.status == 'confirmed').length}', 'Viewings booked'),
            ('GH₵ ${NumberFormat.decimalPattern('en').format(held ~/ 100)}', 'Held for you'),
          ];
          final latest = threads.isEmpty ? null : threads.first;
          return ListView(padding: const EdgeInsets.all(16), children: [
            if (!me.verified) ...[
              const Note('Renters only see homes from verified landlords and agents.', kind: NoteKind.warn, lead: 'First, get verified.'),
              const SizedBox(height: 8),
              SecondaryButton(label: 'Verify my Ghana Card', icon: Icons.badge_outlined, onPressed: () => go(const VerifyIdentityScreen())),
              const SizedBox(height: 14),
            ],
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              childAspectRatio: 2.1,
              children: [
                for (final (v, l) in stats)
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(color: a.surface, borderRadius: BorderRadius.circular(a.cardRadius), border: Border.all(color: a.line)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
                      FittedBox(child: Text(v, style: AfeType.heading(22, color: a.accent))),
                      Text(l, style: TextStyle(fontSize: 12.5, color: a.muted)),
                    ]),
                  ),
              ],
            ),
            const SizedBox(height: 14),
            const SectionLabel('Listings'),
            const SizedBox(height: 8),
            if (listings.isEmpty)
              Text("No listing yet. You can list a home once it's verified.", style: TextStyle(fontSize: 14, color: a.muted))
            else
              Panel(children: [
                for (final (u, l) in listings)
                  InkWell(
                    onTap: () => go(UnitScreen(unitId: u.unit.id)),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: Row(children: [
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(l.title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
                            Text('${l.reference} · ${cedis(l.rent)}', style: TextStyle(fontSize: 12.5, color: a.muted)),
                          ]),
                        ),
                        StatusPill(_listingStatus[l.status] ?? l.status,
                            tone: l.status == 'live' ? PillTone.ok : l.status == 'draft' || l.status == 'pending_review' ? PillTone.warn : PillTone.quiet),
                      ]),
                    ),
                  ),
              ]),
            const SizedBox(height: 14),
            const SectionLabel('Homes'),
            const SizedBox(height: 8),
            if (units.isEmpty)
              Text('No homes yet. Add your first home: its address, a pin on the map, then an ownership document.',
                  style: TextStyle(fontSize: 14, color: a.muted))
            else
              Panel(children: [
                for (final u in units)
                  InkWell(
                    onTap: () => go(UnitScreen(unitId: u.unit.id)),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: Row(children: [
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text([u.unit.propertyType, bedroomsLabel(u.unit.bedrooms), if (u.unit.label.isNotEmpty) u.unit.label].join(' · '),
                                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
                            Text('${u.unit.area} · ${u.unit.digitalAddress}', style: TextStyle(fontSize: 12.5, color: a.muted)),
                          ]),
                        ),
                        StatusPill(_stagePills[u.stage]?.$1 ?? u.stage, tone: _stagePills[u.stage]?.$2 ?? PillTone.quiet),
                      ]),
                    ),
                  ),
              ]),
            const SizedBox(height: 10),
            PrimaryButton(
              label: 'Add a home',
              icon: Icons.add_home_outlined,
              onPressed: () async {
                final id = await Navigator.of(context).push<int>(MaterialPageRoute(builder: (_) => const AddHomeScreen()));
                if (id != null && context.mounted) await Navigator.of(context).push(MaterialPageRoute(builder: (_) => UnitScreen(unitId: id)));
                await reload();
              },
            ),
            if (latest != null) ...[
              const SizedBox(height: 18),
              const SectionLabel('Latest enquiry'),
              const SizedBox(height: 8),
              Panel(padded: true, children: [
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${latest.otherName} · ${latest.listingReference}', style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Text('${latest.unread ? 'New message' : 'Enquiry'} about ${latest.listingTitle}', style: const TextStyle(fontSize: 14)),
                  const SizedBox(height: 8),
                  SmallButton(label: latest.unread ? 'Reply' : 'Open', onPressed: () => openThread(context, latest.id)),
                ]),
              ]),
            ],
          ]);
        },
      ),
    );
  }
}

/// One home, as on the website: the address, the verification stepper, the next step as a card
/// (upload, pay, wait for the visit, create a listing), the documents, and the listings.
class UnitScreen extends StatelessWidget {
  const UnitScreen({super.key, required this.unitId});
  final int unitId;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Home')),
      body: Loader<MyUnit>(
        load: () async => MyUnit((await context.api.get<Json>('/properties/units/$unitId')).data),
        builder: (context, u, reload) {
          Future<void> go(Widget screen) async {
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
            await reload();
          }

          final order = ['documents', if (u.feeRequired || u.stage == 'fee') 'fee', 'visit', 'review', 'verified'];
          final at = u.stage == 'rejected' ? order.indexOf('review') : order.indexOf(u.stage);
          const titles = {
            'documents': ('Upload ownership documents', 'Indenture, title or letter of authority'),
            'fee': ('Pay the verification fee', 'Mobile money or card'),
            'visit': ('Afe verifier visits the home', 'They call you first'),
            'review': ('Afe reviews the visit', 'Usually within 2 working days'),
            'verified': ('Verified', 'You can publish listings'),
          };
          final open = u.listings.any((l) => l.status == 'live' || l.status == 'pending_review' || l.status == 'draft');
          final next = switch (u.stage) {
            'documents' => _NextStep(
              title: 'Upload an ownership document',
              body: 'An indenture, land title or Lands Commission search. Agents add the owner\'s letter of authority.',
              action: 'Upload document',
              onPressed: () => go(UploadDocumentScreen(unitId: u.unit.id)),
            ),
            'fee' => _NextStep(
              title: 'Pay the verification fee',
              body: 'The fee pays for an Afe verifier to visit the home. Pay by mobile money (MTN, Telecel, AT) or card.',
              action: 'Pay now',
              onPressed: () async {
                await attempt(context, () async {
                  final pay = (await context.api.post<Json>('/payments/verification-fee', {'unit_id': u.unit.id})).data;
                  final url = '${pay['checkout_url'] ?? ''}';
                  if (url.isNotEmpty) await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
                });
                await reload();
              },
            ),
            'visit' => _NextStep(
              title: u.visitScheduledFor == null ? 'Waiting for a visit date' : 'Visit on ${dayTime(u.visitScheduledFor)}',
              body: 'An Afe verifier checks the address, meets you there, looks at the original documents and takes the listing photos. They call you first.',
            ),
            'review' => const _NextStep(
              title: 'Afe is reviewing the visit',
              body: 'A reviewer reads the verifier\'s report. You get an SMS with the decision.',
            ),
            'verified' when !open => _NextStep(
              title: 'Create a listing',
              body: 'Afe checks the listing before it goes live. The photos are the ones our verifier took.',
              action: 'Create a listing',
              onPressed: () => go(NewListingScreen(unitId: u.unit.id)),
            ),
            'rejected' => const _NextStep(
              title: 'Not verified',
              body: 'See the reason on the website, and appeal once if you think it\'s wrong.',
              tone: NoteKind.error,
            ),
            _ => null,
          };

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(u.unit.digitalAddress, style: AfeType.mono(12.5, color: a.muted)),
              const SizedBox(height: 4),
              Text(u.unit.label.isEmpty ? u.unit.propertyType : u.unit.label, style: AfeType.heading(26, color: a.ink)),
              const SizedBox(height: 4),
              Text(
                [
                  u.unit.area,
                  bedroomsLabel(u.unit.bedrooms),
                  '${u.unit.bathrooms} bath${u.unit.bathrooms == 1 ? '' : 's'}',
                  u.unit.propertyType,
                  if (u.unit.landmark.isNotEmpty) u.unit.landmark,
                ].join(' · '),
                style: TextStyle(fontSize: 14, color: a.muted),
              ),
              if (u.stage == 'verified' && u.verifiedUntil != null) ...[
                const SizedBox(height: 10),
                Align(alignment: Alignment.centerLeft, child: VerifiedBadge(label: 'Verified until ${day(u.verifiedUntil)}')),
              ],
              const SizedBox(height: 16),
              Panel(
                title: 'Verification',
                children: [
                  for (var i = 0; i < order.length; i++)
                    StepTile(
                      number: i + 1,
                      title: titles[order[i]]!.$1,
                      subtitle: titles[order[i]]!.$2,
                      done: u.stage == 'verified' || (at >= 0 && i < at),
                      current: i == at,
                    ),
                ],
              ),
              if (next != null) ...[const SizedBox(height: 14), next],
              const SizedBox(height: 16),
              Panel(
                title: 'Documents',
                trailing: u.stage == 'verified' ? null : SmallButton(label: 'Add', kind: SmallKind.quiet, onPressed: () => go(UploadDocumentScreen(unitId: u.unit.id))),
                children: [
                  if (u.authorities.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(14),
                      child: Text('Upload proof that you can let this home.', style: TextStyle(fontSize: 14, color: a.muted)),
                    ),
                  for (final d in u.authorities)
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(d.documentLabel, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
                                Text(
                                  [d.relationshipLabel, if (d.reviewNote.isNotEmpty) d.reviewNote].join(' · '),
                                  style: TextStyle(fontSize: 12.5, color: a.muted),
                                ),
                              ],
                            ),
                          ),
                          StatusPill(
                            switch (d.status) {
                              'accepted' => 'Accepted',
                              'rejected' => 'Rejected',
                              _ => 'With Afe',
                            },
                            tone: switch (d.status) {
                              'accepted' => PillTone.ok,
                              'rejected' => PillTone.bad,
                              _ => PillTone.warn,
                            },
                          ),
                        ],
                      ),
                    ),
                ],
              ),
              if (u.listings.isNotEmpty) ...[
                const SizedBox(height: 16),
                Panel(
                  title: 'Listings',
                  children: [
                    for (final l in u.listings)
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(l.title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
                                      Text('${l.reference} · ${cedis(l.rent)} / month', style: AfeType.mono(11.5, color: a.muted)),
                                    ],
                                  ),
                                ),
                                StatusPill(
                                  _listingStatus[l.status] ?? l.status,
                                  tone: l.status == 'live'
                                      ? PillTone.ok
                                      : l.status == 'draft' || l.status == 'pending_review'
                                      ? PillTone.warn
                                      : PillTone.quiet,
                                ),
                              ],
                            ),
                            if (l.statusReason.isNotEmpty) ...[
                              const SizedBox(height: 4),
                              Text(l.statusReason, style: TextStyle(color: a.muted, fontSize: 13)),
                            ],
                            if (l.status != 'let' && l.status != 'archived') ...[
                              const SizedBox(height: 10),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  SmallButton(
                                    label: l.status == 'live' ? 'Edit or feature' : 'Edit',
                                    onPressed: () => go(ListingEditScreen(listingId: l.id)),
                                  ),
                                  if (l.status == 'draft')
                                    SmallButton(
                                      label: 'Submit for review',
                                      kind: SmallKind.primary,
                                      onPressed: () async {
                                        if (await attempt(context, () => context.api.post('/properties/listings/${l.id}/submit'),
                                            done: 'Sent to Afe for a check')) {
                                          await reload();
                                        }
                                      },
                                    ),
                                  SmallButton(
                                    label: 'Take down',
                                    kind: SmallKind.danger,
                                    onPressed: () async {
                                      if (await attempt(context, () => context.api.post('/properties/listings/${l.id}/archive'),
                                          done: 'Listing taken down')) {
                                        await reload();
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
              ],
            ],
          );
        },
      ),
    );
  }
}

/// The "Next step" card from the Landlord canvas: a mono amber kicker, the step, what it means,
/// and its button.
class _NextStep extends StatelessWidget {
  const _NextStep({required this.title, required this.body, this.action, this.onPressed, this.tone = NoteKind.info});
  final String title;
  final String body;
  final String? action;
  final VoidCallback? onPressed;
  final NoteKind tone;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: a.surface,
        borderRadius: BorderRadius.circular(a.cardRadius + 2),
        border: Border.all(color: tone == NoteKind.error ? a.crit : a.line, width: tone == NoteKind.error ? 2 : 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('NEXT STEP', style: AfeType.label(a.warn, size: 11)),
          const SizedBox(height: 6),
          Text(title, style: AfeType.heading(21, color: a.ink)),
          const SizedBox(height: 6),
          Text(body, style: TextStyle(fontSize: 14.5, color: a.muted, height: 1.45)),
          if (action != null) ...[const SizedBox(height: 14), PrimaryButton(label: action!, onPressed: onPressed)],
        ],
      ),
    );
  }
}

/// Payouts from the Landlord canvas: what Afe holds for you, the payout account, and each
/// tenancy's money (held, released, refunded).
class PayoutsScreen extends StatelessWidget {
  const PayoutsScreen({super.key});

  static const _held = ['funded', 'disputed', 'release_pending', 'releasing'];

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Payouts')),
      body: Loader<(Payee?, List<Tenancy>)>(
        load: () async {
          final api = context.api;
          final data = (await api.get<Json?>('/me/payouts')).data;
          final tenancies = [for (final t in (await api.get<List>('/tenancies')).data) Tenancy(t as Json)];
          return (data == null ? null : Payee(data), tenancies.where((t) => t.role == 'landlord').toList());
        },
        builder: (context, data, reload) {
          final (p, tenancies) = data;
          final held = tenancies.where((t) => _held.contains(t.status)).fold<int>(0, (sum, t) => sum + t.payoutPesewas);
          final rows = [
            for (final t in tenancies)
              if (_held.contains(t.status) || t.status == 'released' || t.status == 'refunded') t,
          ];
          final pending = p?.usableFrom != null && p!.usableFrom!.isAfter(DateTime.now());
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const ScreenTitle('Payouts', lede: 'Rent is held by Afe\'s payment partner and released when each tenant confirms move-in.'),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(color: a.okSoft, borderRadius: BorderRadius.circular(a.cardRadius)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Held for you', style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: a.ok)),
                    const SizedBox(height: 4),
                    Text('GH₵ ${NumberFormat.decimalPattern('en').format(held ~/ 100)}', style: AfeType.heading(28, color: a.accent)),
                    const SizedBox(height: 2),
                    Text('Released when each tenant confirms move-in', style: TextStyle(fontSize: 13, color: a.ink)),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: a.surface,
                  borderRadius: BorderRadius.circular(a.cardRadius),
                  border: Border.all(color: a.line),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Payout account', style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: a.muted)),
                    const SizedBox(height: 4),
                    if (p == null) ...[
                      const Text('None yet', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                      Text('Add one before you offer a tenancy.', style: TextStyle(fontSize: 13, color: a.warn)),
                    ] else ...[
                      Text(
                        '${payoutChannels[p.channel] ?? (p.channel == 'bank' ? 'Bank account' : 'Mobile money')} · ${p.masked}',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                      ),
                      Text(
                        pending ? 'Can receive money from ${dayTime(p.usableFrom)}' : '✓ ${p.accountName}, name-matched',
                        style: TextStyle(fontSize: 13, color: pending ? a.warn : a.ok),
                      ),
                    ],
                    const SizedBox(height: 12),
                    SmallButton(
                      label: p == null ? 'Add a payout account' : 'Change',
                      kind: p == null ? SmallKind.primary : SmallKind.secondary,
                      onPressed: () async {
                        await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ChangePayoutScreen()));
                        await reload();
                      },
                    ),
                  ],
                ),
              ),
              if (rows.isNotEmpty) ...[
                const SizedBox(height: 16),
                Panel(
                  children: [
                    for (final t in rows)
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(t.tenantName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
                                  Text(
                                    '${t.listingTitle} · ${day(t.closedAt ?? t.fundedAt)}',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(fontSize: 12.5, color: a.muted),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 10),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(cedis(t.payout), style: const TextStyle(fontWeight: FontWeight.w600, fontFeatures: [FontFeature.tabularFigures()])),
                                const SizedBox(height: 4),
                                StatusPill(
                                  t.status == 'released' ? 'Released' : t.status == 'refunded' ? 'Refunded' : 'Held',
                                  tone: t.status == 'released' ? PillTone.ok : t.status == 'refunded' ? PillTone.quiet : PillTone.warn,
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 14),
              Text(
                'Every change of payout account needs a code from your authenticator app. A changed account waits 72 hours before money can go to it, and we confirm the change with you.',
                style: TextStyle(color: a.muted, fontSize: 13, height: 1.45),
              ),
            ],
          );
        },
      ),
    );
  }
}
