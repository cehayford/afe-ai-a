import 'package:flutter/material.dart';

import 'api/client.dart';
import 'api/token_store.dart';
import 'screens/auth.dart';
import 'screens/get_started.dart';
import 'screens/start.dart';
import 'session.dart';
import 'theme.dart';
import 'widgets/brand.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final session = Session(ApiClient(tokens: SecureTokenStore()))..start();
  runApp(AfeApp(session: session));
}

class AfeApp extends StatelessWidget {
  const AfeApp({super.key, required this.session});
  final Session session;

  @override
  Widget build(BuildContext context) => SessionScope(
    session: session,
    child: MaterialApp(
      title: 'Afe',
      debugShowCheckedModeBanner: false,
      theme: afeTheme(Brightness.light),
      darkTheme: afeTheme(Brightness.dark),
      home: const RootGate(),
    ),
  );
}

/// The app each person sees starts on the start screen from the design: a greeting and a grid of
/// places for their role (renters and visitors, landlords and agents, field verifiers), with the
/// same places in the drawer. Reviewers work on the website. On a phone's first run it opens on
/// "Get started" instead, and after signing up from there, on the "ready" screen for the role.
class RootGate extends StatelessWidget {
  const RootGate({super.key});

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    if (session.starting) return const _Splash();
    final user = session.me?.user;
    if (user != null && user.isReviewer) return const _UseTheWebsite();
    if (user == null && !session.onboarded) return const GetStartedScreen();
    if (user != null && session.welcomeRole != null) return ReadyScreen(key: ValueKey('ready-${user.id}'));
    return StartScreen(key: ValueKey('start-${user?.id}-${user?.role}'));
  }
}

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) => const Scaffold(
    backgroundColor: AfeColors.brand,
    body: Center(child: AfeMark(size: 96, onDark: true)),
  );
}

class _UseTheWebsite extends StatelessWidget {
  const _UseTheWebsite();

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Align(
              alignment: Alignment.centerLeft,
              child: AfeLogo(mark: 40, text: 26, tag: 'Review desk'),
            ),
            const SizedBox(height: 24),
            Text('Reviews happen on the website', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 8),
            const Text('The review queue, money and rules need a bigger screen. Open Afe on a computer.'),
            const SizedBox(height: 20),
            FilledButton(onPressed: () => openWeb('/review'), child: const Text('Open the website')),
            const SizedBox(height: 10),
            OutlinedButton(onPressed: () => SessionScope.read(context).signOut(), child: const Text('Sign out')),
          ],
        ),
      ),
    ),
  );
}
