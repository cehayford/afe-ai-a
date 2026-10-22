import 'dart:convert';

import 'package:afe/api/client.dart';
import 'package:afe/api/token_store.dart';
import 'package:afe/main.dart';
import 'package:afe/session.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response ok(Object data) => http.Response.bytes(utf8.encode(jsonEncode({'data': data})), 200,
    headers: {'content-type': 'application/json; charset=utf-8'});

const _listing = {
  'id': 1,
  'reference': 'AFE-7Q2K',
  'title': 'Bright 2-bedroom flat',
  'rent_pesewas': 350000,
  'rent_display': 'GH₵ 3,500',
  'advance_months': 6,
  'advance_total_display': 'GH₵ 21,000',
  'min_lease_months': 12,
  'available_from': '2026-10-01',
  'status': 'live',
  'status_reason': '',
  'published_at': '2026-09-20T10:00:00Z',
  'bedrooms': 2,
  'area': 'Osu',
  'cover_url': null,
};

const _landlord = {
  'id': 7,
  'username': 'ama',
  'display_name': 'Ama',
  'name': 'Ama Mensah',
  'role': 'landlord',
  'role_label': 'Landlord',
  'phone': '+233244123456',
  'email': null,
  'whatsapp_opt_in': true,
};

/// A phone with no session. [onboarded] is false on a fresh install, so "Get started" shows.
Future<Session> guestSession(List<String> calls, {List<Object?>? bodies, bool onboarded = true, MemoryTokenStore? tokens}) async {
  final store = tokens ?? MemoryTokenStore();
  if (onboarded) store.values[Session.onboardedKey] = '1';
  final api = ApiClient(
    tokens: store,
    baseUrl: 'https://api.afe.test',
    httpClient: MockClient((req) async {
      calls.add(req.url.path);
      if (req.url.path.endsWith('/properties/areas')) return ok([{'id': 1, 'slug': 'osu', 'name': 'Osu'}]);
      if (req.url.path.endsWith('/properties/search')) return ok([_listing]);
      if (req.url.path.endsWith('/auth/code') || req.url.path.endsWith('/auth/signup')) {
        bodies?.add(jsonDecode(req.body));
        if (req.url.path.endsWith('/auth/signup')) return ok({'status': 'ok', 'access_token': 'a-1', 'refresh_token': 'r-1'});
        return ok({'sent': true});
      }
      if (req.url.path.endsWith('/me') && req.method == 'GET') return ok({'user': _landlord, 'unread_notifications': 0});
      if (req.url.path.endsWith('/me') && req.method == 'PATCH') {
        bodies?.add(jsonDecode(req.body));
        return ok(_landlord);
      }
      return http.Response('{}', 404);
    }),
  );
  final session = Session(api);
  await session.start();
  return session;
}

void main() {
  testWidgets('a visitor starts on the start screen and can browse verified homes', (tester) async {
    final calls = <String>[];
    final session = await guestSession(calls);
    await tester.pumpWidget(AfeApp(session: session));
    await tester.pumpAndSettle();

    // The start screen from the design: a greeting and numbered places for a visitor.
    expect(find.text('Welcome to Afe'), findsOneWidget);
    for (final place in ['Find a home', 'Scam check', 'Sign in', 'Create account']) {
      expect(find.text(place), findsOneWidget);
    }
    expect(find.text('Pay safely'), findsNothing, reason: 'payments need an account');

    await tester.tap(find.text('Find a home'));
    await tester.pumpAndSettle();
    expect(find.text('Bright 2-bedroom flat'), findsOneWidget);
    expect(find.text('✓ Landlord + home verified'), findsOneWidget);
    expect(find.text('1 verified home in Accra'), findsOneWidget);
    expect(calls, isNot(contains('/api/v1/me')), reason: 'no session, so no /me call');
  });

  testWidgets('first run: Get started, choose a role, sign up, then the ready screen for that role', (tester) async {
    final bodies = <Object?>[];
    final tokens = MemoryTokenStore();
    final session = await guestSession([], bodies: bodies, onboarded: false, tokens: tokens);
    await tester.pumpWidget(AfeApp(session: session));
    await tester.pumpAndSettle();

    // Three slides, each an example record and the promise under it.
    expect(find.text('Every landlord is checked'), findsOneWidget);
    expect(find.text('I already have an account'), findsOneWidget);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('Every home is visited'), findsOneWidget);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('Your rent waits with us'), findsOneWidget);
    await tester.tap(find.text('Get started'));
    await tester.pumpAndSettle();

    // Continue waits for a choice.
    expect(find.text('How will you use Afe?'), findsOneWidget);
    final next = find.widgetWithText(FilledButton, 'Continue');
    expect(tester.widget<FilledButton>(next).onPressed, isNull);
    await tester.tap(find.text("I'm renting out a home"));
    await tester.pumpAndSettle();
    await tester.tap(next);
    await tester.pumpAndSettle();

    // Sign-up starts with the role already picked.
    expect(find.text('Create your account'), findsOneWidget);
    expect(find.textContaining('Landlords and agents are verified'), findsOneWidget);
    await tester.enterText(find.byType(TextField).at(0), 'Ama Mensah');
    await tester.enterText(find.byType(TextField).at(1), '024 412 3456');
    await tester.tap(find.widgetWithText(FilledButton, 'Send code by WhatsApp'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '123456');
    await tester.pumpAndSettle();
    expect((bodies.last as Map)['role'], 'landlord');

    // Ready: the landlord's first steps, WhatsApp reminders, and the way into verification.
    expect(find.text('Welcome, Ama'), findsOneWidget);
    expect(find.text('Next, get verified so your homes can go live.'), findsOneWidget);
    expect(find.text('Ghana Card and live selfie (3 min)'), findsOneWidget);
    expect(find.text('Start verification'), findsOneWidget);
    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    expect(bodies.last, {'whatsapp_opt_in': false});
    expect(tokens.values[Session.onboardedKey], isNull, reason: 'the welcome is done only after the ready screen');
    await tester.tap(find.text('Start verification'));
    await tester.pumpAndSettle();
    expect(tokens.values[Session.onboardedKey], '1');
    expect(session.welcomeRole, isNull);
  });

  testWidgets('"Just looking" skips the welcome and remembers it on this phone', (tester) async {
    final tokens = MemoryTokenStore();
    final session = await guestSession([], onboarded: false, tokens: tokens);
    await tester.pumpWidget(AfeApp(session: session));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Just looking? Browse homes first'));
    await tester.pumpAndSettle();
    expect(find.text('Welcome to Afe'), findsOneWidget);
    expect(tokens.values[Session.onboardedKey], '1');
  });

  testWidgets('signing in sends the code by WhatsApp or SMS to a +233 number', (tester) async {
    final bodies = <Object?>[];
    final session = await guestSession([], bodies: bodies);
    await tester.pumpWidget(AfeApp(session: session));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Sign in'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Phone number'), findsOneWidget);
    expect(find.text('+233'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Send code by WhatsApp'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Send by SMS'), findsOneWidget);

    // A short number is caught before anything is sent.
    await tester.enterText(find.byType(TextField), '24 12');
    await tester.tap(find.widgetWithText(FilledButton, 'Send code by WhatsApp'));
    await tester.pumpAndSettle();
    expect(find.textContaining('9-digit Ghana number'), findsOneWidget);
    expect(bodies, isEmpty);

    // A number typed with its leading 0 is fine; the code goes by WhatsApp.
    await tester.enterText(find.byType(TextField), '024 412 3456');
    await tester.tap(find.widgetWithText(FilledButton, 'Send code by WhatsApp'));
    await tester.pumpAndSettle();
    expect(bodies.single, {'phone': '+233244123456', 'purpose': 'login', 'channel': 'whatsapp'});
    expect(find.text('Enter your code'), findsOneWidget);
    expect(find.textContaining('Sent by WhatsApp to +233 24 412 3456'), findsOneWidget);
    await tester.pump(const Duration(seconds: 31));
  });
}
