// The API's shapes the app uses, mirroring backend/app/api/schemas.py (the API's
// /api/openapi.json is the source of truth). Only the fields the app shows are read.

typedef Json = Map<String, dynamic>;

String _s(Object? v) => v?.toString() ?? '';
int _i(Object? v) => v is int ? v : int.tryParse('$v') ?? 0;
double? _d(Object? v) => v == null ? null : (v is num ? v.toDouble() : double.tryParse('$v'));
DateTime? _t(Object? v) => v == null ? null : DateTime.tryParse('$v')?.toLocal();
List<T> _list<T>(Object? v, T Function(Json) f) => [for (final x in (v as List? ?? const [])) f(x as Json)];

class User {
  User(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get name => _s(j['name']);
  String get displayName => _s(j['display_name']);
  String get role => _s(j['role']);
  String get roleLabel => _s(j['role_label']);
  String? get phone => j['phone'] as String?;
  String? get email => j['email'] as String?;
  bool get whatsappOptIn => j['whatsapp_opt_in'] == true;
  bool get privacyCurrent => j['privacy_current'] != false;

  bool get isRenter => role == 'renter';
  bool get isLister => role == 'landlord' || role == 'agent';
  bool get isVerifier => role == 'field_verifier';
  bool get isReviewer => role == 'reviewer' || role == 'admin';
}

class Me {
  Me(this.j) : user = User(j['user'] as Json);
  final Json j;
  final User user;
  int get unread => _i(j['unread_notifications']);
  bool get verified => (j['verification'] as Json?)?['verified'] == true;
}

class Area {
  Area(this.j);
  final Json j;
  String get slug => _s(j['slug']);
  String get name => _s(j['name']);

  /// The area's outline as [lat, lng] points. A home's pin must fall inside it.
  List<(double, double)> get boundary => [
        for (final p in (j['boundary'] as List? ?? const []))
          if (p is List && p.length == 2) (_d(p[0]) ?? 0, _d(p[1]) ?? 0),
      ];

  /// The middle of the outline: where the map starts when adding a home here.
  (double, double)? get centre {
    final b = boundary;
    if (b.isEmpty) return null;
    return (b.map((p) => p.$1).reduce((a, c) => a + c) / b.length, b.map((p) => p.$2).reduce((a, c) => a + c) / b.length);
  }
}

class Listing {
  Listing(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get reference => _s(j['reference']);
  String get title => _s(j['title']);
  String get rent => _s(j['rent_display']);
  int get advanceMonths => _i(j['advance_months']);
  String get advanceTotal => _s(j['advance_total_display']);
  int get bedrooms => _i(j['bedrooms']);
  String get propertyType => _s(j['property_type_label']);
  String get area => _s(j['area']);
  String get status => _s(j['status']);
  String get statusReason => _s(j['status_reason']);
  String? get coverUrl => j['cover_url'] as String?;
  bool get featured => j['featured'] == true;
  double? get lat => _d(j['approx_lat']);
  double? get lng => _d(j['approx_lng']);
  DateTime? get availableFrom => _t(j['available_from']);
}

class Photo {
  Photo(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get url => _s(j['url']);
  String get caption => _s(j['caption']);
  bool get duplicate => j['duplicate_of_id'] != null;
}

class Review {
  Review(this.j);
  final Json j;
  int get rating => _i(j['rating']);
  String get body => _s(j['body']);
  String get author => _s(j['author_name']);
}

class ListingDetail extends Listing {
  ListingDetail(super.j);
  String get description => _s(j['description']);
  String get listerName => _s(j['lister_name']);
  String get listerRole => _s(j['lister_role']);
  List<Photo> get photos => _list(j['photos'], Photo.new);
  List<({String text, String date})> get verification => [
        for (final l in (j['verification'] as List? ?? const [])) (text: _s(l['text']), date: _s(l['date'])),
      ];
  bool get saved => j['saved'] == true;
  double? get rating => _d(j['landlord_rating']);
  int get reviewCount => _i(j['landlord_review_count']);
  List<Review> get reviews => _list(j['reviews'], Review.new);
  int get minLease => _i(j['min_lease_months']);
  int get rentPesewas => _i(j['rent_pesewas']);
  DateTime? get featuredUntil => _t(j['featured_until']);
}

class Thread {
  Thread(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get listingReference => _s(j['listing_reference']);
  String get listingTitle => _s(j['listing_title']);
  String get otherName => _s(j['other_name']);
  bool get unread => j['unread'] == true;
  DateTime? get lastMessageAt => _t(j['last_message_at']);
}

class Message {
  Message(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get sender => _s(j['sender']);
  bool get mine => j['mine'] == true;
  bool get system => j['system'] == true;
  String get body => _s(j['body']);
  String get warning => _s(j['warning']);
  DateTime? get at => _t(j['created_at']);
}

class Viewing {
  Viewing(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get listingReference => _s(j['listing_reference']);
  String get listingTitle => _s(j['listing_title']);
  String get otherName => _s(j['other_name']);
  String get role => _s(j['role']);
  DateTime? get when => _t(j['requested_for']);
  String get status => _s(j['status']);
  String get note => _s(j['note']);
  String get responseNote => _s(j['response_note']);
  int get threadId => _i(j['thread_id']);
  String? get outcome => j['outcome'] as String?;
}

class ThreadDetail extends Thread {
  ThreadDetail(super.j);
  List<Message> get messages => _list(j['messages'], Message.new);
  List<Viewing> get viewings => _list(j['viewings'], Viewing.new);
}

class Tenancy {
  Tenancy(this.j);
  final Json j;
  String get reference => _s(j['reference']);
  String get status => _s(j['status']);
  String get role => _s(j['role']);
  List<String> get actions => [for (final a in (j['actions'] as List? ?? const [])) '$a'];
  bool can(String action) => actions.contains(action);
  String get listingTitle => _s(j['listing_title']);
  String get address => _s(j['address']);
  String get area => _s(j['area']);
  String get landlordName => _s(j['landlord_name']);
  String get tenantName => _s(j['tenant_name']);
  String get rent => _s(j['rent_display']);
  int get advanceMonths => _i(j['advance_months']);
  int get leaseMonths => _i(j['lease_months']);
  DateTime? get moveInDate => _t(j['move_in_date']);
  String get held => _s(j['held_display']);
  String get fee => _s(j['fee_display']);
  String get charge => _s(j['charge_display']);
  String get payout => _s(j['payout_display']);
  int get payoutPesewas => _i(j['payout_pesewas']);
  DateTime? get offerExpiresAt => _t(j['offer_expires_at']);
  String get checkoutUrl => _s(j['checkout_url']);
  DateTime? get acceptedAt => _t(j['accepted_at']);
  DateTime? get fundedAt => _t(j['funded_at']);
  DateTime? get tenantConfirmedAt => _t(j['tenant_confirmed_at']);
  DateTime? get closedAt => _t(j['closed_at']);
  String get closeReason => _s(j['close_reason']);
  Json? get dispute => j['dispute'] as Json?;
  bool get hasReceipt => j['has_receipt'] == true;
  bool get hasAgreement => j['has_agreement'] == true;
  bool get hasMoveInPhoto => j['has_move_in_photo'] == true;
}

class AppNotification {
  AppNotification(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get title => _s(j['title']);
  String get body => _s(j['body']);
  String get link => _s(j['link']);
  DateTime? get at => _t(j['created_at']);
  bool get read => j['read_at'] != null;
}

class SavedSearch {
  SavedSearch(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get description => _s(j['description']);
  String get channel => _s(j['channel']);
  int get alertsSent => _i(j['alerts_sent']);
}

class CheckResult {
  CheckResult(this.j);
  final Json j;
  bool get verified => j['verified'] == true;
  String get headline => _s(j['headline']);
  List<String> get details => [for (final d in (j['details'] as List? ?? const [])) '$d'];
  List<String> get advice => [for (final d in (j['advice'] as List? ?? const [])) '$d'];
  List<Listing> get listings => _list(j['listings'], Listing.new);
}

class Unit {
  Unit(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get digitalAddress => _s(j['digital_address']);
  String get label => _s(j['unit_label']);
  double get lat => _d(j['lat']) ?? 0;
  double get lng => _d(j['lng']) ?? 0;
  String get propertyType => _s(j['property_type_label']);
  int get bedrooms => _i(j['bedrooms']);
  int get bathrooms => _i(j['bathrooms']);
  String get landmark => _s(j['landmark']);
  String get area => _s((j['area'] as Json?)?['name']);
}

class MyUnit {
  MyUnit(this.j) : unit = Unit(j['unit'] as Json);
  final Json j;
  final Unit unit;
  String get stage => _s(j['stage']);
  DateTime? get visitScheduledFor => _t(j['visit_scheduled_for']);
  List<Listing> get listings => _list(j['listings'], Listing.new);
  DateTime? get verifiedUntil => _t((j['verification'] as Json?)?['expires_at']);
  bool get feeRequired => j['fee_required'] == true;
  List<Authority> get authorities => _list(j['authorities'], Authority.new);
}

/// An ownership or authority document uploaded for a home.
class Authority {
  Authority(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get documentLabel => _s(j['document_label']);
  String get relationshipLabel => _s(j['relationship_label']);
  String get status => _s(j['status']);
  String get reviewNote => _s(j['review_note']);
}

class Payee {
  Payee(this.j);
  final Json j;
  String get channel => _s(j['channel']);
  String get masked => _s(j['masked']);
  String get accountName => _s(j['account_name']);
  String get status => _s(j['status']);
  DateTime? get usableFrom => _t(j['usable_from']);
}

class Assignment {
  Assignment(this.j) : unit = Unit(j['unit'] as Json);
  final Json j;
  final Unit unit;
  int get id => _i(j['id']);
  String get status => _s(j['status']);
  DateTime? get scheduledFor => _t(j['scheduled_for']);
  String get note => _s(j['note']);
  String get landlordName => _s(j['landlord_name']);
  String? get landlordPhone => j['landlord_phone'] as String?;
  String get purpose => _s(j['purpose']);
}

class Visit {
  Visit(this.j);
  final Json j;
  int get id => _i(j['id']);
  int get unitId => _i(j['unit_id']);
  String get outcome => _s(j['outcome']);
  DateTime? get startedAt => _t(j['started_at']);
  DateTime? get completedAt => _t(j['completed_at']);
}

class Worklist {
  Worklist(this.j);
  final Json j;
  List<Assignment> get assignments => _list(j['assignments'], Assignment.new);
  List<Visit> get inProgress => _list(j['in_progress'], Visit.new);
  int get radiusM => _i(j['radius_m']);
}

class VisitDetail extends Visit {
  VisitDetail(super.j) : unit = Unit(j['unit'] as Json);
  final Unit unit;
  List<Photo> get photos => _list(j['photos'], Photo.new);
  Map<String, String> get checklistItems =>
      {for (final e in ((j['checklist_items'] as Map?) ?? const {}).entries) '${e.key}': '${e.value}'};
  List<String> get captions => [for (final c in (j['captions'] as List? ?? const [])) '$c'];
  int get minPhotos => _i(j['min_photos']);
  int get radiusM => _i(j['radius_m']);
  double get checkinDistanceM => _d(j['checkin_distance_m']) ?? 0;
}

// --- Account ------------------------------------------------------------------------------------

/// A device signed in to this account (Settings).
class Device {
  Device(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get name => _s(j['device']);
  DateTime? get since => _t(j['created_at']);
}

/// A fee, featured listing or plan paid through Afe's payment partner.
class FeePayment {
  FeePayment(this.j);
  final Json j;
  String get reference => _s(j['reference']);
  String get purpose => _s(j['purpose']);
  String get amount => _s(j['amount_display']);
  int get amountPesewas => _i(j['amount_pesewas']);
  String get status => _s(j['status']);
  String get checkoutUrl => _s(j['checkout_url']);
  String get note => _s(j['note']);
  String get subject => _s(j['subject']);
  DateTime? get at => _t(j['paid_at']) ?? _t(j['created_at']);
}

/// A decision this person can still appeal.
class Appealable {
  Appealable(this.j);
  final Json j;
  String get kind => _s(j['kind']);
  int get subjectId => _i(j['subject_id']);
  String get label => _s(j['label']);
  DateTime? get date => _t(j['date']);
}

class Appeal {
  Appeal(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get kind => _s(j['kind']);
  int get subjectId => _i(j['subject_id']);
  String get reason => _s(j['reason']);
  String get status => _s(j['status']);
  String get outcome => _s(j['outcome']);
  DateTime? get at => _t(j['created_at']);
  DateTime? get decidedAt => _t(j['decided_at']);
}

// --- Offering a tenancy ------------------------------------------------------------------------------

class TenancyConfig {
  TenancyConfig(this.j);
  final Json j;
  bool get enabled => j['enabled'] == true;
  DateTime? get freeUntil => _t(j['free_until']);
  int get feeBps => _i(j['fee_bps']);
  int get capLong => _i(j['advance_cap_months_long']);
  int get capShort => _i(j['advance_cap_months_short']);
  int get maxDeposit => _i(j['max_deposit_months']);
  int capFor(int leaseMonths) => leaseMonths > 6 ? capLong : capShort;
}

class Quote {
  Quote(this.j);
  final Json j;
  String get held => _s(j['held_display']);
  int get feePesewas => _i(j['fee_pesewas']);
  String get fee => _s(j['fee_display']);
  String get feePayer => _s(j['fee_payer']);
  String get charge => _s(j['charge_display']);
  String get payout => _s(j['payout_display']);
  int get cap => _i(j['advance_cap_months']);
}

// --- Landlord tools: tenants and rent ------------------------------------------------------------------

class Rental {
  Rental(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get tenantName => _s(j['tenant_name']);
  String get tenantPhone => _s(j['tenant_phone']);
  int get rentPesewas => _i(j['rent_pesewas']);
  int get payEveryMonths => _i(j['pay_every_months']);
  DateTime? get start => _t(j['start_date']);
  DateTime? get end => _t(j['end_date']);
  DateTime? get nextDue => _t(j['next_due_date']);
  String get status => _s(j['status']);
  bool get fromAfe => j['from_afe'] == true;
  bool get tenantOnAfe => j['tenant_on_afe'] == true;
  String get landlordName => _s(j['landlord_name']);
  String get home => _s(j['home']);
  bool get active => status == 'active';
}

class RentPayment {
  RentPayment(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get receiptNo => _s(j['receipt_no']);
  int get amountPesewas => _i(j['amount_pesewas']);
  DateTime? get paidOn => _t(j['paid_on']);
  String get method => _s(j['method']);
  int get coversMonths => _i(j['covers_months']);
  String get note => _s(j['note']);
}

class Repair {
  Repair(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get title => _s(j['title']);
  String get details => _s(j['details']);
  String get status => _s(j['status']);
  String get landlordNote => _s(j['landlord_note']);
  DateTime? get at => _t(j['created_at']);
  bool get hasPhoto => j['has_photo'] == true;
}

class RentalAgreement {
  RentalAgreement(this.j);
  final Json j;
  int get id => _i(j['id']);
  String get body => _s(j['body']);
  String get landlordSignedName => _s(j['landlord_signed_name']);
  DateTime? get landlordSignedAt => _t(j['landlord_signed_at']);
  String get tenantSignedName => _s(j['tenant_signed_name']);
  DateTime? get tenantSignedAt => _t(j['tenant_signed_at']);
}

class Renewal {
  Renewal(this.j);
  final Json j;
  int get id => _i(j['id']);
  DateTime? get newEnd => _t(j['new_end_date']);
  int get newRentPesewas => _i(j['new_rent_pesewas']);
  int get advanceMonths => _i(j['advance_months']);
  String get status => _s(j['status']);
}

class RentalDetail {
  RentalDetail(this.j) : rental = Rental(j['rental'] as Json);
  final Json j;
  final Rental rental;
  bool get landlord => j['role'] == 'landlord';
  List<RentPayment> get payments => _list(j['payments'], RentPayment.new);
  List<Repair> get repairs => _list(j['maintenance'], Repair.new);
  List<RentalAgreement> get agreements => _list(j['agreements'], RentalAgreement.new);
  List<Renewal> get renewals => _list(j['renewals'], Renewal.new);
}

class PlanInfo {
  PlanInfo(this.j);
  final Json j;
  String get plan => _s(j['plan']);
  String get label => _s(j['label']);
  int get limit => _i(j['limit']);
  int get used => _i(j['used']);
  bool get launchOffer => j['launch_offer'] == true;
  DateTime? get periodEnd => _t(j['period_end']);
  bool get full => limit > 0 && used >= limit;

  /// Monthly price in pesewas for 'standard' and 'pro'.
  int price(String plan) => _i((j['prices'] as Map?)?[plan]);
}

// --- Rent index and areas -----------------------------------------------------------------------------------

typedef RentFigure = ({int median, int count});

class RentIndex {
  RentIndex(this.j);
  final Json j;
  int get periodDays => _i(j['period_days']);
  DateTime? get asOf => _t(j['as_of']);
  List<({String name, String slug, Map<int, RentFigure> sizes})> get areas => [
    for (final a in (j['areas'] as List? ?? const []))
      (
        name: _s(a['name']),
        slug: _s(a['slug']),
        sizes: {
          for (final e in ((a['sizes'] as Map?) ?? const {}).entries)
            _i(e.key): (median: _i((e.value as Map)['median']), count: _i((e.value as Map)['count'])),
        },
      ),
  ];
}

typedef RentRange = ({int bedrooms, int low, int median, int high, int count, String source});

class AreaOverview {
  AreaOverview(this.j);
  final Json j;
  String get name => _s((j['area'] as Json?)?['name']);
  String get slug => _s((j['area'] as Json?)?['slug']);
  String get city => _s((j['area'] as Json?)?['city']);
  int get live => _i(j['live']);
  List<RentRange> get ranges => [
    for (final r in (j['ranges'] as List? ?? const []))
      (
        bedrooms: _i(r['bedrooms']),
        low: _i(r['low']),
        median: _i(r['median']),
        high: _i(r['high']),
        count: _i(r['count']),
        source: _s(r['source']),
      ),
  ];
  List<Listing> get listings => _list(j['listings'], Listing.new);
}
