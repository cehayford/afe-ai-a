import 'package:flutter/material.dart';

import '../session.dart';
import '../theme.dart';
import '../widgets/brand.dart';
import '../widgets/common.dart';
import 'auth.dart';
import 'field.dart';
import 'homes.dart';
import 'start.dart';

// "Get started", the new-user flow from the Afe workspace's Mobile App canvas (App Screen, role
// "new"): three welcome slides on Afe green, "How will you use Afe?", sign-up, then a ready screen
// with the first steps for that role.

typedef _Slide = ({String tag, String title, String body, String cardTitle, String cardTag, List<(String, String, bool)> rows});

const List<_Slide> _slides = [
  (
    tag: 'Checked by people',
    title: 'Every landlord is checked',
    body: 'We match their Ghana Card to a live selfie and see the ownership papers before a listing goes live.',
    cardTitle: 'Kwame Asante · Landlord',
    cardTag: 'AFE-0142',
    rows: [('Ghana Card checked', '14 Sep', true), ('Live selfie matched', '14 Sep', true), ('Indenture sighted', '14 Sep', true)],
  ),
  (
    tag: 'Visited in person',
    title: 'Every home is visited',
    body: 'An Afe verifier goes to the address, confirms it matches the listing and takes the photos you see.',
    cardTitle: '2-bedroom apartment · East Legon',
    cardTag: 'AFE-0142',
    rows: [('Visited by Afe', '18 Sep', true), ('Address matches GA-492-7713', '18 Sep', true), ('8 photos taken by Afe', '18 Sep', true)],
  ),
  (
    tag: 'Protected rent',
    title: 'Your rent waits with us',
    body: "Pay through Afe. The landlord is paid only after you confirm you've moved in.",
    cardTitle: 'GH₵ 10,500 · 3 months',
    cardTag: 'Protected',
    rows: [('Paid by MoMo', '24 Sep', true), ('Held by Afe', 'now', true), ('Released after you move in', '', false)],
  ),
];

/// The welcome: an example record per slide, the promise under it, dots, Next / Get started, and
/// "I already have an account".
class GetStartedScreen extends StatefulWidget {
  const GetStartedScreen({super.key});

  @override
  State<GetStartedScreen> createState() => _GetStartedScreenState();
}

class _GetStartedScreenState extends State<GetStartedScreen> {
  final _pages = PageController();
  int _at = 0;

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  void _chooseRole() => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ChooseRoleScreen()));

  void _next() {
    if (_at < _slides.length - 1) {
      _pages.animateToPage(_at + 1, duration: Motion.reduced(context) ? Duration.zero : const Duration(milliseconds: 260), curve: Motion.easeOut);
    } else {
      _chooseRole();
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final hero = a.dark ? const Color(0xFF0B3A31) : AfeColors.brand;
    return Scaffold(
      backgroundColor: hero,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const AfeMark(size: 36, onDark: true),
                  const SizedBox(width: 10),
                  Text('afe', style: AfeType.heading(24, color: Colors.white)),
                  const Spacer(),
                  TextButton(
                    onPressed: _chooseRole,
                    style: TextButton.styleFrom(
                      foregroundColor: Colors.white,
                      backgroundColor: Colors.white.withValues(alpha: 0.1),
                      shape: const StadiumBorder(),
                      minimumSize: const Size(0, 40),
                    ),
                    child: const Text('Skip', style: TextStyle(fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
              Expanded(
                child: PageView.builder(
                  controller: _pages,
                  itemCount: _slides.length,
                  onPageChanged: (i) => setState(() => _at = i),
                  itemBuilder: (context, i) => _SlideView(slide: _slides[i]),
                ),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  for (var i = 0; i < _slides.length; i++)
                    Semantics(
                      button: true,
                      label: 'Slide ${i + 1}',
                      selected: i == _at,
                      child: GestureDetector(
                        onTap: () => _pages.animateToPage(i, duration: const Duration(milliseconds: 260), curve: Motion.easeOut),
                        child: AnimatedContainer(
                          duration: Motion.reduced(context) ? Duration.zero : const Duration(milliseconds: 250),
                          curve: Motion.easeOut,
                          margin: const EdgeInsets.symmetric(horizontal: 3, vertical: 12),
                          width: i == _at ? 24 : 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: i == _at ? AfeColors.darkAmber : Colors.white.withValues(alpha: 0.35),
                            borderRadius: BorderRadius.circular(99),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 4),
              Pressable(
                child: SizedBox(
                  height: a.buttonHeight,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: AfeColors.amber,
                      foregroundColor: AfeColors.ink,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(a.buttonRadius)),
                    ),
                    onPressed: _next,
                    child: Text(_at < _slides.length - 1 ? 'Next' : 'Get started', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                  ),
                ),
              ),
              const SizedBox(height: 4),
              TextButton(
                style: TextButton.styleFrom(foregroundColor: Colors.white, minimumSize: const Size(0, 44)),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SignInScreen())),
                child: const Text('I already have an account', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SlideView extends StatelessWidget {
  const _SlideView({required this.slide});
  final _Slide slide;

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            boxShadow: const [BoxShadow(color: Color(0x40000000), blurRadius: 40, offset: Offset(0, 18))],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: ColoredBox(
              color: a.surface,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    decoration: BoxDecoration(
                      border: Border(bottom: BorderSide(color: a.line)),
                    ),
                    child: Row(
                      children: [
                        Expanded(child: Text(slide.cardTitle.toUpperCase(), style: AfeType.label(a.muted, size: 11))),
                        Text(slide.cardTag, style: AfeType.mono(11, color: a.muted)),
                      ],
                    ),
                  ),
                  for (final (t, d, done) in slide.rows)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
                      decoration: BoxDecoration(
                        border: Border(bottom: BorderSide(color: a.tint)),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 22,
                            height: 22,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(color: done ? a.okSoft : a.tint, shape: BoxShape.circle),
                            child: done
                                ? Icon(Icons.check, size: 14, color: a.ok)
                                : Text(
                                    '·',
                                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: a.muted),
                                  ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(t, style: TextStyle(fontSize: 14, color: a.ink)),
                          ),
                          Text(d, style: AfeType.mono(11, color: a.muted)),
                        ],
                      ),
                    ),
                  // The amber edge along the bottom, as on the design's card.
                  Container(height: 4, color: a.amber),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 22),
        Text(slide.tag.toUpperCase(), style: AfeType.label(AfeColors.darkAmber, size: 11)),
        const SizedBox(height: 10),
        Text(slide.title, style: AfeType.heading(32, color: Colors.white, height: 1.05)),
        const SizedBox(height: 10),
        Text(slide.body, style: const TextStyle(fontSize: 15.5, height: 1.5, color: Color(0xFFEAF4F0))),
      ],
    );
  }
}

/// "How will you use Afe?": renter or landlord cards, the verifier's invite link, Continue.
class ChooseRoleScreen extends StatefulWidget {
  const ChooseRoleScreen({super.key});

  @override
  State<ChooseRoleScreen> createState() => _ChooseRoleScreenState();
}

class _ChooseRoleScreenState extends State<ChooseRoleScreen> {
  String? _pick;

  void _continue() {
    final pick = _pick;
    if (pick == null) return;
    context.session.chooseWelcomeRole(pick);
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => pick == 'verifier' ? const SignInScreen() : SignUpScreen(initialRole: pick)));
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    Widget card(String key, String title, String sub) {
      final on = _pick == key;
      final shape = RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(a.cardRadius),
        side: BorderSide(color: on ? a.brand : a.line, width: on ? 2 : 1),
      );
      return Semantics(
        button: true,
        selected: on,
        child: Pressable(
          scale: 0.98,
          child: Material(
            color: on ? a.tint : a.surface,
            shape: shape,
            child: InkWell(
              customBorder: shape,
              onTap: () => setState(() => _pick = key),
              child: Padding(
                padding: EdgeInsets.all(on ? 15 : 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(title, style: AfeType.heading(19, color: a.ink)),
                        ),
                        AnimatedContainer(
                          duration: Motion.press,
                          width: 22,
                          height: 22,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(color: on ? a.brand : a.line, width: on ? 7 : 2),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(sub, style: TextStyle(fontSize: 14, color: a.muted, height: 1.45)),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  style: TextButton.styleFrom(foregroundColor: a.brand, padding: const EdgeInsets.symmetric(horizontal: 10)),
                  onPressed: () => Navigator.of(context).maybePop(),
                  child: const Text('‹ Back', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                ),
              ),
              const SizedBox(height: 8),
              Text('How will you use Afe?', style: AfeType.heading(28, color: a.ink)),
              const SizedBox(height: 6),
              Text("You'll only see the tools for your choice.", style: TextStyle(fontSize: 15, color: a.muted)),
              const SizedBox(height: 18),
              card('renter', "I'm looking for a home", 'Browse verified homes, book viewings and pay safely.'),
              const SizedBox(height: 10),
              card('landlord', "I'm renting out a home", 'Landlord or agent. Verification is free during the launch offer.'),
              const SizedBox(height: 6),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  style: TextButton.styleFrom(foregroundColor: a.brand, padding: EdgeInsets.zero, minimumSize: const Size(0, 40)),
                  onPressed: () => setState(() => _pick = 'verifier'),
                  child: Text(
                    _pick == 'verifier' ? '✓ Afe verifier (sign in with your invite next)' : 'Afe verifier? Use your invite',
                    style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
              const Spacer(),
              PrimaryButton(label: 'Continue', onPressed: _pick == null ? null : _continue),
              const SizedBox(height: 6),
              TextButton(
                style: TextButton.styleFrom(foregroundColor: a.muted, minimumSize: const Size(0, 44)),
                onPressed: () {
                  Navigator.of(context).popUntil((r) => r.isFirst);
                  context.session.finishOnboarding();
                },
                child: const Text('Just looking? Browse homes first', style: TextStyle(fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// After sign-up: a tick, the first three steps for the role, WhatsApp reminders, and the way in.
class ReadyScreen extends StatefulWidget {
  const ReadyScreen({super.key});

  @override
  State<ReadyScreen> createState() => _ReadyScreenState();
}

class _ReadyScreenState extends State<ReadyScreen> {
  late bool _remind = context.session.me?.user.whatsappOptIn ?? true;

  Future<void> _toggle(bool v) async {
    setState(() => _remind = v);
    await attempt(context, () => context.api.patch('/me', {'whatsapp_opt_in': v}));
  }

  @override
  Widget build(BuildContext context) {
    final a = context.afe;
    final me = SessionScope.of(context).me;
    final first = (me?.user.name ?? '').split(' ').first;
    final role = (me?.user.isVerifier ?? false)
        ? 'verifier'
        : (me?.user.isLister ?? false)
        ? 'landlord'
        : 'renter';
    final (title, sub, steps, cta) = switch (role) {
      'landlord' => (
        'Welcome, $first',
        'Next, get verified so your homes can go live.',
        ['Ghana Card and live selfie (3 min)', 'Add ownership papers', 'Book the home visit'],
        'Start verification',
      ),
      'verifier' => (
        'Welcome, $first',
        'Your verifier account is linked to your invite.',
        ["See today's route", 'Check in at each address', 'Send reports for review'],
        "See today's visits",
      ),
      _ => (
        "You're all set, $first",
        'Your renter account is ready.',
        ['Browse verified homes in Accra', 'Check any number before you pay', 'Book a viewing in the app'],
        'Find a home',
      ),
    };
    Widget destination() => switch (role) {
      'landlord' => const LandlordVerifyScreen(),
      'verifier' => const WorklistScreen(),
      _ => const SearchScreen(),
    };
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 32, 20, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: Container(
                  width: 56,
                  height: 56,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: a.okSoft, shape: BoxShape.circle),
                  child: Icon(Icons.check, size: 30, color: a.ok),
                ),
              ),
              const SizedBox(height: 18),
              Text(title, style: AfeType.heading(30, color: a.ink)),
              const SizedBox(height: 6),
              Text(sub, style: TextStyle(fontSize: 15, color: a.muted)),
              const SizedBox(height: 18),
              Panel(
                children: [
                  for (var i = 0; i < steps.length; i++)
                    Padding(
                      padding: const EdgeInsets.all(14),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 26,
                            child: Text((i + 1).toString().padLeft(2, '0'), style: AfeType.mono(12, color: a.amber)),
                          ),
                          Expanded(child: Text(steps[i], style: const TextStyle(fontSize: 15))),
                        ],
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 14),
              Material(
                color: a.surface,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(a.cardRadius),
                  side: BorderSide(color: a.line),
                ),
                child: SwitchListTile.adaptive(
                  value: _remind,
                  onChanged: _toggle,
                  activeTrackColor: a.ios ? a.ok : a.brand,
                  title: const Text('WhatsApp reminders', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                  subtitle: Text('Viewings, payments and visits', style: TextStyle(fontSize: 13, color: a.muted)),
                ),
              ),
              const Spacer(),
              PrimaryButton(
                label: cta,
                onPressed: () async {
                  // The start screen takes the ready screen's place underneath, so Back from the
                  // first task lands there.
                  final nav = Navigator.of(context);
                  await context.session.finishOnboarding();
                  nav.push(MaterialPageRoute(builder: (_) => destination()));
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}
