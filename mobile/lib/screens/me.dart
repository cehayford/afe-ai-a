import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../config.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'auth.dart' show openWeb;

// Account screens from the "Afe Missing Features" canvas: Settings, Fees paid and Appeals.

/// Settings: name, email and WhatsApp messages; the devices signed in; sign out everywhere.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _name;
  late final TextEditingController _email;
  bool _whatsapp = true;
  bool _saving = false;
  bool _confirm = false;
  String? _error;
  Future<List<Device>>? _devices;

  @override
  void initState() {
    super.initState();
    final user = context.session.me!.user;
    _name = TextEditingController(text: user.displayName.isEmpty ? user.name : user.displayName);
    _email = TextEditingController(text: user.email ?? '');
    _whatsapp = user.whatsappOptIn;
    _devices = _loadDevices();
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    super.dispose();
  }

  Future<List<Device>> _loadDevices() async => [for (final d in (await context.api.get<List>('/me/devices')).data) Device(d as Json)];

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await context.api.patch('/me', {'display_name': _name.text.trim(), 'email': _email.text.trim(), 'whatsapp_opt_in': _whatsapp});
      if (!mounted) return;
      await context.session.reloadMe();
      if (mounted) toast(context, 'Saved.');
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.reasons.isEmpty ? e.message : '${e.message} ${e.reasons.join(' ')}');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _everywhere() async {
    if (!_confirm) {
      setState(() => _confirm = true);
      return;
    }
    final session = context.session;
    final nav = Navigator.of(context);
    if (await attempt(context, () => session.signOutEverywhere(), done: 'Signed out everywhere.')) {
      nav.popUntil((r) => r.isFirst);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final me = SessionScope.of(context).me;
    if (me == null) return const Scaffold(appBar: AfeAppBar(title: Text('Settings')), body: SizedBox.shrink());
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const ScreenTitle('Your details', lede: "Your phone number signs you in, so it can't be changed here."),
          const SizedBox(height: 16),
          if (!me.user.privacyCurrent) ...[
            Note("We've updated our privacy notice. Read what changed, then accept it to keep using Afe.", kind: NoteKind.warn, lead: 'Privacy notice.'),
            const SizedBox(height: 8),
            Row(
              children: [
                SmallButton(label: 'Read it', kind: SmallKind.quiet, onPressed: () => openWeb('/privacy')),
                const SizedBox(width: 8),
                SmallButton(
                  label: 'I accept',
                  kind: SmallKind.primary,
                  onPressed: () async {
                    final session = context.session;
                    if (await attempt(context, () => context.api.post('/me/privacy'), done: 'Thank you.')) await session.reloadMe();
                  },
                ),
              ],
            ),
            const SizedBox(height: 16),
          ],
          if (_error != null) ...[Note(_error!, kind: NoteKind.error), const SizedBox(height: 12)],
          const FieldLabel('Name'),
          TextField(controller: _name, textCapitalization: TextCapitalization.words),
          const SizedBox(height: 14),
          const FieldLabel('Email', optional: true),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(hintText: 'ama@example.com'),
          ),
          const SizedBox(height: 14),
          Material(
            color: a.surface,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(a.cardRadius),
              side: BorderSide(color: a.line),
            ),
            child: SwitchListTile.adaptive(
              value: _whatsapp,
              onChanged: (v) => setState(() => _whatsapp = v),
              title: const Text('Messages on WhatsApp', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
              subtitle: Text('Codes, viewings and payments. SMS if WhatsApp fails.', style: TextStyle(fontSize: 12.5, color: a.muted)),
              activeTrackColor: a.ok,
            ),
          ),
          const SizedBox(height: 16),
          PrimaryButton(label: 'Save', busy: _saving, onPressed: _save),
          const SizedBox(height: 20),
          FutureBuilder<List<Device>>(
            future: _devices,
            builder: (context, snap) => Panel(
              title: 'Signed-in devices',
              children: [
                if (snap.connectionState != ConnectionState.done)
                  const Padding(padding: EdgeInsets.all(14), child: LinearProgressIndicator())
                else if (snap.hasError || (snap.data ?? []).isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(14),
                    child: Text('Only this phone.', style: TextStyle(color: a.muted)),
                  )
                else
                  for (final d in snap.data!)
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(d.name.isEmpty ? 'Unknown device' : d.name, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w500)),
                          Text('since ${day(d.since)}', style: AfeType.mono(11.5, color: a.muted)),
                        ],
                      ),
                    ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          if (_confirm) ...[
            const Note('Every device, this one too, signs out. You sign in again with a code.', kind: NoteKind.warn, lead: 'Sure?'),
            const SizedBox(height: 10),
          ],
          SecondaryButton(label: _confirm ? 'Yes, sign out everywhere' : 'Sign out everywhere', danger: true, onPressed: _everywhere),
          const SizedBox(height: 18),
          Text(
            'Afe ${AppConfig.version}',
            textAlign: TextAlign.center,
            style: AfeType.mono(11.5, color: a.muted),
          ),
        ],
      ),
    );
  }
}

const _purpose = {'verification_fee': 'Verification fee', 'featured_listing': 'Featured listing', 'subscription': 'Landlord tools plan'};

/// Fees paid through Afe's payment partner, newest first; a waiting one can be finished.
class FeesScreen extends StatelessWidget {
  const FeesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Fees paid')),
      body: Loader<List<FeePayment>>(
        load: () async => [for (final p in (await context.api.get<List>('/me/payments')).data) FeePayment(p as Json)],
        builder: (context, fees, reload) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const ScreenTitle('Fees paid', lede: "Verification fees, featured listings and plans you paid through Afe's payment partner."),
            const SizedBox(height: 14),
            if (fees.isEmpty) const EmptyState(title: 'Nothing yet', body: 'Fees you pay for verification or featured listings appear here.'),
            for (final f in fees) ...[_FeeCard(fee: f, onPaid: reload), const SizedBox(height: 10)],
            if (fees.isNotEmpty) Text('Rent held with Afe is on each tenancy, not here.', style: TextStyle(fontSize: 12.5, color: a.muted)),
          ],
        ),
      ),
    );
  }
}

class _FeeCard extends StatelessWidget {
  const _FeeCard({required this.fee, required this.onPaid});
  final FeePayment fee;
  final Future<void> Function() onPaid;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final f = fee;
    final waiting = f.status == 'pending';
    final (label, tone) = switch (f.status) {
      'paid' => ('Paid', PillTone.ok),
      'pending' => ('Waiting', PillTone.warn),
      'waived' => ('Waived', PillTone.quiet),
      _ => ('Failed', PillTone.bad),
    };
    return Container(
      padding: EdgeInsets.all(waiting ? 13 : 14),
      decoration: BoxDecoration(
        color: a.surface,
        borderRadius: BorderRadius.circular(a.cardRadius),
        border: Border.all(color: waiting ? a.amber : a.line, width: waiting ? 2 : 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(_purpose[f.purpose] ?? f.purpose, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15.5)),
              ),
              StatusPill(label, tone: tone),
            ],
          ),
          const SizedBox(height: 4),
          Text([if (f.subject.isNotEmpty) f.subject, day(f.at)].join(' · '), style: TextStyle(fontSize: 13.5, color: a.muted)),
          if (f.note.isNotEmpty) Text(f.note, style: TextStyle(fontSize: 12.5, color: a.muted)),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: Text(cedis(f.amount), style: AfeType.heading(20, color: a.accent)),
              ),
              Text(f.reference, style: AfeType.mono(11.5, color: a.muted)),
            ],
          ),
          if (waiting && f.checkoutUrl.isNotEmpty) ...[
            const SizedBox(height: 10),
            PrimaryButton(
              label: 'Finish paying',
              onPressed: () async {
                await launchUrl(Uri.parse(f.checkoutUrl), mode: LaunchMode.externalApplication);
                await onPaid();
              },
            ),
          ],
          const SizedBox(height: 8),
          SmallButton(
            label: waiting || f.status == 'failed' ? 'Invoice (PDF)' : 'Receipt (PDF)',
            kind: SmallKind.quiet,
            onPressed: () => openDocument(context, 'fee', f.reference),
          ),
        ],
      ),
    );
  }
}

const _appealKind = {'verification': 'Verification', 'listing': 'Listing', 'report': 'Scam report'};

/// Appeals: the decisions you can still appeal, and the appeals you sent with their outcome.
class AppealsScreen extends StatefulWidget {
  const AppealsScreen({super.key});

  @override
  State<AppealsScreen> createState() => _AppealsScreenState();
}

class _AppealsScreenState extends State<AppealsScreen> {
  String _tab = 'decisions';

  Future<(List<Appealable>, List<Appeal>)> _load() async {
    final api = context.api;
    final open = [for (final x in (await api.get<List>('/me/appealable')).data) Appealable(x as Json)];
    final mine = [for (final x in (await api.get<List>('/me/appeals')).data) Appeal(x as Json)];
    return (open, mine);
  }

  Future<void> _appeal(Appealable d, Future<void> Function() reload) async {
    final sent = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _AppealSheet(decision: d),
    );
    if (sent == true) {
      await reload();
      if (mounted) setState(() => _tab = 'mine');
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Appeals')),
      body: Loader<(List<Appealable>, List<Appeal>)>(
        load: _load,
        builder: (context, data, reload) {
          final (open, mine) = data;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const ScreenTitle('Appeals', lede: 'Think Afe got a decision wrong? Each decision can be appealed once. A different reviewer decides.'),
              const SizedBox(height: 14),
              Segmented<String>(
                items: [('decisions', 'Decisions (${open.length})'), ('mine', 'My appeals (${mine.length})')],
                value: _tab,
                onChanged: (v) => setState(() => _tab = v),
              ),
              const SizedBox(height: 14),
              if (_tab == 'decisions') ...[
                if (open.isEmpty) const EmptyState(title: 'Nothing to appeal', body: "Decisions about you that you haven't appealed yet show here."),
                for (final d in open) ...[
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
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(d.label, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15.5)),
                            ),
                            const SizedBox(width: 8),
                            _KindTag(_appealKind[d.kind] ?? d.kind, bad: d.kind != 'listing'),
                          ],
                        ),
                        if (d.date != null) Text('Decided ${day(d.date)}', style: TextStyle(fontSize: 13.5, color: a.muted)),
                        const SizedBox(height: 10),
                        SmallButton(label: 'Appeal this decision', onPressed: () => _appeal(d, reload)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                ],
              ] else ...[
                if (mine.isEmpty) const EmptyState(title: 'No appeals yet', body: 'Appeals you send, and what the reviewer decided, show here.'),
                for (final x in mine) ...[
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
                              child: Text(_appealKind[x.kind] ?? x.kind, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15.5)),
                            ),
                            StatusPill(
                              switch (x.status) {
                                'upheld' => 'Upheld',
                                'rejected' => 'Not upheld',
                                _ => 'With Afe',
                              },
                              tone: switch (x.status) {
                                'upheld' => PillTone.ok,
                                'rejected' => PillTone.quiet,
                                _ => PillTone.warn,
                              },
                            ),
                          ],
                        ),
                        Text(
                          x.decidedAt == null ? 'Sent ${day(x.at)} · a different reviewer decides' : 'Sent ${day(x.at)} · decided ${day(x.decidedAt)}',
                          style: TextStyle(fontSize: 13.5, color: a.muted),
                        ),
                        if (x.outcome.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                            decoration: BoxDecoration(color: a.bg, borderRadius: BorderRadius.circular(a.inputRadius)),
                            child: Text(x.outcome, style: const TextStyle(fontSize: 14, height: 1.45)),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                ],
              ],
            ],
          );
        },
      ),
    );
  }
}

class _KindTag extends StatelessWidget {
  const _KindTag(this.text, {this.bad = false});
  final String text;
  final bool bad;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: bad ? a.critSoft : a.warnSoft, borderRadius: BorderRadius.circular(4)),
      child: Text(text, style: AfeType.mono(11, color: bad ? a.crit : a.warn)),
    );
  }
}

/// The appeal form as a bottom sheet: the reason, at least 30 characters, then Send.
class _AppealSheet extends StatefulWidget {
  const _AppealSheet({required this.decision});
  final Appealable decision;

  @override
  State<_AppealSheet> createState() => _AppealSheetState();
}

class _AppealSheetState extends State<_AppealSheet> {
  final _reason = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _reason.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.api.post('/me/appeals', {'kind': widget.decision.kind, 'subject_id': widget.decision.subjectId, 'reason': _reason.text.trim()});
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final n = _reason.text.trim().length;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 0, 16, 16 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Appeal: ${widget.decision.label}', style: AfeType.heading(21, color: a.ink)),
          const SizedBox(height: 4),
          Text('Say what the reviewer missed. You can appeal this once.', style: TextStyle(fontSize: 14, color: a.muted)),
          const SizedBox(height: 12),
          if (_error != null) ...[Note(_error!, kind: NoteKind.error), const SizedBox(height: 10)],
          const FieldLabel('Why the decision is wrong'),
          TextField(controller: _reason, minLines: 4, maxLines: 8, maxLength: 4000, textCapitalization: TextCapitalization.sentences),
          Text(n >= 30 ? '$n characters' : '$n of at least 30 characters', style: TextStyle(fontSize: 12.5, color: n >= 30 ? a.ok : a.muted)),
          const SizedBox(height: 12),
          PrimaryButton(label: 'Send appeal', busy: _busy, onPressed: n >= 30 ? _send : null),
        ],
      ),
    );
  }
}
