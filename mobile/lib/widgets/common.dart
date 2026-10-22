import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../session.dart';
import '../theme.dart';

final _day = DateFormat('EEE d MMM');
final _dayTime = DateFormat('EEE d MMM, HH:mm');
final _short = DateFormat('d MMM');

String day(DateTime? t) => t == null ? '' : _day.format(t);
String dayTime(DateTime? t) => t == null ? '' : _dayTime.format(t);
String shortDay(DateTime? t) => t == null ? '' : _short.format(t);

/// "2 h ago", "Yesterday", "3 days ago" (the website's `ago`).
String ago(DateTime? t) {
  if (t == null) return '';
  final mins = DateTime.now().difference(t).inMinutes;
  if (mins < 60) return mins <= 1 ? 'Just now' : '$mins min ago';
  final hours = (mins / 60).round();
  if (hours < 24) return '$hours h ago';
  final days = (hours / 24).round();
  return days == 1 ? 'Yesterday' : days < 7 ? '$days days ago' : day(t);
}

String bedroomsLabel(int n) => switch (n) {
  0 => 'Single room',
  1 => '1 bedroom',
  _ => '$n bedrooms',
};

/// The design sets money with a space after the symbol: "GH₵3,500" -> "GH₵ 3,500".
String cedis(String display) => display.replaceFirst(RegExp(r'^GH₵\s?'), 'GH₵ ');

/// Pesewas as the design sets money: 300000 -> "GH₵ 3,000", 150050 -> "GH₵ 1,500.50".
String ghs(int pesewas) {
  final cedi = pesewas / 100;
  final f = NumberFormat.decimalPatternDigits(locale: 'en', decimalDigits: pesewas % 100 == 0 ? 0 : 2);
  return 'GH₵ ${f.format(cedi)}';
}

/// "2026-09-26" for the API's date fields.
String isoDay(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// Pressable things shrink slightly under the finger (0.97, 160 ms, ease-out) so the app
/// feels like it heard the tap. A Listener doesn't compete with the child's own gestures.
class Pressable extends StatefulWidget {
  const Pressable({super.key, required this.child, this.scale = 0.97});
  final Widget child;
  final double scale;

  @override
  State<Pressable> createState() => _PressableState();
}

class _PressableState extends State<Pressable> {
  bool _down = false;

  void _set(bool v) {
    if (_down != v) setState(() => _down = v);
  }

  @override
  Widget build(BuildContext context) {
    if (Motion.reduced(context)) return widget.child;
    return Listener(
      onPointerDown: (_) => _set(true),
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: AnimatedScale(scale: _down ? widget.scale : 1, duration: Motion.press, curve: Motion.easeOut, child: widget.child),
    );
  }
}

/// A main action: full width, press feedback, and a spinner while it works.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({super.key, required this.label, required this.onPressed, this.busy = false, this.icon});
  final String label;
  final VoidCallback? onPressed;
  final bool busy;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final child = busy ? SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2.4, color: a.onBrand)) : Text(label);
    return Pressable(
      child: SizedBox(
        width: double.infinity,
        child: icon == null
            ? FilledButton(onPressed: busy ? null : onPressed, child: child)
            : FilledButton.icon(onPressed: busy ? null : onPressed, icon: Icon(icon, size: 20), label: child),
      ),
    );
  }
}

class SecondaryButton extends StatelessWidget {
  const SecondaryButton({super.key, required this.label, required this.onPressed, this.icon, this.danger = false});
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final style = danger
        ? OutlinedButton.styleFrom(
            foregroundColor: a.crit,
            side: BorderSide(color: a.crit),
          )
        : null;
    return Pressable(
      child: SizedBox(
        width: double.infinity,
        child: icon == null
            ? OutlinedButton(style: style, onPressed: onPressed, child: Text(label))
            : OutlinedButton.icon(style: style, onPressed: onPressed, icon: Icon(icon, size: 20), label: Text(label)),
      ),
    );
  }
}

/// A compact action inside a card (Reply, Confirm, Take down): 40 px high and sized to its label,
/// like the canvas's small buttons. [kind] picks filled, outlined in brand, quiet, or danger.
class SmallButton extends StatelessWidget {
  const SmallButton({super.key, required this.label, required this.onPressed, this.kind = SmallKind.secondary});
  final String label;
  final VoidCallback? onPressed;
  final SmallKind kind;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    const text = TextStyle(fontFamily: AfeType.sans, fontSize: 14, fontWeight: FontWeight.w600);
    const pad = EdgeInsets.symmetric(horizontal: 14);
    const size = Size(0, 40);
    final child = Text(label);
    return Pressable(
      child: SizedBox(
        height: 40,
        child: switch (kind) {
          SmallKind.primary => FilledButton(
            style: FilledButton.styleFrom(minimumSize: size, padding: pad, textStyle: text),
            onPressed: onPressed,
            child: child,
          ),
          SmallKind.secondary => OutlinedButton(
            style: OutlinedButton.styleFrom(
              minimumSize: size,
              padding: pad,
              textStyle: text,
              foregroundColor: a.brand,
              side: BorderSide(color: onPressed == null ? a.line : a.brand),
            ),
            onPressed: onPressed,
            child: child,
          ),
          SmallKind.quiet => TextButton(
            style: TextButton.styleFrom(minimumSize: size, padding: pad, textStyle: text, foregroundColor: a.brand),
            onPressed: onPressed,
            child: child,
          ),
          SmallKind.danger => OutlinedButton(
            style: OutlinedButton.styleFrom(
              minimumSize: size,
              padding: pad,
              textStyle: text,
              foregroundColor: a.crit,
              side: BorderSide(color: a.crit),
            ),
            onPressed: onPressed,
            child: child,
          ),
        },
      ),
    );
  }
}

enum SmallKind { primary, secondary, quiet, danger }

/// A message the person needs to read: an error, a warning, or good news. [lead] is set in bold
/// before the text ("Keep it private.").
class Note extends StatelessWidget {
  const Note(this.text, {super.key, this.kind = NoteKind.info, this.lead});
  final String text;
  final NoteKind kind;
  final String? lead;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final (bg, fg) = switch (kind) {
      NoteKind.error => (a.critSoft, a.crit),
      NoteKind.warn => (a.warnSoft, a.ink),
      NoteKind.ok => (a.okSoft, a.ok),
      NoteKind.info => (a.tint, a.ink),
    };
    return Semantics(
      liveRegion: kind == NoteKind.error,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(a.cardRadius)),
        child: Text.rich(
          TextSpan(
            children: [
              if (lead != null)
                TextSpan(
                  text: '$lead  ',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              TextSpan(text: text),
            ],
          ),
          style: TextStyle(color: fg, height: 1.45, fontSize: 13.5),
        ),
      ),
    );
  }
}

enum NoteKind { info, ok, warn, error }

/// The "never pay before you view" line renter screens repeat.
class NeverPayBanner extends StatelessWidget {
  const NeverPayBanner({super.key});

  @override
  Widget build(BuildContext context) =>
      const Note('Pay only through Afe. Afe never asks for a viewing fee.', kind: NoteKind.warn, lead: 'Never pay before you view.');
}

/// A small rounded status label.
class StatusPill extends StatelessWidget {
  const StatusPill(this.text, {super.key, this.tone = PillTone.brand});
  final String text;
  final PillTone tone;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final (bg, fg) = switch (tone) {
      PillTone.ok => (a.okSoft, a.ok),
      PillTone.warn => (a.warnSoft, a.warn),
      PillTone.bad => (a.critSoft, a.crit),
      PillTone.quiet => (a.tint, a.muted),
      PillTone.next => (a.brand, a.onBrand),
      PillTone.brand => (a.tint, a.accent),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(99)),
      child: Text(
        text,
        style: TextStyle(color: fg, fontSize: 11.5, fontWeight: FontWeight.w600),
      ),
    );
  }
}

enum PillTone { brand, ok, warn, bad, quiet, next }

class VerifiedBadge extends StatelessWidget {
  const VerifiedBadge({super.key, this.label = 'Verified by Afe'});
  final String label;

  @override
  Widget build(BuildContext context) => StatusPill('✓ $label', tone: PillTone.ok);
}

/// "NOT VERIFIED BY AFE": mono uppercase tag on the warning colour.
class WarnTag extends StatelessWidget {
  const WarnTag(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: a.warn, borderRadius: BorderRadius.circular(4)),
      child: Text(text.toUpperCase(), style: AfeType.label(a.bg, size: 11)),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.title, this.body, this.action});
  final String title;
  final String? body;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 48, 24, 24),
      child: Column(
        children: [
          Text(
            title,
            textAlign: TextAlign.center,
            style: AfeType.heading(19, color: a.ink),
          ),
          if (body != null) ...[
            const SizedBox(height: 6),
            Text(
              body!,
              textAlign: TextAlign.center,
              style: TextStyle(color: a.muted, fontSize: 14.5),
            ),
          ],
          if (action != null) ...[const SizedBox(height: 16), action!],
        ],
      ),
    );
  }
}

/// A big title and a muted line under it: the top of most screens.
class ScreenTitle extends StatelessWidget {
  const ScreenTitle(this.title, {super.key, this.lede, this.size = 26});
  final String title;
  final String? lede;
  final double size;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: AfeType.heading(size, color: a.ink)),
        if (lede != null) ...[const SizedBox(height: 6), Text(lede!, style: TextStyle(color: a.muted, fontSize: 14.5, height: 1.45))],
      ],
    );
  }
}

/// Loads something from the API and shows it, with a spinner, a readable error with Retry,
/// and pull to refresh. [builder] gets a `reload` callback for after actions.
class Loader<T> extends StatefulWidget {
  const Loader({super.key, required this.load, required this.builder});
  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;

  @override
  State<Loader<T>> createState() => _LoaderState<T>();
}

class _LoaderState<T> extends State<Loader<T>> {
  T? _data;
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = _data == null;
      _error = null;
    });
    try {
      final data = await widget.load();
      if (mounted) setState(() => _data = data);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_data == null) {
      return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Note(_error is ApiException ? '$_error' : 'Something went wrong. Try again.', kind: NoteKind.error),
          const SizedBox(height: 12),
          SecondaryButton(label: 'Try again', onPressed: _reload),
        ],
      );
    }
    return RefreshIndicator(onRefresh: _reload, child: widget.builder(context, _data as T, _reload));
  }
}

/// Diagonal stripes: the design's stand-in where a photo isn't there yet.
class Stripes extends StatelessWidget {
  const Stripes({super.key, this.child, this.step = 8});
  final Widget? child;
  final double step;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return CustomPaint(painter: _StripePainter(a.tint, a.bg, step), child: child ?? const SizedBox.expand());
  }
}

class _StripePainter extends CustomPainter {
  _StripePainter(this.a, this.b, this.step);
  final Color a, b;
  final double step;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = b);
    final p = Paint()
      ..color = a
      ..strokeWidth = step * 0.72;
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    for (var x = -size.height; x < size.width + size.height; x += step * 2) {
      canvas.drawLine(Offset(x, size.height), Offset(x + size.height, 0), p);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_StripePainter old) => old.a != a || old.b != b;
}

/// A network photo that fades in once it has loaded (content arriving, 220 ms ease-out).
class NetPhoto extends StatelessWidget {
  const NetPhoto(this.url, {super.key, this.fit = BoxFit.cover, this.semanticLabel});
  final String? url;
  final BoxFit fit;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    const placeholder = Stripes();
    if (url == null || url!.isEmpty) return placeholder;
    return Image.network(
      url!,
      fit: fit,
      semanticLabel: semanticLabel,
      errorBuilder: (_, _, _) => placeholder,
      frameBuilder: (context, child, frame, wasSynchronous) {
        if (wasSynchronous || Motion.reduced(context)) return child;
        return Stack(
          fit: StackFit.passthrough,
          children: [
            placeholder,
            AnimatedOpacity(opacity: frame == null ? 0 : 1, duration: Motion.appear, curve: Motion.easeOut, child: child),
          ],
        );
      },
    );
  }
}

/// A verified home in a list, as on the canvas's search screen: square photo, title, area and
/// size, the verified pill, then rent.
class ListingCard extends StatelessWidget {
  const ListingCard({super.key, required this.listing, required this.onTap});
  final Listing listing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final from = listing.availableFrom;
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
                  child: SizedBox.square(dimension: 84, child: NetPhoto(listing.coverUrl, semanticLabel: listing.title)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(listing.title, style: AfeType.heading(17, color: a.ink, height: 1.15)),
                      const SizedBox(height: 4),
                      Text(
                        [listing.area, bedroomsLabel(listing.bedrooms), if (from != null) 'From ${shortDay(from)}'].join(' · '),
                        style: TextStyle(fontSize: 13, color: a.muted),
                      ),
                      const SizedBox(height: 4),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          if (listing.status == 'live') const StatusPill('✓ Landlord + home verified', tone: PillTone.ok),
                          if (listing.featured) const StatusPill('Featured', tone: PillTone.warn),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: cedis(listing.rent),
                              style: AfeType.heading(17, color: a.accent),
                            ),
                            TextSpan(
                              text: ' / month',
                              style: TextStyle(fontSize: 12, color: a.muted),
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
      ),
    );
  }
}

/// One choice among a few (bedrooms, day, time): pill on iOS, 8 px corners on Android.
class AfeChip extends StatelessWidget {
  const AfeChip({super.key, required this.label, required this.selected, required this.onTap, this.height});
  final String label;
  final bool selected;
  final VoidCallback onTap;
  final double? height;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Semantics(
      button: true,
      selected: selected,
      child: Pressable(
        child: Material(
          color: selected ? a.tint : a.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(a.chipRadius),
            side: BorderSide(color: selected ? a.brand : a.line),
          ),
          child: InkWell(
            onTap: onTap,
            customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.chipRadius)),
            child: Container(
              height: height ?? a.chipHeight,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              alignment: Alignment.center,
              child: Text(
                label,
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: a.ink),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A row of [AfeChip]s that scrolls sideways.
class ChipRow<T> extends StatelessWidget {
  const ChipRow({super.key, required this.items, required this.value, required this.onChanged, this.padding = EdgeInsets.zero});
  final List<(T, String)> items;
  final T value;
  final ValueChanged<T> onChanged;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    padding: padding,
    child: Row(
      children: [
        for (final (v, label) in items) ...[
          AfeChip(label: label, selected: v == value, onTap: () => onChanged(v)),
          const SizedBox(width: 8),
        ],
      ],
    ),
  );
}

/// Segmented control (My Afe: Saved, Viewings, Payments). iOS: white thumb on tint; Android:
/// the selected segment filled in brand.
class Segmented<T> extends StatelessWidget {
  const Segmented({super.key, required this.items, required this.value, required this.onChanged});
  final List<(T, String)> items;
  final T value;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: a.tint, borderRadius: BorderRadius.circular(a.segmentRadius)),
      child: Row(
        children: [
          for (final (v, label) in items)
            Expanded(
              child: Semantics(
                button: true,
                selected: v == value,
                child: GestureDetector(
                  onTap: () => onChanged(v),
                  child: AnimatedContainer(
                    duration: Motion.reduced(context) ? Duration.zero : Motion.press,
                    curve: Motion.easeOut,
                    height: a.ios ? 32 : 36,
                    margin: const EdgeInsets.symmetric(horizontal: 1),
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: v == value ? (a.ios ? a.surface : a.brand) : Colors.transparent,
                      borderRadius: BorderRadius.circular(a.ios ? 7 : 18),
                      boxShadow: v == value && a.ios
                          ? const [BoxShadow(color: Color(0x26000000), blurRadius: 3, offset: Offset(0, 1))]
                          : null,
                    ),
                    child: Text(
                      label,
                      style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: v == value && !a.ios ? a.onBrand : a.ink),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A white card with an optional header row and hairline-separated rows.
class Panel extends StatelessWidget {
  const Panel({super.key, this.title, this.trailing, required this.children, this.padded = false});
  final String? title;
  final Widget? trailing;
  final List<Widget> children;
  final bool padded;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      decoration: BoxDecoration(
        color: a.surface,
        borderRadius: BorderRadius.circular(a.cardRadius),
        border: Border.all(color: a.line),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: a.line)),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(title!, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                  ),
                  ?trailing,
                ],
              ),
            ),
          for (var i = 0; i < children.length; i++)
            DecoratedBox(
              decoration: BoxDecoration(
                border: i < children.length - 1 ? Border(bottom: BorderSide(color: a.tint)) : null,
              ),
              child: padded ? Padding(padding: const EdgeInsets.all(14), child: children[i]) : children[i],
            ),
        ],
      ),
    );
  }
}

/// A checked line in a verification record: green tick, text, and the date in mono.
class CheckLine extends StatelessWidget {
  const CheckLine(this.text, {super.key, this.date, this.state = true});
  final String text;
  final String? date;

  /// true = passed, false = failed, null = not done.
  final bool? state;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final (bg, fg, mark) = switch (state) {
      true => (a.okSoft, a.ok, '✓'),
      false => (a.critSoft, a.crit, '✕'),
      null => (a.tint, a.muted, '–'),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(
        children: [
          Container(
            width: 20,
            height: 20,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: bg, shape: BoxShape.circle),
            child: Text(
              mark,
              style: TextStyle(color: fg, fontSize: 12, fontWeight: FontWeight.w700),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 14))),
          if (date != null && date!.isNotEmpty) Text(date!, style: AfeType.mono(11, color: a.muted)),
        ],
      ),
    );
  }
}

/// Mono labels over values in equal cells, split by hairlines (Beds · Type · From).
class FactsGrid extends StatelessWidget {
  const FactsGrid(this.cells, {super.key});
  final List<(String, String)> cells;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      decoration: BoxDecoration(
        color: a.surface,
        borderRadius: BorderRadius.circular(a.cardRadius),
        border: Border.all(color: a.line),
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var i = 0; i < cells.length; i++)
              Expanded(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    border: i > 0 ? Border(left: BorderSide(color: a.line)) : null,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(cells[i].$1.toUpperCase(), style: AfeType.label(a.muted)),
                      const SizedBox(height: 2),
                      Text(cells[i].$2, style: const TextStyle(fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// The money trail in four bars: paid, held, moved in, released.
class PayFlowBar extends StatelessWidget {
  const PayFlowBar({super.key, required this.reached, this.labels = const ['Paid', 'Held', 'Moved in', 'Released']});
  final int reached;
  final List<String> labels;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Semantics(
      label: 'Payment progress: $reached of ${labels.length} steps',
      child: Row(
        children: [
          for (var i = 0; i < labels.length; i++) ...[
            if (i > 0) const SizedBox(width: 4),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    height: 5,
                    decoration: BoxDecoration(color: i < reached ? a.brand : a.line, borderRadius: BorderRadius.circular(3)),
                  ),
                  const SizedBox(height: 5),
                  Text(labels[i], style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Yes / No for one check (verifier visit). [value] null = not answered yet.
class YesNo extends StatelessWidget {
  const YesNo({
    super.key,
    required this.value,
    required this.onChanged,
    this.yesLabel = 'Yes',
    this.noLabel = 'No',
    this.yesEnabled = true,
  });
  final bool? value;
  final ValueChanged<bool> onChanged;
  final String yesLabel;
  final String noLabel;
  final bool yesEnabled;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    Widget pick(bool v, String label, Color c, Color bg, bool enabled) {
      final on = value == v;
      return Expanded(
        child: Semantics(
          button: true,
          selected: on,
          child: Pressable(
            child: Material(
              color: on ? bg : a.surface,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(a.pickRadius),
                side: BorderSide(color: on ? c : a.line, width: on ? 2 : 1),
              ),
              child: InkWell(
                onTap: enabled ? () => onChanged(v) : null,
                customBorder: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.pickRadius)),
                child: Container(
                  height: 44,
                  alignment: Alignment.center,
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w600,
                      color: !enabled
                          ? a.muted
                          : on
                          ? c
                          : a.ink,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Row(
      children: [
        pick(true, yesLabel, a.ok, a.okSoft, yesEnabled),
        const SizedBox(width: 8),
        pick(false, noLabel, a.crit, a.critSoft, true),
      ],
    );
  }
}

/// A numbered step you can open (landlord verification): dot, title, note, chevron.
class StepTile extends StatelessWidget {
  const StepTile({super.key, required this.number, required this.title, this.subtitle, this.done = false, this.current = false, this.onTap});
  final int number;
  final String title;
  final String? subtitle;
  final bool done;

  /// The step the person is on: a brand dot on a paper background, as on the canvas's stepper.
  final bool current;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final now = current && !done;
    return InkWell(
      onTap: onTap,
      child: Container(
        color: now ? a.bg : null,
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Container(
              width: 28,
              height: 28,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: done ? a.ok : (now ? a.brand : a.tint), shape: BoxShape.circle),
              child: Text(
                done ? '✓' : '$number',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: done ? a.bg : (now ? a.onBrand : a.muted)),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                  if (subtitle != null) Text(subtitle!, style: TextStyle(fontSize: 12.5, color: a.muted)),
                ],
              ),
            ),
            if (onTap != null) Text('›', style: TextStyle(color: a.muted, fontSize: 20)),
          ],
        ),
      ),
    );
  }
}

/// A field's label above it (14 px, semibold), as the canvases draw every form.
class FieldLabel extends StatelessWidget {
  const FieldLabel(this.text, {super.key, this.optional = false});
  final String text;
  final bool optional;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text.rich(
      TextSpan(
        children: [
          TextSpan(text: text),
          if (optional)
            TextSpan(
              text: ' (optional)',
              style: TextStyle(fontWeight: FontWeight.w400, color: context.afe.muted),
            ),
        ],
      ),
      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
    ),
  );
}

/// The canvas's upload tile: a dashed, striped box ("Upload document", "PDF or photo, all
/// pages") that turns solid green with a tick once something is added.
class UploadTile extends StatelessWidget {
  const UploadTile({super.key, required this.title, required this.note, required this.done, required this.onTap, this.height = 132});
  final String title;
  final String note;
  final bool done;
  final VoidCallback onTap;
  final double height;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final radius = BorderRadius.circular(12);
    final content = Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(title, textAlign: TextAlign.center, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: done ? a.ok : a.ink)),
        const SizedBox(height: 6),
        Text(note, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis, style: AfeType.mono(11, color: a.muted)),
      ],
    );
    return Semantics(
      button: true,
      label: '$title. $note',
      child: Pressable(
        scale: 0.98,
        child: GestureDetector(
          onTap: onTap,
          child: SizedBox(
            height: height,
            child: done
                ? Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: a.okSoft, borderRadius: radius, border: Border.all(color: a.ok, width: 2)),
                    child: content,
                  )
                : ClipRRect(
                    borderRadius: radius,
                    child: CustomPaint(
                      foregroundPainter: _DashedBorder(a.line),
                      child: Stripes(step: 7, child: Padding(padding: const EdgeInsets.all(16), child: content)),
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}

class _DashedBorder extends CustomPainter {
  _DashedBorder(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    final path = Path()..addRRect(RRect.fromRectAndRadius((Offset.zero & size).deflate(1), const Radius.circular(11)));
    for (final metric in path.computeMetrics()) {
      for (double d = 0; d < metric.length; d += 10) {
        canvas.drawPath(metric.extractPath(d, d + 6), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashedBorder old) => old.color != color;
}

/// A number with − and + (bedrooms, bathrooms).
class CountStepper extends StatelessWidget {
  const CountStepper({super.key, required this.label, required this.value, required this.onChanged, this.min = 0, this.max = 10});
  final String label;
  final int value;
  final int min, max;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    Widget button(String text, String tip, VoidCallback? onTap) => Semantics(
      button: true,
      label: '$tip $label',
      child: Pressable(
        child: Material(
          color: a.surface,
          shape: CircleBorder(side: BorderSide(color: onTap == null ? a.line : a.brand)),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox.square(
              dimension: 40,
              child: Center(
                child: Text(text, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: onTap == null ? a.muted : a.brand)),
              ),
            ),
          ),
        ),
      ),
    );
    return Row(
      children: [
        Expanded(child: Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500))),
        button('−', 'Fewer', value > min ? () => onChanged(value - 1) : null),
        SizedBox(
          width: 44,
          child: Text('$value', textAlign: TextAlign.center, style: AfeType.heading(20, color: a.ink)),
        ),
        button('+', 'More', value < max ? () => onChanged(value + 1) : null),
      ],
    );
  }
}

/// A big green tick in a circle: something is done.
class DoneMark extends StatelessWidget {
  const DoneMark({super.key});

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      width: 48,
      height: 48,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: a.okSoft, shape: BoxShape.circle),
      child: Text(
        '✓',
        style: TextStyle(color: a.ok, fontSize: 22, fontWeight: FontWeight.w700),
      ),
    );
  }
}

/// Phone number with the fixed +233 prefix, as on the sign-in canvases.
class PhoneField extends StatelessWidget {
  const PhoneField({super.key, required this.controller, this.enabled = true, this.onSubmitted});
  final TextEditingController controller;
  final bool enabled;
  final ValueChanged<String>? onSubmitted;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      height: 52,
      decoration: BoxDecoration(
        color: a.surface,
        borderRadius: BorderRadius.circular(a.inputRadius),
        border: Border.all(color: a.line),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              border: Border(right: BorderSide(color: a.line)),
            ),
            child: Text('+233', style: AfeType.mono(15, color: a.muted)),
          ),
          Expanded(
            child: TextField(
              controller: controller,
              enabled: enabled,
              keyboardType: TextInputType.phone,
              autofillHints: const [AutofillHints.telephoneNumberNational],
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9 ]')), LengthLimitingTextInputFormatter(13)],
              onSubmitted: onSubmitted,
              style: TextStyle(fontSize: 17, color: a.ink),
              decoration: const InputDecoration(
                hintText: '24 123 4567',
                filled: false,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                contentPadding: EdgeInsets.symmetric(horizontal: 12),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// "24 412 3456", "024 412 3456" or "+233 24 412 3456" -> "+233244123456" for the API.
String phoneE164(String text) {
  var d = text.replaceAll(RegExp(r'\D'), '');
  if (d.startsWith('233') && d.length == 12) d = d.substring(3);
  if (d.startsWith('0') && d.length == 10) d = d.substring(1);
  return d.length == 9 ? '+233$d' : text.trim();
}

/// Six boxes over one hidden field for a one-time code; the next box is outlined in brand.
class CodeBoxes extends StatefulWidget {
  const CodeBoxes({super.key, required this.controller, this.error = false, this.onCompleted});
  final TextEditingController controller;
  final bool error;
  final VoidCallback? onCompleted;

  @override
  State<CodeBoxes> createState() => _CodeBoxesState();
}

class _CodeBoxesState extends State<CodeBoxes> {
  final _focus = FocusNode();

  @override
  void dispose() {
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final code = widget.controller.text;
    return GestureDetector(
      onTap: () => _focus.requestFocus(),
      child: Stack(
        children: [
          Row(
            children: [
              for (var i = 0; i < 6; i++) ...[
                if (i > 0) const SizedBox(width: 6),
                Expanded(
                  child: Container(
                    height: 52,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: a.surface,
                      borderRadius: BorderRadius.circular(a.ios ? 10 : 4),
                      border: Border.all(
                        color: i == code.length
                            ? a.brand
                            : widget.error
                            ? a.crit
                            : a.line,
                        width: i == code.length ? 2 : 1,
                      ),
                    ),
                    child: Text(i < code.length ? code[i] : '', style: AfeType.mono(22, color: a.ink)),
                  ),
                ),
              ],
            ],
          ),
          Positioned.fill(
            child: Opacity(
              opacity: 0,
              child: TextField(
                controller: widget.controller,
                focusNode: _focus,
                autofocus: true,
                keyboardType: TextInputType.number,
                autofillHints: const [AutofillHints.oneTimeCode],
                inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
                showCursor: false,
                onChanged: (v) {
                  setState(() {});
                  if (v.length == 6) widget.onCompleted?.call();
                },
                decoration: const InputDecoration(border: InputBorder.none, filled: false),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A small heading between blocks of a screen ("Listings", "Latest enquiry").
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Text(text, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15));
}

void toast(BuildContext context, String text) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}

/// Runs an action, showing the API's message if it fails. Returns true when it worked.
Future<bool> attempt(BuildContext context, Future<void> Function() action, {String? done}) async {
  try {
    await action();
    if (done != null && context.mounted) toast(context, done);
    return true;
  } on ApiException catch (e) {
    if (context.mounted) toast(context, e.message);
    return false;
  }
}

/// Opens a private document (a receipt, an invoice, an agreement, the move-in photo) in the phone's
/// viewer. The viewer can't carry the app's sign-in, so the API hands out a five-minute link to just
/// this one file, and checks the person's access again when it's opened.
Future<void> openDocument(BuildContext context, String kind, String key) async {
  final api = context.api;
  await attempt(context, () async {
    final link = (await api.post<Json>('/documents/links', {'kind': kind, 'key': key})).data;
    final opened = await launchUrl(Uri.parse('${api.baseUrl}${link['path']}'), mode: LaunchMode.inAppBrowserView);
    if (!opened && context.mounted) toast(context, "Couldn't open the file. Try again.");
  });
}

/// A row that opens a document: an icon, what it is, a muted line, and the file type.
class DocumentRow extends StatelessWidget {
  const DocumentRow({super.key, required this.label, required this.kind, required this.docKey, this.sub = '', this.photo = false});
  final String label;
  final String kind;
  final String docKey;
  final String sub;
  final bool photo;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Semantics(
      button: true,
      label: '$label, ${photo ? 'photo' : 'PDF'}',
      excludeSemantics: true,
      child: InkWell(
        onTap: () => openDocument(context, kind, docKey),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            children: [
              Icon(photo ? Icons.image_outlined : Icons.picture_as_pdf_outlined, size: 22, color: a.accent),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
                    if (sub.isNotEmpty) Text(sub, style: AfeType.mono(11.5, color: a.muted)),
                  ],
                ),
              ),
              Text(photo ? 'PHOTO' : 'PDF', style: AfeType.label(a.muted, size: 10.5)),
              const SizedBox(width: 4),
              Icon(Icons.chevron_right, size: 20, color: a.muted),
            ],
          ),
        ),
      ),
    );
  }
}
