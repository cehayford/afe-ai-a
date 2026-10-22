import 'package:flutter/material.dart';

import '../api/models.dart';
import '../config.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'auth.dart';
import 'homes.dart';
import 'lister.dart';
import 'me.dart';
import 'messages.dart';
import 'offer.dart';
import 'rentals.dart';
import 'safety.dart';
import 'tenancies.dart';

/// Account: who you are on a card, then panels of rows (your Afe, safety, your data), and sign out.
class AccountScreen extends StatelessWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final session = SessionScope.of(context);
    final me = session.me;
    void push(Widget w) => Navigator.of(context).push(MaterialPageRoute(builder: (_) => w));

    return Scaffold(
      appBar: const AfeAppBar(title: Text('Account')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (me == null) ...[
            const ScreenTitle('Your account', lede: 'Sign in to save homes, message landlords, book viewings and get alerts.'),
            const SizedBox(height: 16),
            PrimaryButton(label: 'Sign in', onPressed: () => push(const SignInScreen())),
            const SizedBox(height: 10),
            SecondaryButton(label: 'Create an account', onPressed: () => push(const SignUpScreen())),
            const SizedBox(height: 18),
          ] else ...[
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: a.surface,
                borderRadius: BorderRadius.circular(a.cardRadius),
                border: Border.all(color: a.line),
              ),
              child: Row(
                children: [
                  Initials(name: me.user.name, size: 52),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(me.user.name, style: AfeType.heading(20, color: a.ink)),
                        const SizedBox(height: 2),
                        Text(me.user.roleLabel, style: TextStyle(fontSize: 13.5, color: a.muted)),
                        if (me.user.phone != null) Text(me.user.phone!, style: AfeType.mono(12.5, color: a.muted)),
                      ],
                    ),
                  ),
                  if (me.verified) const VerifiedBadge(label: 'Verified'),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Panel(
              title: 'Your Afe',
              children: [
                _Row(
                  icon: Icons.notifications_outlined,
                  label: 'Notifications',
                  trailing: me.unread > 0 ? StatusPill('${me.unread} new', tone: PillTone.warn) : null,
                  onTap: () => push(const NotificationsScreen()),
                ),
                _Row(icon: Icons.tune, label: 'Settings', sub: 'Name, email, WhatsApp, devices', onTap: () => push(const SettingsScreen())),
                _Row(icon: Icons.chat_bubble_outline, label: 'Messages', onTap: () => push(const MessagesScreen())),
                if (me.user.isRenter) ...[
                  _Row(icon: Icons.notifications_active_outlined, label: 'Home alerts', onTap: () => push(const AlertsScreen())),
                  _Row(icon: Icons.event_outlined, label: 'Viewings', onTap: () => push(const ViewingsScreen())),
                  _Row(icon: Icons.lock_outline, label: 'Protected payments', onTap: () => push(const TenanciesScreen())),
                  _Row(icon: Icons.home_outlined, label: 'My home', sub: 'Rent, receipts and repairs', onTap: () => push(const MyHomesScreen())),
                ],
                if (me.user.isLister) ...[
                  _Row(icon: Icons.event_outlined, label: 'Viewings', onTap: () => push(const ViewingsScreen())),
                  _Row(icon: Icons.view_list_outlined, label: 'Listings', sub: 'Edit, feature, take down', onTap: () => push(const MyListingsScreen())),
                  _Row(icon: Icons.account_balance_wallet_outlined, label: 'Payouts', onTap: () => push(const PayoutsScreen())),
                  _Row(icon: Icons.receipt_long_outlined, label: 'Tenancies', onTap: () => push(const TenanciesScreen())),
                  _Row(icon: Icons.people_outline, label: 'Tenants and rent', sub: 'Receipts, repairs, agreements', onTap: () => push(const TenantsScreen())),
                  _Row(icon: Icons.receipt_outlined, label: 'Fees paid', onTap: () => push(const FeesScreen())),
                ],
                _Row(icon: Icons.gavel_outlined, label: 'Appeals', sub: 'Ask for a decision to be looked at again', onTap: () => push(const AppealsScreen())),
              ],
            ),
            const SizedBox(height: 16),
          ],
          Panel(
            title: 'Safety and help',
            children: [
              if (me == null || !me.user.isVerifier)
                _Row(icon: Icons.shield_outlined, label: 'Check before you pay', onTap: () => push(const CheckScreen())),
              _Row(icon: Icons.report_outlined, label: 'Report a scam', onTap: () => push(const ReportScamScreen())),
              _Row(icon: Icons.bar_chart_outlined, label: 'Rent index', sub: 'What rent really costs', onTap: () => push(const RentIndexScreen())),
              _Row(icon: Icons.privacy_tip_outlined, label: 'Privacy notice', external: true, onTap: () => openWeb('/privacy')),
              _Row(icon: Icons.description_outlined, label: 'Terms', external: true, onTap: () => openWeb('/terms')),
              if (me != null)
                _Row(
                  icon: Icons.download_outlined,
                  label: 'Download my data, close my account',
                  sub: 'On the website',
                  external: true,
                  onTap: () => openWeb('/account'),
                ),
            ],
          ),
          if (me != null) ...[
            const SizedBox(height: 16),
            SecondaryButton(label: 'Sign out', icon: Icons.logout, onPressed: () => session.signOut()),
          ],
          const SizedBox(height: 18),
          Text('Afe ${AppConfig.version}', textAlign: TextAlign.center, style: AfeType.mono(11.5, color: a.muted)),
        ],
      ),
    );
  }
}

/// One row in an account panel: icon, label (and a note), then a badge, ↗ for the website, or ›.
class _Row extends StatelessWidget {
  const _Row({required this.icon, required this.label, required this.onTap, this.sub, this.trailing, this.external = false});
  final IconData icon;
  final String label;
  final String? sub;
  final Widget? trailing;
  final bool external;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 52),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(
            children: [
              Icon(icon, size: 21, color: a.accent),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
                    if (sub != null) Text(sub!, style: TextStyle(fontSize: 12.5, color: a.muted)),
                  ],
                ),
              ),
              if (trailing != null) ...[trailing!, const SizedBox(width: 8)],
              Text(external ? '↗' : '›', style: TextStyle(color: a.muted, fontSize: external ? 16 : 20)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Notifications as the website's list: a dot on the new ones, the title, the text, and how long
/// ago. Opening the screen marks them read.
class NotificationsScreen extends StatelessWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Notifications')),
      body: Loader<List<AppNotification>>(
        load: () async {
          final list = [for (final n in (await context.api.get<List>('/me/notifications')).data) AppNotification(n as Json)];
          if (list.any((n) => !n.read) && context.mounted) {
            await context.api.post('/me/notifications/read', {'ids': null});
            if (context.mounted) await context.session.reloadMe();
          }
          return list;
        },
        builder: (context, list, _) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const ScreenTitle('Notifications', lede: 'Viewings, offers, payments and alerts.'),
            const SizedBox(height: 14),
            if (list.isEmpty)
              const EmptyState(title: 'Nothing new', body: 'Viewings, offers, payments and alerts appear here.')
            else
              Panel(
                children: [
                  for (final n in list)
                    InkWell(
                      onTap: () => _follow(context, n.link),
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              margin: const EdgeInsets.only(top: 7, right: 10),
                              decoration: BoxDecoration(color: n.read ? Colors.transparent : a.amber, shape: BoxShape.circle),
                            ),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(n.title, style: TextStyle(fontSize: 14.5, fontWeight: n.read ? FontWeight.w500 : FontWeight.w700)),
                                  const SizedBox(height: 2),
                                  Text(n.body, style: TextStyle(fontSize: 13.5, color: a.muted, height: 1.4)),
                                ],
                              ),
                            ),
                            const SizedBox(width: 10),
                            Text(ago(n.at), style: AfeType.mono(11, color: a.muted)),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  /// Notification links are website paths; open the matching app screen where there is one.
  void _follow(BuildContext context, String link) {
    Widget? screen;
    final home = RegExp(r'^/homes/([^/?#]+)').firstMatch(link);
    final tenancy = RegExp(r'^/tenancies/([^/?#]+)').firstMatch(link);
    final thread = RegExp(r'^/account/messages/(\d+)').firstMatch(link);
    if (home != null) {
      screen = HomeScreen(reference: home.group(1)!);
    } else if (tenancy != null) {
      screen = TenancyScreen(reference: tenancy.group(1)!);
    } else if (thread != null) {
      screen = ThreadScreen(id: int.parse(thread.group(1)!));
    } else if (link.startsWith('/account/viewings') || link.startsWith('/landlord/viewings')) {
      screen = const ViewingsScreen();
    } else if (link.startsWith('/tenancies')) {
      screen = const TenanciesScreen();
    }
    if (screen != null) {
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen!));
    } else if (link.startsWith('/')) {
      openWeb(link);
    }
  }
}
