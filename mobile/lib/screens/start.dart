import 'package:flutter/material.dart';

import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/brand.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'account.dart';
import 'auth.dart';
import 'field.dart';
import 'homes.dart';
import 'lister.dart';
import 'lister_forms.dart';
import 'messages.dart';
import 'offer.dart';
import 'rentals.dart';
import 'tenancies.dart';

/// Where someone can go from the start screen and the drawer, by who they are.
typedef Destination = ({String label, String sub, Widget Function() screen});

List<Destination> destinationsFor(Me? me) {
  final u = me?.user;
  if (u == null) {
    return [
      (label: 'Find a home', sub: 'Map and verified list', screen: SearchScreen.new),
      (label: 'Scam check', sub: 'Check a number first', screen: CheckScreen.new),
      (label: 'Sign in', sub: 'Phone and code', screen: SignInScreen.new),
      (label: 'Create account', sub: 'Renters, landlords, agents', screen: SignUpScreen.new),
    ];
  }
  if (u.isLister) {
    return [
      (label: 'Get verified', sub: 'Card, papers, visit', screen: LandlordVerifyScreen.new),
      (label: 'Dashboard', sub: 'Homes and listings', screen: ListerHomesScreen.new),
      (label: 'Listings', sub: 'Edit, feature, take down', screen: MyListingsScreen.new),
      (label: 'Viewings', sub: 'Requests to answer', screen: ViewingsScreen.new),
      (label: 'Enquiries', sub: 'Messages from renters', screen: MessagesScreen.new),
      (label: 'Payouts', sub: 'Where rent is paid', screen: PayoutsScreen.new),
      (label: 'Tenants', sub: 'Rent, receipts, repairs', screen: TenantsScreen.new),
      (label: 'Scam check', sub: 'See what renters see', screen: CheckScreen.new),
    ];
  }
  if (u.isVerifier) {
    return [
      (label: "Today's visits", sub: 'Your route', screen: WorklistScreen.new),
      (label: 'Scam check', sub: 'Look up a number', screen: CheckScreen.new),
      (label: 'Account', sub: 'Profile and sign out', screen: AccountScreen.new),
    ];
  }
  return [
    (label: 'Find a home', sub: 'Map and verified list', screen: SearchScreen.new),
    (label: 'Scam check', sub: 'Check a number first', screen: CheckScreen.new),
    (label: 'Viewings', sub: 'Book and keep track', screen: ViewingsScreen.new),
    (label: 'Pay safely', sub: 'Rent held until move-in', screen: TenanciesScreen.new),
    (label: 'Messages', sub: "Landlords' replies", screen: MessagesScreen.new),
    (label: 'My home', sub: 'Rent, receipts, repairs', screen: MyHomesScreen.new),
    (label: 'My Afe', sub: 'Saved, viewings, payments', screen: MyAfeScreen.new),
  ];
}

void _push(BuildContext context, Widget Function() screen) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen()));

/// The app's first screen, from the canvas: the mark and a greeting, a grid of numbered tiles,
/// and the launch offer while it lasts. ☰ opens the drawer with the same places.
class StartScreen extends StatefulWidget {
  const StartScreen({super.key});

  @override
  State<StartScreen> createState() => _StartScreenState();
}

class _StartScreenState extends State<StartScreen> {
  Json? _pricing;

  @override
  void initState() {
    super.initState();
    context.api
        .get<Json>('/pricing')
        .then((r) {
          if (mounted) setState(() => _pricing = r.data);
        })
        .catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final me = SessionScope.of(context).me;
    final first = me?.user.name.split(RegExp(r'\s+')).first ?? '';
    final hour = DateTime.now().hour;
    final greet = me == null
        ? 'Welcome to Afe'
        : me.user.isVerifier
        ? '${hour < 12
              ? 'Morning'
              : hour < 17
              ? 'Afternoon'
              : 'Evening'}, $first'
        : 'Hello, $first';
    final places = destinationsFor(me);
    final until = DateTime.tryParse('${_pricing?['free_until'] ?? ''}');
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Afe')),
      drawer: const AfeDrawer(),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              const AfeMark(size: 44),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(greet, style: AfeType.heading(24, color: a.ink)),
                    Text('Where do you want to go?', style: TextStyle(fontSize: 14, color: a.muted)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 1.45,
            children: [
              for (var i = 0; i < places.length; i++)
                Pressable(
                  child: Material(
                    color: a.surface,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(a.cardRadius),
                      side: BorderSide(color: a.line),
                    ),
                    child: InkWell(
                      customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.cardRadius)),
                      onTap: () => _push(context, places[i].screen),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('${i + 1}'.padLeft(2, '0'), style: AfeType.mono(11, color: a.amber)),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(places[i].label, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                                const SizedBox(height: 2),
                                Text(
                                  places[i].sub,
                                  style: TextStyle(fontSize: 12.5, color: a.muted),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
          if (_pricing?['launch_offer'] == true) ...[
            const SizedBox(height: 18),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: a.warnSoft, borderRadius: BorderRadius.circular(a.cardRadius)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Launch offer', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
                  const SizedBox(height: 4),
                  Text(
                    'Verification, protection and featured listings are free${until == null ? '' : ' until ${DateFormatShort.full(until)}'}.',
                    style: const TextStyle(fontSize: 13.5),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class DateFormatShort {
  static const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  static String full(DateTime d) => '${d.day} ${_months[d.month - 1]} ${d.year}';
}

/// The drawer: the mark, "afe" and the role, then the same places as the start screen.
class AfeDrawer extends StatelessWidget {
  const AfeDrawer({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final session = SessionScope.of(context);
    final me = session.me;
    final role = me == null
        ? null
        : me.user.isLister
        ? 'Landlord'
        : me.user.isVerifier
        ? 'Verifier'
        : 'Renter';
    Widget item(String label, VoidCallback onTap, {bool on = false}) => Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Material(
        color: on ? a.tint : Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.drawerItemRadius)),
        child: InkWell(
          customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.drawerItemRadius)),
          onTap: onTap,
          child: Container(
            height: a.drawerItemHeight,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            alignment: Alignment.centerLeft,
            child: Text(
              label,
              style: TextStyle(fontSize: a.ios ? 17 : 15, fontWeight: on ? FontWeight.w600 : FontWeight.w500, color: on ? a.accent : a.ink),
            ),
          ),
        ),
      ),
    );
    return Drawer(
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
              child: Align(
                alignment: Alignment.centerLeft,
                child: AfeLogo(mark: 32, text: 22, tag: role),
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  item('Home', () => Navigator.of(context).pop(), on: true),
                  for (final d in destinationsFor(me))
                    item(d.label, () {
                      Navigator.of(context).pop();
                      _push(context, d.screen);
                    }),
                  if (me != null && !me.user.isVerifier)
                    item('Account', () {
                      Navigator.of(context).pop();
                      _push(context, AccountScreen.new);
                    }),
                  if (me != null)
                    item('Sign out', () async {
                      Navigator.of(context).pop();
                      await session.signOut();
                    }),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// My Afe from the canvas: a segmented control over Saved, Viewings and Payments.
class MyAfeScreen extends StatefulWidget {
  const MyAfeScreen({super.key});

  @override
  State<MyAfeScreen> createState() => _MyAfeScreenState();
}

class _MyAfeScreenState extends State<MyAfeScreen> {
  int _tab = 0;

  static const _viewingLabels = {
    'requested': ('Requested', PillTone.warn),
    'confirmed': ('Booked', PillTone.brand),
    'completed': ('Viewed', PillTone.ok),
    'declined': ('Declined', PillTone.quiet),
    'cancelled': ('Cancelled', PillTone.quiet),
    'no_show': ('Missed', PillTone.bad),
  };
  static const _payLabels = {
    'offered': ('Offer', PillTone.warn),
    'funding': ('Paying', PillTone.warn),
    'funded': ('Held', PillTone.warn),
    'disputed': ('On hold', PillTone.bad),
    'release_pending': ('Releasing', PillTone.brand),
    'releasing': ('Releasing', PillTone.brand),
    'released': ('Released', PillTone.ok),
    'refunding': ('Refunding', PillTone.quiet),
    'refunded': ('Refunded', PillTone.quiet),
  };

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    Widget item(String t, String s, (String, PillTone) pill, VoidCallback onTap) => Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Pressable(
        child: Material(
          color: a.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(a.cardRadius),
            side: BorderSide(color: a.line),
          ),
          child: InkWell(
            customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.cardRadius)),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(t, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15.5)),
                      ),
                      StatusPill(pill.$1, tone: pill.$2),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(s, style: TextStyle(fontSize: 13.5, color: a.muted)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    Widget empty(String text) => Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(text, style: TextStyle(fontSize: 14.5, color: a.muted)),
    );

    return Scaffold(
      appBar: const AfeAppBar(title: Text('My Afe')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Segmented<int>(
            items: const [(0, 'Saved'), (1, 'Viewings'), (2, 'Payments')],
            value: _tab,
            onChanged: (v) => setState(() => _tab = v),
          ),
          const SizedBox(height: 16),
          if (_tab == 0)
            Loader<List<Listing>>(
              key: const ValueKey('saved'),
              load: () async => [for (final l in (await context.api.get<List>('/me/saved')).data) Listing(l as Json)],
              builder: (context, homes, _) => Column(
                children: [
                  if (homes.isEmpty) empty('Nothing saved yet. Tap Save on any home to keep it here.'),
                  for (final l in homes)
                    item(l.title, '${l.area} · ${cedis(l.rent)} / month', ('Saved', PillTone.brand), () => openHome(context, l.reference)),
                ],
              ),
            )
          else if (_tab == 1)
            Loader<List<Viewing>>(
              key: const ValueKey('viewings'),
              load: () async => [for (final v in (await context.api.get<List>('/viewings')).data) Viewing(v as Json)],
              builder: (context, list, _) => Column(
                children: [
                  if (list.isEmpty) empty('No viewings booked yet.'),
                  for (final v in list)
                    item(
                      v.listingTitle,
                      '${dayTime(v.when)} · ${v.otherName}',
                      _viewingLabels[v.status] ?? (v.status, PillTone.quiet),
                      () => openThread(context, v.threadId),
                    ),
                ],
              ),
            )
          else
            Loader<List<Tenancy>>(
              key: const ValueKey('payments'),
              load: () async => [for (final t in (await context.api.get<List>('/tenancies')).data) Tenancy(t as Json)],
              builder: (context, list, _) => Column(
                children: [
                  if (list.isEmpty) empty('No payments yet.'),
                  for (final t in list)
                    item(
                      '${t.listingTitle}, ${t.area}',
                      cedis(t.role == 'tenant' ? t.charge : t.held),
                      _payLabels[t.status] ?? (t.status, PillTone.quiet),
                      () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => TenancyScreen(reference: t.reference))),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// "Get verified" for landlords and agents, from the canvas: four steps, each opening the real
/// form (Ghana Card, ownership papers, payout account, the home visit).
class LandlordVerifyScreen extends StatelessWidget {
  const LandlordVerifyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final me = SessionScope.of(context).me!;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Get verified')),
      body: Loader<(List<MyUnit>, Payee?)>(
        load: () async {
          final api = context.api;
          final units = [for (final u in (await api.get<List>('/me/units')).data) MyUnit(u as Json)];
          final p = (await api.get<Json?>('/me/payouts')).data;
          return (units, p == null ? null : Payee(p));
        },
        builder: (context, data, reload) {
          final (units, payee) = data;
          final docs = units.any((u) => u.stage != 'documents');
          final visit = units.any((u) => u.stage == 'review' || u.stage == 'verified');
          final done = [me.verified, docs, payee != null, visit];
          Future<void> open(Widget Function() screen) async {
            final session = context.session;
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen()));
            await session.reloadMe();
            await reload();
          }

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const ScreenTitle('Get verified', lede: 'Four steps, then one home visit. Tap a step to complete it.'),
              const SizedBox(height: 14),
              Panel(
                children: [
                  StepTile(
                    number: 1,
                    title: 'Ghana Card and selfie',
                    subtitle: 'Live check, 3 min',
                    done: done[0],
                    onTap: () => open(VerifyIdentityScreen.new),
                  ),
                  StepTile(
                    number: 2,
                    title: 'Ownership papers',
                    subtitle: 'Indenture or letter of authority',
                    done: done[1],
                    onTap: () => open(
                      () => units.isEmpty
                          ? const AddHomeScreen()
                          : UploadDocumentScreen(
                              unitId: units.firstWhere((u) => u.stage == 'documents', orElse: () => units.first).unit.id,
                            ),
                    ),
                  ),
                  StepTile(
                    number: 3,
                    title: 'Payout account',
                    subtitle: 'Name must match your card',
                    done: done[2],
                    onTap: () => open(PayoutsScreen.new),
                  ),
                  StepTile(
                    number: 4,
                    title: 'The home visit',
                    subtitle: 'A verifier meets you there',
                    done: done[3],
                    onTap: () => open(ListerHomesScreen.new),
                  ),
                ],
              ),
              if (done.every((d) => d)) ...[
                const SizedBox(height: 20),
                const DoneMark(),
                const SizedBox(height: 12),
                Text('Submitted.', style: AfeType.heading(26, color: a.ink)),
                const SizedBox(height: 6),
                Text(
                  'Your listing goes live once the visit passes review, usually within 2 working days.',
                  style: TextStyle(fontSize: 14.5, color: a.muted, height: 1.5),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}
