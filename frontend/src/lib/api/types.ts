// Mirrors backend/app/api/schemas.py. The API's OpenAPI document (/api/openapi.json) is
// the source of truth; keep these in step when a schema changes.

export type Role = 'renter' | 'landlord' | 'agent' | 'field_verifier' | 'reviewer' | 'admin';

export interface Envelope<T> {
	data: T | null;
	meta: Record<string, unknown>;
	error: { code: string; message: string; reasons: string[] } | null;
}

export interface User {
	id: number;
	username: string;
	display_name: string;
	name: string;
	role: Role;
	role_label: string;
	phone: string | null;
	email: string | null;
	whatsapp_opt_in: boolean;
	mfa_enabled: boolean;
	has_password: boolean;
	privacy_current: boolean;
	is_active: boolean;
}

export interface VerificationStatus {
	verified: boolean;
	expires_at: string | null;
	latest_decision: string | null;
	identity_check: 'passed' | 'failed' | null;
}

export interface Me {
	user: User;
	verification: VerificationStatus | null;
	unread_notifications: number;
}

export interface SignIn {
	status: 'signed_in' | 'mfa_required' | 'mfa_setup';
	user: User;
	access_token: string;
	refresh_token: string;
	expires_in: number;
	mfa_token: string;
	otpauth_uri: string;
	totp_secret: string;
}

export interface Device {
	id: number;
	device: string;
	created_at: string;
}

export interface Notification {
	id: number;
	title: string;
	body: string;
	link: string;
	created_at: string;
	read_at: string | null;
}

export interface Area {
	id: number;
	slug: string;
	name: string;
	city: string;
	country: string;
	boundary: [number, number][];
}

export interface Unit {
	id: number;
	digital_address: string;
	unit_label: string;
	lat: string;
	lng: string;
	property_type: string;
	property_type_label: string;
	bedrooms: number;
	bathrooms: number;
	landmark: string;
	area: Area;
}

export interface IdentityCheck {
	id: number;
	status: 'passed' | 'failed';
	masked_card: string;
	name_on_card: string;
	name_matches: boolean;
	liveness_passed: boolean;
	failure_reason: string;
	provider: string;
	created_at: string;
}

export interface Authority {
	id: number;
	unit_id: number;
	party_id: number;
	relationship_type: string;
	relationship_label: string;
	document_type: string;
	document_label: string;
	utility_reference: string;
	status: 'pending' | 'accepted' | 'rejected';
	review_note: string;
	owner_name: string;
	owner_confirmed_at: string | null;
	created_at: string;
}

export interface Payment {
	reference: string;
	purpose: string;
	unit_id: number | null;
	amount_pesewas: number;
	amount_display: string;
	status: 'pending' | 'paid' | 'failed' | 'waived';
	checkout_url: string;
	note: string;
	created_at: string;
	paid_at: string | null;
	listing_id?: number | null;
	/** What it paid for ("GA-543-2210 · Flat 3"); only on the payments list. */
	subject?: string;
}

export interface Photo {
	id: number;
	url: string;
	width: number;
	height: number;
	caption: string;
	taken_at: string;
	duplicate_of_id: number | null;
}

export interface Visit {
	id: number;
	unit_id: number;
	outcome: 'in_progress' | 'passed' | 'failed';
	started_at: string;
	completed_at: string | null;
	checklist: Record<string, boolean>;
	notes: string;
}

export interface VisitDetail extends Visit {
	unit: Unit;
	verifier_name: string;
	checkin_distance_m: number;
	photos: Photo[];
	checklist_items: Record<string, string>;
	captions: string[];
	min_photos: number;
	radius_m: number;
}

export interface Assignment {
	id: number;
	status: 'open' | 'done' | 'cancelled';
	scheduled_for: string;
	note: string;
	verifier_id: number;
	verifier_name: string;
	unit: Unit;
	landlord_name: string;
	landlord_phone: string | null;
	purpose: 'verification' | 'qa_recheck';
}

export interface Worklist {
	assignments: Assignment[];
	in_progress: Visit[];
	radius_m: number;
}

export interface Verification {
	id: number;
	party_id: number | null;
	unit_id: number | null;
	status: 'approved' | 'rejected' | 'revoked';
	reason_codes: string[];
	note: string;
	decided_at: string;
	expires_at: string | null;
	decided_by_name: string;
}

export interface Flag {
	id: number;
	subject_type: string;
	subject_id: string;
	rule: string;
	severity: 'low' | 'medium' | 'high';
	explanation: string;
	status: string;
	created_at: string;
}

export interface ReasonCode {
	code: string;
	label: string;
	approval: boolean;
}

export interface Listing {
	id: number;
	reference: string;
	title: string;
	rent_pesewas: number;
	rent_display: string;
	advance_months: number;
	advance_total_display: string;
	min_lease_months: number;
	available_from: string;
	status: 'draft' | 'pending_review' | 'live' | 'paused' | 'let' | 'archived';
	status_reason: string;
	published_at: string | null;
	bedrooms: number;
	property_type_label: string;
	area: string;
	area_slug: string;
	cover_url: string | null;
	featured: boolean;
	approx_lat: number | null;
	approx_lng: number | null;
}

export interface PanelLine {
	text: string;
	date: string;
}

export interface ListingDetail extends Listing {
	description: string;
	lister_name: string;
	lister_role: string;
	city: string;
	photos: Photo[];
	verification: PanelLine[];
	saved: boolean;
	landlord_rating: number | null;
	landlord_review_count: number;
	reviews: Review[];
	featured_until: string | null;
	tenancy_available: boolean;
}

export type HomeStage = 'documents' | 'fee' | 'visit' | 'review' | 'verified' | 'rejected';

export interface MyUnit {
	unit: Unit;
	stage: HomeStage;
	authorities: Authority[];
	fee_required: boolean;
	fee_settled: boolean;
	visit_scheduled_for: string | null;
	latest_visit_outcome: string | null;
	verification: Verification | null;
	listings: Listing[];
}

export interface Message {
	id: number;
	sender: string;
	mine: boolean;
	system: boolean;
	body: string;
	warning: string;
	created_at: string;
}

export interface Thread {
	id: number;
	listing_reference: string;
	listing_title: string;
	other_name: string;
	role: 'renter' | 'lister';
	last_message_at: string;
	unread: boolean;
}

export interface Viewing {
	id: number;
	listing_reference: string;
	listing_title: string;
	other_name: string;
	role: 'renter' | 'lister';
	requested_for: string;
	status: 'requested' | 'confirmed' | 'declined' | 'cancelled' | 'completed' | 'no_show';
	note: string;
	response_note: string;
	thread_id: number;
	outcome?: string | null;
}

export interface ThreadDetail extends Thread {
	messages: Message[];
	viewings: Viewing[];
}

export interface CheckResult {
	verified: boolean;
	headline: string;
	details: string[];
	advice: string[];
	listings: Listing[];
}

export interface PersonReview {
	user: User;
	identity: IdentityCheck | null;
	current: Verification | null;
	history: Verification[];
	flags: Flag[];
	model_notes: ModelNote[];
	links: AccountLink[];
	reviews: ReviewModeration[];
}

/** A tenant's review as a reviewer sees it, hidden ones included. */
export interface ReviewModeration {
	id: number;
	rating: number;
	body: string;
	author_name: string;
	listing_reference: string;
	created_at: string;
	hidden: boolean;
}

export interface HomeReview {
	unit: Unit;
	registered_by: User;
	authorities: Authority[];
	visit: VisitDetail | null;
	current: Verification | null;
	history: Verification[];
	flags: Flag[];
	fee_settled: boolean;
	open_assignment: Assignment | null;
	model_notes: ModelNote[];
}

export interface QueueHome {
	id: number;
	address: string;
	area: string;
	landlord: string;
	last_visit: string | null;
}

export interface Queue {
	people: { id: number; name: string; role: string; phone: string | null; last_check: string }[];
	homes_to_decide: QueueHome[];
	homes_to_visit: QueueHome[];
	homes_awaiting_fee: QueueHome[];
	assignments: Assignment[];
	listings: { listing: Listing; lister: string; blockers: string[] }[];
	flags: Flag[];
}

// --- Phase 2: protected payments --------------------------------------------------------------

export type TenancyStatus =
	| 'offered'
	| 'funding'
	| 'funded'
	| 'disputed'
	| 'release_pending'
	| 'releasing'
	| 'released'
	| 'refunding'
	| 'refunded'
	| 'declined'
	| 'withdrawn'
	| 'expired';

export type TenancyAction =
	| 'accept'
	| 'decline'
	| 'pay'
	| 'confirm_move_in'
	| 'dispute'
	| 'review'
	| 'withdraw'
	| 'record_move_in'
	| 'approve_release'
	| 'decide';

export interface Review {
	id: number;
	rating: number;
	body: string;
	author_name: string;
	created_at: string;
}

export interface Dispute {
	id: number;
	tenancy_reference: string;
	reason: string;
	reason_label: string;
	details: string;
	status: 'open' | 'resolved';
	decision: '' | 'release' | 'refund';
	decision_note: string;
	opened_by_name: string;
	created_at: string;
	decided_at: string | null;
}

export interface Tenancy {
	reference: string;
	status: TenancyStatus;
	role: 'tenant' | 'landlord' | 'reviewer';
	actions: TenancyAction[];
	listing_reference: string;
	listing_title: string;
	address: string;
	area: string;
	landlord_name: string;
	tenant_name: string;
	rent_display: string;
	advance_months: number;
	deposit_months: number;
	lease_months: number;
	move_in_date: string;
	held_display: string;
	fee_display: string;
	fee_pesewas: number;
	fee_payer: 'tenant' | 'landlord' | 'split';
	charge_display: string;
	payout_display: string;
	charge_pesewas: number;
	held_pesewas: number;
	payout_pesewas: number;
	offer_expires_at: string;
	checkout_url: string;
	accepted_at: string | null;
	funded_at: string | null;
	tenant_confirmed_at: string | null;
	landlord_evidence_at: string | null;
	landlord_evidence: string;
	closed_at: string | null;
	close_reason: string;
	has_agreement: boolean;
	has_receipt: boolean;
	has_move_in_photo: boolean;
	payee: string;
	dispute: Dispute | null;
	review: Review | null;
}

export interface TenancyConfig {
	enabled: boolean;
	free_until: string | null;
	fee_bps: number;
	fee_payer: string;
	advance_cap_months_long: number;
	advance_cap_months_short: number;
	max_deposit_months: number;
}

export interface Quote {
	held_pesewas: number;
	fee_pesewas: number;
	fee_payer: string;
	charge_pesewas: number;
	payout_pesewas: number;
	held_display: string;
	fee_display: string;
	charge_display: string;
	payout_display: string;
	advance_cap_months: number;
}

export interface Payee {
	id: number;
	channel: 'momo_mtn' | 'momo_telecel' | 'momo_at' | 'bank';
	masked: string;
	account_name: string;
	status: 'active' | 'superseded';
	usable_from: string;
}

export interface Rule {
	key: string;
	label: string;
	value: unknown;
	version: number;
	source: string;
	pending: { id: number; value: unknown; version: number; source: string; proposed_by_name: string; proposed_at: string }[];
}

export interface Finance {
	by_status: Record<string, { count: number; held_pesewas: number }>;
	held_now_pesewas: number;
	fees_earned_pesewas: number;
}

export interface Mismatch {
	partner_ref: string;
	kind: string;
	problem: string;
	tenancy: string;
	ours: number | null;
	theirs: number | null;
}

// --- Phase 3: detection ------------------------------------------------------------------------

export type ModelMode = 'off' | 'shadow' | 'canary' | 'active';

export interface ModelNote {
	detector: string;
	label: string;
	subject: string;
	version: string;
	score: number;
	threshold: number;
	reasons: string[];
	mode: ModelMode;
	acted: boolean;
	created_at: string;
}

export interface AccountLink {
	other_user_id: number;
	other_name: string;
	kind: 'ghana_card' | 'payout_account' | 'photo' | 'phone_in_message';
	evidence: string;
}

export interface Tally {
	tp: number;
	fp: number;
	fn: number;
	tn: number;
	flagged: number;
	precision: number | null;
	recall: number | null;
}

export interface Detector {
	name: string;
	label: string;
	mode: ModelMode;
	threshold: number;
	version: string | null;
	scores: number;
	acted: number;
	pending: number;
	failed: number;
	evaluation: {
		version: string | null;
		labels: number;
		fraud: number;
		model: Tally;
		rules: Tally;
		promotable: boolean;
		reason: string;
	};
}

export interface EvaluationSnapshot {
	detector: string;
	week: string;
	version: string | null;
	labels: number;
	fraud: number;
	model: Tally;
	rules: Tally;
	promotable: boolean;
	reason: string;
	seeded: { cases: number; fraud: number; skipped: number; model: Tally; rules: Tally; missed: string[] } | null;
	created_at: string;
}

export interface CopilotNumbers {
	level: string;
	days: number;
	runs: number;
	done: number;
	failed: number;
	refused: number;
	too_late: number;
	decided: number;
	agreement: number | null;
	false_approvals: number;
	code_overlap: number | null;
	cost_usd: number;
}

export interface ModelVersion {
	detector: string;
	version: string;
	trained_on: number;
	notes: string;
	created_at: string;
}

export interface FraudReport {
	id: number;
	created_at: string;
	channel: string;
	reported_phone: string;
	reported_reference: string;
	what_happened: string;
	amount_lost_pesewas: number | null;
	status: 'new' | 'upheld' | 'not_upheld';
	matched_user_id: number | null;
	matched_user_name: string;
	matched_listing_title: string;
}

export interface Pricing {
	launch_offer: boolean;
	free_until: string;
	verification_fee_pesewas: number;
	protection_fee_bps: number;
	featured_fee_pesewas: number;
	featured_days: number;
}

export interface VerifierStats {
	id: number;
	name: string;
	active: boolean;
	visits: number;
	passed: number;
	failed: number;
	pass_rate: number | null;
	rechecked: number;
	reversals: number;
}

export interface StaffMember extends User {
	is_active: boolean;
	created_at: string;
}

export interface SavedSearch {
	id: number;
	description: string;
	area_slug: string | null;
	bedrooms: number | null;
	max_rent_pesewas: number | null;
	channel: 'sms' | 'whatsapp' | 'in_app';
	alerts_sent: number;
	created_at: string;
}

export interface RentRange {
	bedrooms: number;
	low: number;
	median: number;
	high: number;
	count: number;
	source: 'afe' | 'survey';
}

export interface AreaOverview {
	area: Area;
	live: number;
	ranges: RentRange[];
	listings: Listing[];
}

export interface Appeal {
	id: number;
	kind: 'verification' | 'listing' | 'report';
	subject_id: number;
	reason: string;
	status: 'open' | 'upheld' | 'rejected';
	outcome: string;
	created_at: string;
	decided_at: string | null;
	appellant_name: string;
}

export interface Appealable {
	kind: Appeal['kind'];
	subject_id: number;
	label: string;
	date: string | null;
}

export interface Workload {
	sla_days: number;
	queues: { queue: string; count: number; oldest_days: number | null; over_sla: number }[];
	median_days_to_live: number | null;
	homes_live_last_30_days: number;
	decisions_last_7_days: { reviewer: string; decisions: number }[];
}

export interface RouteStop {
	unit_id: number;
	address: string;
	landlord: string;
	lat: number;
	lng: number;
}

export interface VisitPlan {
	day: string;
	per_verifier: number;
	routes: { verifier_id: number; verifier_name: string; area: string; km: number; stops: RouteStop[] }[];
	unplanned: RouteStop[];
}

export interface LabelCheck {
	id: number;
	subject: string;
	outcome: 'fraud' | 'legit';
	source: string;
	reasons: string[];
	decided_at: string;
}

export interface PersonGraph {
	nodes: { id: number; name: string; role: string; active: boolean; verified: boolean | null; flags: number; fraud: boolean; focus: boolean }[];
	edges: { a: number; b: number; kind: string; evidence: string }[];
}

export interface Target {
	name: string;
	value: number | null;
	target: string;
	met: boolean | null;
	note: string;
}

export interface RentIndex {
	period_days: number;
	as_of: string;
	areas: { name: string; slug: string; sizes: Record<string, { median: number; count: number }> }[];
}

export interface AreaAdmin extends Area {
	is_active: boolean;
	missing: string[];
	surveyed_sizes: number[];
}

export interface Rental {
	id: number;
	tenant_name: string;
	tenant_phone: string;
	rent_pesewas: number;
	pay_every_months: number;
	start_date: string;
	end_date: string;
	next_due_date: string;
	status: 'active' | 'ended';
	from_afe: boolean;
	tenant_on_afe: boolean;
	landlord_name: string;
	home: string;
}

export interface RentalDetail {
	rental: Rental;
	role: 'landlord' | 'tenant';
	payments: { id: number; receipt_no: string; amount_pesewas: number; paid_on: string; method: string; covers_months: number; note: string }[];
	maintenance: { id: number; title: string; details: string; status: 'open' | 'in_progress' | 'done'; landlord_note: string; created_at: string; has_photo: boolean }[];
	agreements: { id: number; body: string; body_hash: string; landlord_signed_name: string; landlord_signed_at: string | null; tenant_signed_name: string; tenant_signed_at: string | null }[];
	renewals: { id: number; new_end_date: string; new_rent_pesewas: number; advance_months: number; status: 'offered' | 'accepted' | 'declined' }[];
}

export interface PlanInfo {
	plan: 'free' | 'standard' | 'pro';
	label: string;
	limit: number;
	used: number;
	period_end: string | null;
	prices: Record<string, number>;
	launch_offer: boolean;
}
