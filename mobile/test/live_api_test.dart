// Contract test against a running Afe API with demo data: the app's own client and models,
// signing in as each kind of user. Skipped unless AFE_LIVE_API is set.
//
//   cd backend && AFE_DEBUG=1 python -m app.cli seed-demo && uvicorn app.main:app --port 8765
//   cd mobile && AFE_LIVE_API=http://127.0.0.1:8765 AFE_LIVE_BACKEND=../backend flutter test test/live_api_test.dart
//
// AFE_LIVE_BACKEND is the backend folder, used to read demo authenticator codes (debug only).
// AFE_LIVE_PYTHON overrides the Python that runs the CLI. The tenancy test needs the API started
// with AFE_PROTECTED_PAYMENTS_ENABLED=1 on fresh demo data (it offers on the demo's completed viewing).
import 'dart:io';

import 'package:afe/api/client.dart';
import 'package:afe/api/models.dart';
import 'package:afe/api/token_store.dart';
import 'package:afe/session.dart';
import 'package:afe/widgets/common.dart' show isoDay;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

final live = Platform.environment['AFE_LIVE_API'];
final backend = Platform.environment['AFE_LIVE_BACKEND'] ?? '../backend';
final python = Platform.environment['AFE_LIVE_PYTHON'] ??
    (Platform.isWindows ? '$backend/.venv/Scripts/python.exe' : '$backend/.venv/bin/python');
const demoPassword = 'afe-demo-password';

Session newSession() => Session(ApiClient(tokens: MemoryTokenStore(), baseUrl: live, device: 'afe-live-test'));

Future<String> totp(String username) async {
  final r = await Process.run(python, ['-m', 'app.cli', 'totp', username],
      workingDirectory: backend, environment: {'AFE_DEBUG': '1'});
  if (r.exitCode != 0) throw StateError('totp failed: ${r.stderr}');
  return (r.stdout as String).trim();
}

Future<Session> signIn(String username) async {
  final s = newSession();
  var step = await s.signInWithPassword(username, demoPassword);
  if (step is NeedsMfa) step = await s.completeMfa(step.mfaToken, await totp(username));
  expect(step, isA<SignedIn>(), reason: '$username signs in');
  return s;
}

void main() {
  final skip = live == null ? 'set AFE_LIVE_API to run against a live API' : null;

  // The screens from the "Afe Missing Features" canvas. They run first: the older flow below changes
  // a payout account, which then waits 72 hours and can't take an offer.
  test('landlord: settings, fees, appeals, offer a tenancy, edit and feature a listing, tenants', () async {
    final lister = await signIn('ama');
    final api = lister.api;

    // Settings: change the name, see it come back, put it back; the devices signed in.
    final me = lister.me!;
    await api.patch('/me', {'display_name': 'Ama O.', 'whatsapp_opt_in': true});
    await lister.reloadMe();
    expect(lister.me!.user.name, 'Ama O.');
    await api.patch('/me', {'display_name': me.user.displayName.isEmpty ? me.user.name : me.user.displayName});
    expect([for (final d in (await api.get<List>('/me/devices')).data) Device(d as Json)], isNotEmpty);

    // Fees paid and appeals parse.
    for (final f in [for (final f in (await api.get<List>('/me/payments')).data) FeePayment(f as Json)]) {
      expect(f.reference, isNotEmpty);
    }
    expect([for (final x in (await api.get<List>('/me/appealable')).data) Appealable(x as Json)], isA<List<Appealable>>());
    expect([for (final x in (await api.get<List>('/me/appeals')).data) Appeal(x as Json)], isA<List<Appeal>>());

    // Offer a tenancy on the completed viewing: the quote carries the legal cap, an offer over it
    // is refused, then the real offer.
    final config = TenancyConfig((await api.get<Json>('/tenancies/config')).data);
    expect(config.enabled, isTrue, reason: 'start the API with AFE_PROTECTED_PAYMENTS_ENABLED=1');
    final viewings = [for (final v in (await api.get<List>('/viewings')).data) Viewing(v as Json)];
    final done = viewings.firstWhere((v) => v.role == 'lister' && v.status == 'completed');
    final terms = {
      'viewing_id': done.id,
      'move_in_date': isoDay(DateTime.now().add(const Duration(days: 7))),
      'lease_months': 12,
      'advance_months': 6,
      'deposit_months': 1,
    };
    final quote = Quote((await api.post<Json>('/tenancies/quote', terms)).data);
    expect(quote.cap, config.capFor(12));
    expect(quote.payout, startsWith('GH₵'));
    await expectLater(
      api.post('/tenancies', {...terms, 'advance_months': quote.cap + 1}),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('caps advance rent'))),
    );
    expect(Tenancy((await api.post<Json>('/tenancies', terms)).data).reference, startsWith('AFE-T-'));

    // Feature a live listing (waived during the launch offer, else a checkout), then edit it: an
    // edit sends it back to review.
    final units = [for (final u in (await api.get<List>('/me/units')).data) MyUnit(u as Json)];
    final live = units.expand((u) => u.listings).firstWhere((l) => l.status == 'live');
    final detail = ListingDetail((await api.get<Json>('/properties/listings/${live.id}')).data);
    expect(detail.description, isNotEmpty);
    expect(['paid', 'waived', 'pending'], contains((await api.post<Json>('/properties/listings/${live.id}/feature')).data['status']));
    final edited = Listing((await api.patch<Json>('/properties/listings/${live.id}', {'title': '${detail.title} (edited)'})).data);
    expect(edited.status, 'pending_review');

    // Tenants: add one on the renter's number, record rent, prepare and sign the agreement, offer
    // a renewal.
    expect(PlanInfo((await api.get<Json>('/rentals/plan')).data).limit, greaterThan(0));
    final start = DateTime.now().subtract(const Duration(days: 20));
    final rental = Rental((await api.post<Json>('/rentals', {
      'tenant_name': 'Yaa Mensah',
      'tenant_phone': '+233240000009',
      'rent_ghs': 3000,
      'pay_every_months': 1,
      'start_date': isoDay(start),
      'end_date': isoDay(start.add(const Duration(days: 365))),
      'unit_id': null,
    }))
        .data);
    expect(rental.active, isTrue);
    final paid = RentPayment((await api.post<Json>('/rentals/${rental.id}/payments', {
      'amount_ghs': 3000,
      'covers_months': 1,
      'paid_on': isoDay(DateTime.now().subtract(const Duration(days: 1))),
      'method': 'momo',
      'note': '',
    }))
        .data);
    expect(paid.receiptNo, isNotEmpty);
    await api.post('/rentals/${rental.id}/agreements');
    final d = RentalDetail((await api.get<Json>('/rentals/${rental.id}')).data);
    expect(d.landlord, isTrue);
    expect(d.payments.single.receiptNo, paid.receiptNo);
    await api.post('/rentals/agreements/${d.agreements.single.id}/sign', {'typed_name': 'Ama Owusu'});
    await api.post('/rentals/${rental.id}/renewals', {
      'new_end_date': isoDay(start.add(const Duration(days: 365 * 2))),
      'new_rent_ghs': 3200,
      'advance_months': 6,
    });
    expect([for (final r in (await api.get<List>('/rentals')).data) Rental(r as Json)].map((r) => r.id), contains(rental.id));

    // Listings: every listing on the account, the edited one back with Afe for a check.
    final mine = [for (final l in (await api.get<List>('/me/listings')).data) Listing(l as Json)];
    expect(mine.firstWhere((l) => l.id == live.id).status, 'pending_review');

    // Documents open by a five-minute link, as the app hands them to the phone's viewer: the rent
    // receipt, the invoice for the next rent, the agreement, and each fee's invoice or receipt.
    Future<void> opens(String kind, String key) async {
      final link = (await api.post<Json>('/documents/links', {'kind': kind, 'key': key})).data;
      final res = await http.get(Uri.parse('${api.baseUrl}${link['path']}'));
      expect(res.statusCode, 200, reason: '$kind $key');
      expect(res.headers['content-type'], 'application/pdf');
      expect(String.fromCharCodes(res.bodyBytes.take(5)), '%PDF-');
    }

    await opens('rent_receipt', '${rental.id}:${paid.id}');
    await opens('rent_invoice', '${rental.id}');
    await opens('rent_agreement', '${d.agreements.single.id}');
    for (final f in [for (final f in (await api.get<List>('/me/payments')).data) FeePayment(f as Json)]) {
      await opens('fee', f.reference);
    }
    await expectLater(
      api.post('/documents/links', {'kind': 'rent_receipt', 'key': '${rental.id}:999999'}),
      throwsA(isA<ApiException>().having((e) => e.status, 'status', 404)),
    );

    // A plan: free during the launch offer, otherwise the payment partner's checkout.
    final chosen = (await api.post<Json>('/rentals/plan/standard')).data;
    if (chosen['active'] == true) {
      expect(PlanInfo((await api.get<Json>('/rentals/plan')).data).plan, 'standard');
    } else {
      expect('${chosen['checkout_url']}', startsWith('http'));
    }
  }, skip: skip, timeout: const Timeout(Duration(minutes: 2)));

  test('renter: My home (repair, sign, renew), report a scam, rent index and an area, sign out everywhere', () async {
    final renter = await signIn('yaa');
    final api = renter.api;

    final homes = [for (final r in (await api.get<List>('/rentals/my-homes')).data) Rental(r as Json)];
    expect(homes, isNotEmpty, reason: 'the landlord test added a tenancy on this number');
    final id = homes.first.id;
    await api.upload('/rentals/$id/maintenance', fields: {'title': 'Leaking tap', 'details': 'The kitchen tap drips all night long.'});
    var d = RentalDetail((await api.get<Json>('/rentals/$id')).data);
    expect(d.landlord, isFalse);
    expect(d.repairs.map((m) => m.title), contains('Leaking tap'));
    for (final x in d.agreements.where((x) => x.tenantSignedAt == null)) {
      await api.post('/rentals/agreements/${x.id}/sign', {'typed_name': 'Yaa Mensah'});
    }
    for (final rn in d.renewals.where((r) => r.status == 'offered')) {
      await api.post('/rentals/renewals/${rn.id}/accept');
    }
    d = RentalDetail((await api.get<Json>('/rentals/$id')).data);
    expect(d.agreements.every((x) => x.tenantSignedAt != null), isTrue);
    expect(d.renewals.every((r) => r.status != 'offered'), isTrue);

    await api.post('/check/reports', {
      'what_happened': 'Someone asked me for a GH₵ 500 viewing fee by MoMo before any viewing.',
      'reported_phone': '+233555123123',
      'reported_reference': '',
      'amount_lost_ghs': '500',
      'reporter_contact': '',
    });
    final index = RentIndex((await api.get<Json>('/properties/rent-index')).data);
    expect(index.periodDays, greaterThan(0));
    final area = AreaOverview((await api.get<Json>('/properties/areas/${index.areas.isEmpty ? 'east-legon' : index.areas.first.slug}')).data);
    expect(area.name, isNotEmpty);

    // Sign out everywhere: gone on this phone, and the old refresh token no longer works.
    final oldRefresh = await api.tokens.read(TokenStore.refresh);
    await renter.signOutEverywhere();
    expect(renter.me, isNull);
    final stale = newSession();
    await stale.api.saveSession({'access_token': null, 'refresh_token': oldRefresh});
    await expectLater(stale.api.get<Json>('/me'), throwsA(isA<ApiException>()));
  }, skip: skip, timeout: const Timeout(Duration(minutes: 2)));

  test('guest: areas, search and a home\'s details', () async {
    final api = newSession().api;
    final areas = [for (final a in (await api.get<List>('/properties/areas')).data) Area(a as Json)];
    expect(areas, isNotEmpty);
    final homes = [for (final l in (await api.get<List>('/properties/search')).data) Listing(l as Json)];
    expect(homes, isNotEmpty);
    expect(homes.first.rent, startsWith('GH₵'));
    final detail = ListingDetail((await api.get<Json>('/properties/${homes.first.reference}')).data);
    expect(detail.verification, isNotEmpty, reason: 'every live home shows what was checked');
    expect(detail.photos, isNotEmpty);
    final check = CheckResult((await api.get<Json>('/check', query: {'q': '0244123456'})).data);
    expect(check.headline, isNotEmpty);
  }, skip: skip);

  test('renter, landlord and verifier flows', () async {
    // Renter: message a landlord and book a viewing.
    final renter = await signIn('yaa');
    expect(renter.me!.user.isRenter, isTrue);
    final home = Listing((await renter.api.get<List>('/properties/search')).data.first as Json);
    final thread = Thread((await renter.api.post<Json>('/properties/${home.reference}/enquiries',
            {'body': 'Hello, is this still available? When can I view it?'}))
        .data);
    final when = DateTime.now().add(const Duration(days: 2)).copyWith(hour: 10, minute: 0);
    try {
      await renter.api.post('/properties/${home.reference}/viewings', {'when': when.toUtc().toIso8601String()});
    } on ApiException catch (e) {
      expect(e.message, contains('already'), reason: 'rerun: the viewing from last time is still booked');
    }
    final detail = ThreadDetail((await renter.api.get<Json>('/messages/${thread.id}')).data);
    expect(detail.messages, isNotEmpty);
    expect(detail.viewings.first.role, 'renter');
    for (final path in ['/me/saved', '/viewings', '/tenancies', '/messages', '/me/notifications', '/me/searches']) {
      expect((await renter.api.get<List>(path)).data, isA<List>(), reason: path);
    }

    // Landlord or agent who listed that home: their homes, and the viewing request.
    final listerName = ListingDetail((await renter.api.get<Json>('/properties/${home.reference}')).data).listerName;
    final lister = await signIn(listerName.startsWith('Kofi') ? 'kofi' : 'ama');
    final units = [for (final u in (await lister.api.get<List>('/me/units')).data) MyUnit(u as Json)];
    expect(units.map((u) => u.stage), contains('verified'));
    final viewings = [for (final v in (await lister.api.get<List>('/viewings')).data) Viewing(v as Json)];
    expect(viewings.any((v) => v.role == 'lister'), isTrue);
    final payee = (await lister.api.get<Json?>('/me/payouts')).data;
    if (payee != null) expect(Payee(payee).masked, isNotEmpty);

    // The landlord forms: add a home, upload an ownership document, change the payout account.
    final area = Area((await lister.api.get<List>('/properties/areas')).data.first as Json);
    final added = MyUnit((await lister.api.post<Json>('/properties/units', {
      'area_slug': area.slug,
      'digital_address': 'GA-${100 + DateTime.now().second}-${DateTime.now().millisecond.toString().padLeft(4, '0')}',
      'unit_label': 'Flat ${DateTime.now().microsecond}',
      'lat': area.centre!.$1.toStringAsFixed(6),
      'lng': area.centre!.$2.toStringAsFixed(6),
      'property_type': 'apartment',
      'bedrooms': 2,
      'bathrooms': 1,
      'landmark': 'Test landmark',
    }))
        .data);
    expect(added.stage, 'documents');
    final doc = File('${Directory.systemTemp.path}/afe-live-document.jpg');
    final made = await Process.run(python, ['-c', 'from PIL import Image; Image.new("RGB",(1200,1600),(240,240,235)).save(r"${doc.path}","JPEG")']);
    expect(made.exitCode, 0, reason: '${made.stderr}');
    await lister.api.upload('/kyc/units/${added.unit.id}/authority',
        fields: {'relationship': 'owner', 'document_type': 'land_title', 'utility_reference': ''}, files: {'document': doc.path});
    final after = MyUnit((await lister.api.get<Json>('/properties/units/${added.unit.id}')).data);
    expect(after.stage, isNot('documents'), reason: 'the document moves the home on');
    final listerUser = listerName.startsWith('Kofi') ? 'kofi' : 'ama';
    final wallet = listerUser == 'kofi' ? '0501234567' : '0244123456';
    Future<Payee> setPayee(String channel) async => Payee((await lister.api.post<Json>('/me/payouts', {
          'channel': channel,
          'account_number': wallet,
          'code': await totp(listerUser),
        }))
            .data);
    final current = (await lister.api.get<Json?>('/me/payouts')).data;
    if (current == null) {
      final first = await setPayee('momo_mtn');
      expect(first.usableFrom!.isAfter(DateTime.now().add(const Duration(minutes: 1))), isFalse,
          reason: 'the first payout account works straight away');
    }
    final now = (await lister.api.get<Json?>('/me/payouts')).data!;
    final changed = await setPayee(Payee(now).channel == 'momo_mtn' ? 'momo_telecel' : 'momo_mtn');
    expect(changed.usableFrom!.isAfter(DateTime.now().add(const Duration(hours: 71))), isTrue,
        reason: 'a changed payout account waits 72 hours');

    // Field verifier: the worklist, then a visit with a photo through the upload queue's call.
    final verifier = await signIn('verifier');
    expect(verifier.me!.user.isVerifier, isTrue);
    final work = Worklist((await verifier.api.get<Json>('/verify/worklist')).data);
    expect(work.radiusM, greaterThan(0));
    if (work.assignments.isNotEmpty) {
      final unit = work.assignments.first.unit;
      final visit = Visit((await verifier.api.post<Json>('/verify/visits', {'unit_id': unit.id, 'lat': unit.lat, 'lng': unit.lng})).data);
      final v = VisitDetail((await verifier.api.get<Json>('/verify/visits/${visit.id}')).data);
      expect(v.checklistItems, isNotEmpty);
      expect(v.captions, isNotEmpty);
      final jpeg = File('${Directory.systemTemp.path}/afe-live-photo.jpg');
      final r = await Process.run(python, ['-c', 'from PIL import Image; Image.new("RGB",(800,600),(90,140,110)).save(r"${jpeg.path}","JPEG")']);
      expect(r.exitCode, 0, reason: '${r.stderr}');
      final ref = 'live-${DateTime.now().microsecondsSinceEpoch}';
      Future<ApiResult<Json>> send() => verifier.api.upload<Json>('/verify/visits/${visit.id}/photos', fields: {
            'lat': '${unit.lat}',
            'lng': '${unit.lng}',
            'taken_at': DateTime.now().toUtc().toIso8601String(),
            'caption': v.captions.first,
            'client_ref': ref,
          }, files: {
            'photo': jpeg.path,
          });
      final first = Photo((await send()).data);
      final retry = Photo((await send()).data);
      expect(retry.id, first.id, reason: 'a retried upload with the same client_ref is stored once');
    }

    await renter.signOut();
    expect(renter.me, isNull);
  }, skip: skip, timeout: const Timeout(Duration(minutes: 2)));
}
