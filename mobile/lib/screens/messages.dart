import 'package:flutter/material.dart';

import '../api/models.dart';
import '../session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/shell.dart';
import 'offer.dart';

void openThread(BuildContext context, int id) =>
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => ThreadScreen(id: id)));

/// Conversations as the Landlord canvas's enquiry cards: initials, name, home and when, the
/// latest line, and Reply / Open. New ones are outlined in brand.
class MessagesScreen extends StatelessWidget {
  const MessagesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Messages')),
      body: Loader<List<Thread>>(
        load: () async => [for (final t in (await context.api.get<List>('/messages')).data) Thread(t as Json)],
        builder: (context, threads, reload) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const ScreenTitle('Messages', lede: 'Keep the conversation on Afe. Phone numbers are shared once a viewing is booked.'),
            const SizedBox(height: 14),
            if (threads.isEmpty)
              const EmptyState(title: 'No messages yet', body: 'Ask a landlord a question from any verified home.')
            else
              for (final t in threads) ...[
                _ThreadCard(
                  thread: t,
                  onTap: () async {
                    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ThreadScreen(id: t.id)));
                    await reload();
                  },
                ),
                const SizedBox(height: 10),
              ],
            if (threads.isNotEmpty)
              Text('Afe never asks you to pay before a viewing.', style: TextStyle(fontSize: 12.5, color: a.muted)),
          ],
        ),
      ),
    );
  }
}

class _ThreadCard extends StatelessWidget {
  const _ThreadCard({required this.thread, required this.onTap});
  final Thread thread;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final t = thread;
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(a.cardRadius),
      side: BorderSide(color: t.unread ? a.brand : a.line, width: t.unread ? 2 : 1),
    );
    return Semantics(
      button: true,
      label: '${t.otherName}, ${t.listingTitle}${t.unread ? ', new message' : ''}',
      child: Pressable(
        scale: 0.98,
        child: Material(
          color: a.surface,
          shape: shape,
          child: InkWell(
            customBorder: shape,
            onTap: onTap,
            child: Padding(
              padding: EdgeInsets.all(t.unread ? 13 : 14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Initials(name: t.otherName, size: 40, soft: true),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: 8,
                          runSpacing: 2,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Text(t.otherName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                            Text('${t.listingReference} · ${ago(t.lastMessageAt)}', style: TextStyle(fontSize: 12.5, color: a.muted)),
                            if (t.unread) const StatusPill('New', tone: PillTone.warn),
                          ],
                        ),
                        const SizedBox(height: 3),
                        Text(t.listingTitle, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14)),
                        const SizedBox(height: 10),
                        SmallButton(label: t.unread ? 'Reply' : 'Open', onPressed: onTap),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// One conversation: who and which home, any viewings between you, the messages as bubbles (yours
/// on tint, theirs outlined, Afe's notes dashed and centred), and a composer pinned to the bottom.
/// Afe's warnings (e.g. "asked for money before a viewing") show under the message.
class ThreadScreen extends StatefulWidget {
  const ThreadScreen({super.key, required this.id});
  final int id;

  @override
  State<ThreadScreen> createState() => _ThreadScreenState();
}

class _ThreadScreenState extends State<ThreadScreen> {
  final _text = TextEditingController();
  Key _key = UniqueKey();
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final body = _text.text.trim();
    if (body.isEmpty) return;
    setState(() => _sending = true);
    final ok = await attempt(context, () => context.api.post('/messages/${widget.id}', {'body': body}));
    if (!mounted) return;
    setState(() {
      _sending = false;
      if (ok) {
        _text.clear();
        _key = UniqueKey();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final canSend = !_sending && _text.text.trim().isNotEmpty;
    return Scaffold(
      appBar: const AfeAppBar(title: Text('Conversation')),
      body: Column(
        children: [
          Expanded(
            child: Loader<ThreadDetail>(
              key: _key,
              load: () async => ThreadDetail((await context.api.get<Json>('/messages/${widget.id}')).data),
              builder: (context, t, reload) => ListView(
                reverse: true,
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                children: [
                  for (final m in t.messages.reversed) _Bubble(m),
                  if (t.messages.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      child: Text('No messages yet.', textAlign: TextAlign.center, style: TextStyle(color: a.muted)),
                    ),
                  for (final v in t.viewings.reversed)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: ViewingTile(viewing: v, onChanged: reload),
                    ),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: Row(
                      children: [
                        Initials(name: t.otherName, size: 48, soft: true),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t.otherName, style: AfeType.heading(22, color: a.ink)),
                              const SizedBox(height: 2),
                              Text.rich(
                                TextSpan(
                                  children: [
                                    TextSpan(text: '${t.listingTitle} · '),
                                    TextSpan(text: t.listingReference, style: AfeType.mono(12.5, color: a.muted)),
                                  ],
                                ),
                                style: TextStyle(fontSize: 13.5, color: a.muted),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          Container(
            decoration: BoxDecoration(
              color: a.bar,
              border: Border(top: BorderSide(color: a.line)),
            ),
            padding: EdgeInsets.fromLTRB(12, 10, 12, 10 + MediaQuery.paddingOf(context).bottom),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _text,
                        minLines: 1,
                        maxLines: 4,
                        maxLength: 2000,
                        buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                        textCapitalization: TextCapitalization.sentences,
                        decoration: const InputDecoration(hintText: 'Write a message', isDense: true),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SmallButton(label: _sending ? 'Sending…' : 'Send', kind: SmallKind.primary, onPressed: canSend ? _send : null),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  'Afe never asks you to pay before a viewing. Keep payments and contact on Afe.',
                  style: TextStyle(fontSize: 11.5, color: a.muted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.m);
  final Message m;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final meta = Text(
      m.system ? dayTime(m.at) : '${m.mine ? 'You' : m.sender} · ${dayTime(m.at)}',
      style: AfeType.mono(10.5, color: a.muted),
    );
    if (m.system) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Center(
          child: Container(
            constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.86),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(a.cardRadius),
              border: Border.all(color: a.line),
            ),
            child: Column(
              children: [
                Text(m.body, textAlign: TextAlign.center, style: TextStyle(fontSize: 13, color: a.muted, height: 1.4)),
                const SizedBox(height: 4),
                meta,
              ],
            ),
          ),
        ),
      );
    }
    return Align(
      alignment: m.mine ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.8),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: m.mine ? a.tint : a.surface,
              border: Border.all(color: m.mine ? a.tint : a.line),
              borderRadius: BorderRadius.circular(a.cardRadius),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(m.body, style: TextStyle(color: a.ink, fontSize: 15, height: 1.4)),
                if (m.warning.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(m.warning, style: TextStyle(color: a.crit, fontSize: 13.5, fontWeight: FontWeight.w600)),
                ],
                const SizedBox(height: 4),
                meta,
              ],
            ),
          ),
        ),
      ),
    );
  }
}

const _outcomes = {
  'rented_through_afe': 'Yes, and I paid through Afe',
  'paid_directly': 'Yes, but I paid the landlord directly',
  'not_renting': "No, I'm not renting it",
  'still_deciding': "I'm still deciding",
};

const _viewingPill = {
  'requested': PillTone.warn,
  'confirmed': PillTone.brand,
  'completed': PillTone.ok,
  'declined': PillTone.quiet,
  'cancelled': PillTone.quiet,
  'no_show': PillTone.bad,
};

/// A viewing card: when, the status pill, the note, and what this person can do next. The lister
/// confirms or declines, then says whether the renter came; the renter can cancel, and after the
/// viewing says whether they're renting it.
class ViewingTile extends StatelessWidget {
  const ViewingTile({super.key, required this.viewing, required this.onChanged});
  final Viewing viewing;
  final Future<void> Function() onChanged;

  Future<void> _do(BuildContext context, String path, [Object? body, String? done]) async {
    if (await attempt(context, () => context.api.post('/viewings/${viewing.id}/$path', body), done: done)) await onChanged();
  }

  Future<void> _askOutcome(BuildContext context) async {
    final a = context.afe;
    final answer = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Are you renting this home?', style: AfeType.heading(20, color: a.ink)),
              const SizedBox(height: 4),
              Text('Tell Afe what happened after the viewing.', style: TextStyle(fontSize: 13.5, color: a.muted)),
              const SizedBox(height: 12),
              for (final e in _outcomes.entries) ...[
                AfeChip(label: e.value, selected: false, height: 48, onTap: () => Navigator.pop(context, e.key)),
                const SizedBox(height: 8),
              ],
            ],
          ),
        ),
      ),
    );
    if (answer != null && context.mounted) await _do(context, 'outcome', {'answer': answer}, 'Thanks for telling us');
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final v = viewing;
    final lister = v.role == 'lister';
    final past = v.when != null && v.when!.isBefore(DateTime.now());
    final status = switch (v.status) {
      'requested' => lister ? 'Waiting for you' : 'Waiting for the landlord',
      'confirmed' => 'Confirmed',
      'declined' => 'Declined',
      'cancelled' => 'Cancelled',
      'completed' => 'Done',
      'no_show' => lister ? "They didn't come" : 'Not attended',
      _ => v.status,
    };
    final actions = <Widget>[
      if (lister && v.status == 'requested') ...[
        SmallButton(label: 'Confirm', kind: SmallKind.primary, onPressed: () => _do(context, 'respond', {'confirm': true}, 'Viewing confirmed')),
        SmallButton(label: "Can't do this time", onPressed: () => _do(context, 'respond', {'confirm': false}, 'Viewing declined')),
      ],
      if (lister && v.status == 'confirmed' && past) ...[
        SmallButton(label: 'They came', kind: SmallKind.primary, onPressed: () => _do(context, 'complete', {'attended': true})),
        SmallButton(label: "They didn't come", onPressed: () => _do(context, 'complete', {'attended': false})),
      ],
      if (lister && v.status == 'completed')
        SmallButton(
          label: 'Offer a tenancy',
          kind: SmallKind.primary,
          onPressed: () async {
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => OfferScreen(viewing: v)));
            await onChanged();
          },
        ),
      if (!lister && past && v.status != 'cancelled' && v.outcome == null)
        SmallButton(label: 'Are you renting it?', kind: SmallKind.primary, onPressed: () => _askOutcome(context)),
      if ((v.status == 'requested' || v.status == 'confirmed') && !past)
        SmallButton(label: 'Cancel viewing', kind: SmallKind.quiet, onPressed: () => _do(context, 'cancel', null, 'Viewing cancelled')),
    ];
    return Container(
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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('VIEWING', style: AfeType.label(a.muted)),
                    const SizedBox(height: 2),
                    Text(dayTime(v.when), style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                  ],
                ),
              ),
              StatusPill(status, tone: _viewingPill[v.status] ?? PillTone.quiet),
            ],
          ),
          const SizedBox(height: 6),
          Text('${v.listingTitle} · ${v.otherName}', style: TextStyle(fontSize: 13.5, color: a.muted)),
          if (v.note.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('“${v.note}”', style: TextStyle(fontSize: 13.5, color: a.muted)),
          ],
          if (v.status == 'declined' && v.responseNote.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(v.responseNote, style: TextStyle(fontSize: 13.5, color: a.muted)),
          ],
          if (actions.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(spacing: 8, runSpacing: 8, children: actions),
          ],
        ],
      ),
    );
  }
}

/// Every viewing, next ones first, as cards.
class ViewingsScreen extends StatelessWidget {
  const ViewingsScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: const AfeAppBar(title: Text('Viewings')),
    body: Loader<List<Viewing>>(
      load: () async => [for (final v in (await context.api.get<List>('/viewings')).data) Viewing(v as Json)],
      builder: (context, viewings, reload) {
        final now = DateTime.now();
        final upcoming = [for (final v in viewings) if (v.when != null && v.when!.isAfter(now)) v]
          ..sort((x, y) => x.when!.compareTo(y.when!));
        final earlier = [for (final v in viewings) if (!upcoming.contains(v)) v];
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const ScreenTitle('Viewings', lede: 'Never pay before you view. Afe never asks for a viewing fee.'),
            const SizedBox(height: 14),
            if (viewings.isEmpty) const EmptyState(title: 'No viewings yet', body: 'Book one from any verified home.'),
            if (upcoming.isNotEmpty) ...[
              const SectionLabel('Coming up'),
              const SizedBox(height: 8),
              for (final v in upcoming) ...[ViewingTile(viewing: v, onChanged: reload), const SizedBox(height: 10)],
            ],
            if (earlier.isNotEmpty) ...[
              const SizedBox(height: 6),
              const SectionLabel('Earlier'),
              const SizedBox(height: 8),
              for (final v in earlier) ...[ViewingTile(viewing: v, onChanged: reload), const SizedBox(height: 10)],
            ],
          ],
        );
      },
    ),
  );
}
