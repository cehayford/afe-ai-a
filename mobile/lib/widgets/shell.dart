import 'package:flutter/foundation.dart' show defaultTargetPlatform;
import 'package:flutter/material.dart';

import '../session.dart';
import '../theme.dart';
import 'common.dart';

/// The top bar from the App Screen canvas. iOS: centred title, "‹ Back" in brand, a 32 px
/// initials avatar. Android (Material 3): leading ← or ☰, title on the left, a 36 px avatar.
/// The avatar goes back to the start screen; ☰ opens the drawer on the start screen.
class AfeAppBar extends StatelessWidget implements PreferredSizeWidget {
  const AfeAppBar({super.key, this.title, this.actions = const [], this.avatar = true});
  final Widget? title;
  final List<Widget> actions;
  final bool avatar;

  static bool get _ios => defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.macOS;

  @override
  Size get preferredSize => Size.fromHeight(_ios ? 44 : 64);

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final canPop = ModalRoute.of(context)?.canPop ?? false;
    final hasDrawer = Scaffold.maybeOf(context)?.hasDrawer ?? false;
    final me = SessionScope.of(context).me;
    Widget? leading;
    if (canPop) {
      leading = a.ios
          ? TextButton(
              onPressed: () => Navigator.of(context).maybePop(),
              style: TextButton.styleFrom(
                foregroundColor: a.brand,
                padding: const EdgeInsets.only(left: 8),
                alignment: Alignment.centerLeft,
                textStyle: const TextStyle(fontFamily: 'CupertinoSystemText', fontSize: 17),
              ),
              child: const Text('‹ Back', maxLines: 1),
            )
          : IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => Navigator.of(context).maybePop());
    } else if (hasDrawer) {
      leading = IconButton(
        tooltip: 'Menu',
        icon: Icon(Icons.menu, color: a.ios ? a.brand : a.ink),
        onPressed: () => Scaffold.of(context).openDrawer(),
      );
    }
    return AppBar(
      automaticallyImplyLeading: false,
      leading: leading,
      leadingWidth: a.ios && canPop ? 84 : null,
      title: title,
      actions: [
        ...actions,
        if (avatar && me != null)
          Padding(
            padding: EdgeInsets.only(right: a.ios ? 12 : 8, left: 4),
            child: Initials(
              name: me.user.name,
              size: a.ios ? 32 : 36,
              onTap: canPop ? () => Navigator.of(context).popUntil((r) => r.isFirst) : null,
            ),
          ),
      ],
    );
  }
}

/// Initials in a brand circle (the signed-in person). [soft] is the tint circle used for other
/// people (conversations, enquiries).
class Initials extends StatelessWidget {
  const Initials({super.key, required this.name, this.size = 36, this.onTap, this.soft = false});
  final String name;
  final double size;
  final VoidCallback? onTap;
  final bool soft;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final letters = name.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).take(2).map((w) => w[0].toUpperCase()).join();
    return Semantics(
      button: onTap != null,
      label: onTap != null ? 'Home' : name,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: soft ? a.tint : a.brand, shape: BoxShape.circle),
          child: Text(
            letters.isEmpty ? 'A' : letters,
            style: AfeType.heading(size <= 32 ? 12 : size >= 48 ? 17 : (soft ? 14 : 13), color: soft ? a.accent : a.onBrand),
          ),
        ),
      ),
    );
  }
}

/// The bar pinned under a screen's content: an optional price on the left, one main action.
class BottomActionBar extends StatelessWidget {
  const BottomActionBar({super.key, required this.label, required this.onPressed, this.price, this.priceNote, this.busy = false});
  final String label;
  final VoidCallback? onPressed;
  final String? price;
  final String? priceNote;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Container(
      decoration: BoxDecoration(
        color: a.bar,
        border: Border(top: BorderSide(color: a.line)),
      ),
      padding: EdgeInsets.fromLTRB(16, 12, 16, 12 + MediaQuery.paddingOf(context).bottom),
      child: Row(
        children: [
          if (price != null) ...[
            Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(price!, style: AfeType.heading(20, color: a.accent)),
                if (priceNote != null) Text(priceNote!, style: TextStyle(fontSize: 11.5, color: a.muted)),
              ],
            ),
            const SizedBox(width: 12),
          ],
          Expanded(
            child: PrimaryButton(label: label, onPressed: onPressed, busy: busy),
          ),
        ],
      ),
    );
  }
}
