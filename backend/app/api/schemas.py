"""Request and response shapes for /api/v1. The frontend's TypeScript types mirror these
(frontend/src/lib/api/types.ts); /api/openapi.json is the source of truth."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.ghana import format_ghs
from app.modules.media.storage import storage


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Accounts and sign-in ----------------------------------------------------------------------


class UserOut(Out):
    id: int
    username: str
    display_name: str
    name: str
    role: str
    role_label: str
    phone: str | None
    email: str | None
    whatsapp_opt_in: bool
    mfa_enabled: bool = False
    has_password: bool = False
    privacy_current: bool = True
    is_active: bool = True

    @classmethod
    def of(cls, user) -> "UserOut":
        out = cls.model_validate(user)
        out.mfa_enabled = user.totp_enabled_at is not None
        out.has_password = bool(user.password_hash)
        from app.modules.accounts.privacy import NOTICE_VERSION

        out.privacy_current = user.privacy_version == NOTICE_VERSION
        return out


class CodeRequestIn(BaseModel):
    phone: str = Field(examples=["024 412 3456"])
    purpose: str = Field(pattern="^(login|signup)$")
    channel: str = Field(default="sms", pattern="^(sms|whatsapp)$")


class SignUpIn(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)
    display_name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(renter|landlord|agent)$")
    accept_privacy: bool = False


class CodeSignInIn(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)


class PasswordSignInIn(BaseModel):
    login: str
    password: str


class MfaIn(BaseModel):
    mfa_token: str
    code: str


class RefreshIn(BaseModel):
    refresh_token: str


class SignInOut(BaseModel):
    """status is signed_in (tokens included), mfa_required (send the authenticator code with
    mfa_token), or mfa_setup (add totp_secret to an authenticator app, then send a code)."""

    status: str
    user: UserOut
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int = 0
    mfa_token: str = ""
    otpauth_uri: str = ""
    totp_secret: str = ""

    @classmethod
    def of(cls, result) -> "SignInOut":
        return cls(
            status=result.status,
            user=UserOut.of(result.user),
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            expires_in=result.expires_in,
            mfa_token=result.mfa_token,
            otpauth_uri=result.otpauth_uri,
            totp_secret=result.totp_secret,
        )


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    whatsapp_opt_in: bool | None = None


class DeviceOut(Out):
    id: int
    device: str
    created_at: datetime


class VerificationStatusOut(BaseModel):
    verified: bool
    expires_at: datetime | None = None
    latest_decision: str | None = None
    identity_check: str | None = None  # passed | failed | None


class MeOut(BaseModel):
    user: UserOut
    verification: VerificationStatusOut | None = None
    unread_notifications: int


class NotificationOut(Out):
    id: int
    title: str
    body: str
    link: str
    created_at: datetime
    read_at: datetime | None


# --- Identity, areas, homes ----------------------------------------------------------------------------


class IdentityCheckOut(Out):
    id: int
    status: str
    masked_card: str
    name_on_card: str
    name_matches: bool
    liveness_passed: bool
    failure_reason: str
    provider: str
    created_at: datetime


class AreaOut(Out):
    id: int
    slug: str
    name: str
    city: str
    country: str
    boundary: list


class UnitIn(BaseModel):
    area_slug: str
    digital_address: str = Field(examples=["GA-492-7424"])
    unit_label: str = "Whole property"
    lat: Decimal
    lng: Decimal
    property_type: str = Field(examples=["apartment"])
    bedrooms: int = Field(ge=0, le=20)
    bathrooms: int = Field(default=1, ge=0, le=20)
    landmark: str = Field(default="", max_length=160)


class UnitOut(Out):
    id: int
    digital_address: str
    unit_label: str
    lat: Decimal
    lng: Decimal
    property_type: str
    property_type_label: str
    bedrooms: int
    bathrooms: int
    landmark: str
    area: AreaOut


class AuthorityOut(Out):
    id: int
    unit_id: int
    party_id: int
    relationship_type: str
    relationship_label: str
    document_type: str
    document_label: str
    utility_reference: str
    status: str
    review_note: str
    owner_name: str
    owner_confirmed_at: datetime | None
    created_at: datetime


class PaymentOut(Out):
    reference: str
    purpose: str
    unit_id: int | None
    amount_pesewas: int
    amount_display: str = ""
    status: str
    checkout_url: str
    note: str
    created_at: datetime
    paid_at: datetime | None
    listing_id: int | None = None
    subject: str = ""  # what it paid for: "GA-543-2210 · Flat 3" or "AFE-3T55X3 · <title>"

    @classmethod
    def of(cls, payment) -> "PaymentOut":
        out = cls.model_validate(payment)
        out.amount_display = format_ghs(payment.amount_pesewas)
        return out


# --- Visits ----------------------------------------------------------------------------------------------------


class VisitStartIn(BaseModel):
    unit_id: int
    lat: Decimal
    lng: Decimal


class AssignIn(BaseModel):
    verifier_id: int
    scheduled_for: date
    note: str = Field(default="", max_length=300)


class AssignmentOut(BaseModel):
    id: int
    status: str
    scheduled_for: date
    note: str
    verifier_id: int
    verifier_name: str
    unit: UnitOut
    landlord_name: str
    landlord_phone: str | None
    purpose: str = "verification"  # or "qa_recheck": an unannounced second visit

    @classmethod
    def of(cls, a) -> "AssignmentOut":
        return cls(
            id=a.id,
            status=a.status,
            purpose=a.purpose or "verification",
            scheduled_for=a.scheduled_for,
            note=a.note,
            verifier_id=a.verifier_id,
            verifier_name=a.verifier.name,
            unit=UnitOut.model_validate(a.unit),
            landlord_name=a.unit.registered_by.name,
            landlord_phone=a.unit.registered_by.phone,
        )


class VisitCompleteIn(BaseModel):
    checklist: dict[str, bool]
    notes: str = Field(default="", max_length=2000)
    travel_minutes: int | None = Field(default=None, ge=0, le=600)
    transport_ghs: float | None = Field(default=None, ge=0, le=2000)
    # The verifier's own verdict. Left out, the checklist decides (every item ticked = pass).
    result: str | None = Field(default=None, pattern="^(pass|fail)$")
    fail_reason: str | None = None


class PhotoOut(BaseModel):
    id: int
    url: str
    width: int
    height: int
    caption: str
    taken_at: datetime
    duplicate_of_id: int | None = None

    @classmethod
    def of(cls, photo) -> "PhotoOut":
        return cls(
            id=photo.id,
            url=storage.public_url(photo.image_key),
            width=photo.width,
            height=photo.height,
            caption=photo.caption,
            taken_at=photo.taken_at,
            duplicate_of_id=photo.duplicate_of_id,
        )


class VisitOut(Out):
    id: int
    unit_id: int
    outcome: str
    started_at: datetime
    completed_at: datetime | None
    checklist: dict
    notes: str


class VisitDetailOut(VisitOut):
    unit: UnitOut
    verifier_name: str
    checkin_distance_m: float
    photos: list[PhotoOut]
    checklist_items: dict[str, str]
    captions: list[str]
    min_photos: int
    radius_m: int

    @classmethod
    def of(cls, visit, checklist_items, captions, min_photos, radius_m) -> "VisitDetailOut":
        return cls(
            **VisitOut.model_validate(visit).model_dump(),
            unit=UnitOut.model_validate(visit.unit),
            verifier_name=visit.verifier.name,
            checkin_distance_m=round(visit.checkin_distance_m, 1),
            photos=[PhotoOut.of(p) for p in visit.photos],
            checklist_items=checklist_items,
            captions=captions,
            min_photos=min_photos,
            radius_m=radius_m,
        )


class WorklistOut(BaseModel):
    assignments: list[AssignmentOut]
    in_progress: list[VisitOut]
    radius_m: int


# --- Review ---------------------------------------------------------------------------------------------------------


class DecisionIn(BaseModel):
    approve: bool
    reason_codes: list[str]
    note: str = Field(default="", max_length=300)


class RevokeIn(BaseModel):
    reason_codes: list[str]
    note: str = Field(default="", max_length=300)


class AuthorityReviewIn(BaseModel):
    accept: bool
    note: str = Field(default="", max_length=300)


class OwnerConfirmIn(BaseModel):
    owner_phone: str
    owner_name: str = Field(min_length=2, max_length=160)


class FlagResolveIn(BaseModel):
    confirmed_fraud: bool
    note: str = Field(min_length=3, max_length=300)


class WaiverIn(BaseModel):
    note: str = Field(min_length=3, max_length=300)


class VerificationOut(Out):
    id: int
    party_id: int | None
    unit_id: int | None
    status: str
    reason_codes: list[str]
    note: str
    decided_at: datetime
    expires_at: datetime | None
    decided_by_name: str = ""

    @classmethod
    def of(cls, v) -> "VerificationOut":
        out = cls.model_validate(v)
        out.decided_by_name = v.decided_by.name
        return out


class FlagOut(Out):
    id: int
    subject_type: str
    subject_id: str
    rule: str
    severity: str
    explanation: str
    status: str
    created_at: datetime


class ReasonCodeOut(BaseModel):
    code: str
    label: str
    approval: bool


class ReviewModerationOut(BaseModel):
    """A tenant's review as a reviewer sees it: with whether it's hidden from renters."""

    id: int
    rating: int
    body: str
    author_name: str
    listing_reference: str
    created_at: datetime
    hidden: bool


class PersonReviewOut(BaseModel):
    user: UserOut
    identity: IdentityCheckOut | None
    current: VerificationOut | None
    history: list[VerificationOut]
    flags: list[FlagOut]
    model_notes: list["ModelNoteOut"] = []
    links: list["LinkOut"] = []
    reviews: list[ReviewModerationOut] = []


class HomeReviewOut(BaseModel):
    unit: UnitOut
    registered_by: UserOut
    authorities: list[AuthorityOut]
    visit: VisitDetailOut | None
    current: VerificationOut | None
    history: list[VerificationOut]
    flags: list[FlagOut]
    fee_settled: bool
    open_assignment: AssignmentOut | None
    model_notes: list["ModelNoteOut"] = []


class QueuePersonOut(BaseModel):
    id: int
    name: str
    role: str
    phone: str | None
    last_check: datetime


class QueueHomeOut(BaseModel):
    id: int
    address: str
    area: str
    landlord: str
    last_visit: datetime | None = None


# --- Listings ------------------------------------------------------------------------------------------------------


class ListingIn(BaseModel):
    unit_id: int
    title: str = Field(min_length=5, max_length=90)
    description: str = Field(min_length=20, max_length=5000)
    rent_ghs: Decimal = Field(gt=0, description="Monthly rent in cedis")
    advance_months: int = Field(ge=0, le=24)
    min_lease_months: int = Field(default=12, ge=1, le=60)
    available_from: date


class ListingUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=90)
    description: str | None = Field(default=None, min_length=20, max_length=5000)
    rent_ghs: Decimal | None = Field(default=None, gt=0)
    advance_months: int | None = Field(default=None, ge=0, le=24)
    min_lease_months: int | None = Field(default=None, ge=1, le=60)
    available_from: date | None = None


MAP_GRID = 0.005  # degrees; about 550 m in Accra


def _approx(value) -> float | None:
    return None if value is None else round(round(float(value) / MAP_GRID) * MAP_GRID, 4)


class ListingOut(Out):
    id: int
    reference: str
    title: str
    rent_pesewas: int
    rent_display: str
    advance_months: int
    advance_total_display: str = ""
    min_lease_months: int
    available_from: date
    status: str
    status_reason: str
    published_at: datetime | None
    bedrooms: int
    property_type_label: str = ""
    area: str
    area_slug: str = ""
    cover_url: str | None = None
    featured: bool = False
    # Approximate position only (snapped to a ~550 m grid): the exact address is shared after a
    # viewing is booked, so a public map can't be used to find an empty home.
    approx_lat: float | None = None
    approx_lng: float | None = None

    @classmethod
    def of(cls, listing, cover=None, **extra):
        fields = (
            "id",
            "reference",
            "title",
            "rent_pesewas",
            "rent_display",
            "advance_months",
            "min_lease_months",
            "available_from",
            "status",
            "status_reason",
            "published_at",
        )
        return cls(
            **{k: getattr(listing, k) for k in fields},
            advance_total_display=format_ghs(listing.advance_total_pesewas),
            bedrooms=listing.unit.bedrooms,
            property_type_label=listing.unit.property_type_label,
            area=listing.unit.area.name,
            area_slug=listing.unit.area.slug,
            cover_url=storage.public_url(cover.image_key) if cover else None,
            approx_lat=_approx(listing.unit.lat),
            approx_lng=_approx(listing.unit.lng),
            **extra,
        )


class PanelLineOut(BaseModel):
    text: str
    date: datetime


class ListingDetailOut(ListingOut):
    description: str
    lister_name: str
    lister_role: str
    city: str
    photos: list[PhotoOut]
    verification: list[PanelLineOut]
    saved: bool = False
    landlord_rating: float | None = None
    landlord_review_count: int = 0
    reviews: list["ReviewOut"] = []
    featured_until: datetime | None = None
    tenancy_available: bool = False


class MyUnitOut(BaseModel):
    """A landlord's home and where it is in the verification journey."""

    unit: UnitOut
    stage: str  # documents | fee | visit | review | verified | rejected
    authorities: list[AuthorityOut]
    fee_required: bool
    fee_settled: bool
    visit_scheduled_for: date | None
    latest_visit_outcome: str | None
    verification: VerificationOut | None
    listings: list[ListingOut]


# --- Messages and viewings -----------------------------------------------------------------------------------------


class EnquiryIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: int
    sender: str
    mine: bool
    system: bool
    body: str
    warning: str
    created_at: datetime


class ThreadOut(BaseModel):
    id: int
    listing_reference: str
    listing_title: str
    other_name: str
    role: str  # renter | lister: the signed-in person's side
    last_message_at: datetime
    unread: bool


class ViewingIn(BaseModel):
    when: datetime = Field(description="ISO 8601 with timezone")
    note: str = Field(default="", max_length=300)


class ViewingRespondIn(BaseModel):
    confirm: bool
    note: str = Field(default="", max_length=300)


class ViewingCompleteIn(BaseModel):
    attended: bool


class ViewingOut(BaseModel):
    id: int
    listing_reference: str
    listing_title: str
    other_name: str
    role: str
    requested_for: datetime
    status: str
    note: str
    response_note: str
    thread_id: int
    outcome: str | None = None


class ThreadDetailOut(ThreadOut):
    messages: list[MessageOut]
    viewings: list[ViewingOut]


# --- Check before you pay, events -------------------------------------------------------------------------------------


class CheckOut(BaseModel):
    verified: bool
    headline: str
    details: list[str]
    advice: list[str]
    listings: list[ListingOut]


class ReportIn(BaseModel):
    what_happened: str = Field(min_length=10, max_length=4000)
    reported_phone: str = ""
    reported_reference: str = ""
    amount_lost_ghs: Decimal | None = Field(default=None, ge=0)
    reporter_contact: str = Field(default="", max_length=120)


class EventIn(BaseModel):
    name: str
    anonymous_id: str = Field(default="", max_length=64)
    path: str = Field(default="", max_length=300)
    props: dict = {}


# --- Phase 2: protected payments -------------------------------------------------------------------


class PayeeIn(BaseModel):
    channel: str = Field(pattern="^(momo_mtn|momo_telecel|momo_at|bank)$")
    account_number: str = Field(min_length=9, max_length=24)
    code: str = Field(default="", max_length=7, description="Fresh authenticator code")


class PayeeOut(Out):
    id: int
    channel: str
    masked: str
    account_name: str
    status: str
    usable_from: datetime


class OfferIn(BaseModel):
    viewing_id: int
    move_in_date: date
    lease_months: int = Field(ge=1, le=60)
    advance_months: int = Field(ge=0, le=24)
    deposit_months: int = Field(ge=0, le=12)


class QuoteOut(BaseModel):
    held_pesewas: int
    fee_pesewas: int
    fee_payer: str
    charge_pesewas: int
    payout_pesewas: int
    held_display: str
    fee_display: str
    charge_display: str
    payout_display: str
    advance_cap_months: int


class DisputeIn(BaseModel):
    reason: str
    details: str = Field(min_length=20, max_length=4000)


class DisputeDecisionIn(BaseModel):
    decision: str = Field(pattern="^(release|refund)$")
    note: str = Field(min_length=10, max_length=500)


class EvidenceIn(BaseModel):
    note: str = Field(min_length=10, max_length=2000)


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=20, max_length=2000)


class ReviewOut(BaseModel):
    id: int
    rating: int
    body: str
    author_name: str
    created_at: datetime


class DisputeOut(BaseModel):
    id: int
    tenancy_reference: str
    reason: str
    reason_label: str
    details: str
    status: str
    decision: str
    decision_note: str
    opened_by_name: str
    created_at: datetime
    decided_at: datetime | None


class TenancyOut(BaseModel):
    reference: str
    status: str
    role: str  # tenant | landlord | reviewer
    actions: list[str]
    listing_reference: str
    listing_title: str
    address: str
    area: str
    landlord_name: str
    tenant_name: str
    rent_display: str
    advance_months: int
    deposit_months: int
    lease_months: int
    move_in_date: date
    held_display: str
    held_pesewas: int = 0
    fee_display: str
    fee_pesewas: int = 0
    fee_payer: str
    charge_display: str
    payout_display: str
    payout_pesewas: int = 0
    charge_pesewas: int
    offer_expires_at: datetime
    checkout_url: str
    accepted_at: datetime | None
    funded_at: datetime | None
    tenant_confirmed_at: datetime | None
    landlord_evidence_at: datetime | None
    landlord_evidence: str
    closed_at: datetime | None
    close_reason: str
    has_agreement: bool
    has_receipt: bool = False
    has_move_in_photo: bool = False
    payee: str
    dispute: DisputeOut | None = None
    review: ReviewOut | None = None


class RulePendingOut(BaseModel):
    id: int
    value: object
    version: int
    source: str
    proposed_by_name: str
    proposed_at: datetime


class RuleOut(BaseModel):
    key: str
    label: str
    value: object
    version: int
    source: str
    pending: list[RulePendingOut]


class RuleProposeIn(BaseModel):
    key: str
    value: object
    source: str = Field(min_length=5, max_length=300)


# --- Phase 3: detection ------------------------------------------------------------------------------


class ModelNoteOut(BaseModel):
    """A model's score shown to a reviewer. In shadow it is information only."""

    detector: str
    label: str
    subject: str
    version: str
    score: int
    threshold: int
    reasons: list[str]
    mode: str
    acted: bool
    created_at: datetime


class LinkOut(BaseModel):
    other_user_id: int
    other_name: str
    kind: str
    evidence: str


class TallyOut(BaseModel):
    tp: int
    fp: int
    fn: int
    tn: int
    flagged: int
    precision: float | None
    recall: float | None


class EvaluationOut(BaseModel):
    version: str | None
    labels: int
    fraud: int
    model: TallyOut
    rules: TallyOut
    promotable: bool
    reason: str


class DetectorOut(BaseModel):
    name: str
    label: str
    mode: str
    threshold: int
    version: str | None
    scores: int
    acted: int
    pending: int
    failed: int
    evaluation: EvaluationOut


class SeededOut(BaseModel):
    cases: int
    fraud: int
    skipped: int
    model: TallyOut
    rules: TallyOut
    missed: list[str]


class SnapshotOut(Out):
    detector: str
    week: str
    version: str | None
    labels: int
    fraud: int
    model: TallyOut
    rules: TallyOut
    promotable: bool
    reason: str
    seeded: SeededOut | None
    created_at: datetime


class CopilotNumbersOut(BaseModel):
    level: str
    days: int
    runs: int
    done: int
    failed: int
    refused: int
    too_late: int
    decided: int
    agreement: float | None
    false_approvals: int
    code_overlap: float | None
    cost_usd: float


class ModelVersionOut(Out):
    detector: str
    version: str
    trained_on: int
    notes: str
    created_at: datetime


class ReportOut(Out):
    id: int
    created_at: datetime
    channel: str
    reported_phone: str
    reported_reference: str
    what_happened: str
    amount_lost_pesewas: int | None
    status: str
    matched_user_id: int | None = None
    matched_user_name: str = ""
    matched_listing_title: str = ""


class ReportDecisionIn(BaseModel):
    upheld: bool
    note: str = Field(min_length=10, max_length=300)


# --- Data rights and staff -------------------------------------------------------------------------


class CloseAccountIn(BaseModel):
    confirm: str = Field(max_length=10, description='Type "DELETE"')
    password: str = Field(default="", max_length=200)
    code: str = Field(default="", max_length=7)


class StaffOut(UserOut):
    is_active: bool
    created_at: datetime


class StaffIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    phone: str = Field(min_length=9, max_length=20)
    role: str = Field(pattern="^(field_verifier|reviewer|admin)$")


class StaffRoleIn(BaseModel):
    role: str = Field(pattern="^(field_verifier|reviewer|admin)$")


class StaffActiveIn(BaseModel):
    active: bool


class SuspendIn(BaseModel):
    active: bool
    reason: str = Field(default="", max_length=500)


# --- Renter growth ---------------------------------------------------------------------------------


class SavedSearchIn(BaseModel):
    area_slug: str | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=3)
    max_rent_ghs: int | None = Field(default=None, ge=50, le=200_000)
    channel: str = Field(default="", pattern="^(|sms|whatsapp|in_app)$")


class SavedSearchOut(BaseModel):
    id: int
    description: str
    area_slug: str | None
    bedrooms: int | None
    max_rent_pesewas: int | None
    channel: str
    alerts_sent: int
    created_at: datetime


class RentRangeOut(BaseModel):
    bedrooms: int
    low: int
    median: int
    high: int
    count: int
    source: str  # "afe" (verified listings) or "survey"


class AreaOverviewOut(BaseModel):
    area: AreaOut
    live: int
    ranges: list[RentRangeOut]
    listings: list[ListingOut]


# --- Trust and safety operations ----------------------------------------------------------------


class AppealIn(BaseModel):
    kind: str = Field(pattern="^(verification|listing|report)$")
    subject_id: int
    reason: str = Field(min_length=30, max_length=4000)


class AppealOut(Out):
    id: int
    kind: str
    subject_id: int
    reason: str
    status: str
    outcome: str
    created_at: datetime
    decided_at: datetime | None
    appellant_name: str = ""


class AppealableOut(BaseModel):
    kind: str
    subject_id: int
    label: str
    date: datetime | None


class AppealDecisionIn(BaseModel):
    upheld: bool
    outcome: str = Field(min_length=20, max_length=500)


class RouteStopOut(BaseModel):
    unit_id: int
    address: str
    landlord: str
    lat: float
    lng: float


class RouteOut(BaseModel):
    verifier_id: int
    verifier_name: str
    area: str
    km: float
    stops: list[RouteStopOut]


class VisitPlanOut(BaseModel):
    day: date
    per_verifier: int
    routes: list[RouteOut]
    unplanned: list[RouteStopOut]


class AssignRouteIn(BaseModel):
    verifier_id: int
    unit_ids: list[int] = Field(min_length=1, max_length=12)
    day: date


class LabelCheckOut(BaseModel):
    id: int
    subject: str
    outcome: str
    source: str
    reasons: list[str]
    decided_at: datetime


class LabelCheckIn(BaseModel):
    agree: bool
    note: str = Field(default="", max_length=300)


# --- Insights ----------------------------------------------------------------------------------------


class ViewingOutcomeIn(BaseModel):
    answer: str = Field(pattern="^(rented_through_afe|paid_directly|not_renting|still_deciding)$")


class TargetOut(BaseModel):
    name: str
    value: float | int | None
    target: str
    met: bool | None
    note: str



class AreaIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    slug: str = Field(min_length=3, max_length=60)
    city: str = Field(default="Accra", max_length=80)
    boundary: list[list[float]]


class PriceSurveyRow(BaseModel):
    bedrooms: int = Field(ge=0, le=3)
    low_ghs: int = Field(gt=0)
    median_ghs: int = Field(gt=0)
    high_ghs: int = Field(gt=0)


class AreaAdminOut(AreaOut):
    is_active: bool
    missing: list[str] = []
    surveyed_sizes: list[int] = []


class AreaOpenIn(BaseModel):
    open: bool


# --- Landlord and agent tools (workstream G) -------------------------------------------------------


class RentalIn(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=120)
    tenant_phone: str = Field(default="", max_length=20)
    rent_ghs: int = Field(gt=0, le=200_000)
    pay_every_months: int = Field(ge=1, le=24)
    start_date: date
    end_date: date
    unit_id: int | None = None


class RentalOut(Out):
    id: int
    tenant_name: str
    tenant_phone: str
    rent_pesewas: int
    pay_every_months: int
    start_date: date
    end_date: date
    next_due_date: date
    status: str
    from_afe: bool = False
    tenant_on_afe: bool = False
    landlord_name: str = ""
    home: str = ""


class RentPaymentIn(BaseModel):
    amount_ghs: float = Field(gt=0, le=2_000_000)
    paid_on: date
    method: str = Field(pattern="^(momo|bank|cash)$")
    covers_months: int = Field(ge=1, le=24)
    note: str = Field(default="", max_length=300)


class RentPaymentOut(Out):
    id: int
    receipt_no: str
    amount_pesewas: int
    paid_on: date
    method: str
    covers_months: int
    note: str


class MaintenanceOut(Out):
    id: int
    title: str
    details: str
    status: str
    landlord_note: str
    created_at: datetime
    has_photo: bool = False


class MaintenanceStatusIn(BaseModel):
    status: str = Field(pattern="^(open|in_progress|done)$")
    note: str = Field(default="", max_length=500)


class AgreementOut(Out):
    id: int
    body: str
    body_hash: str
    landlord_signed_name: str
    landlord_signed_at: datetime | None
    tenant_signed_name: str
    tenant_signed_at: datetime | None


class SignIn(BaseModel):
    typed_name: str = Field(min_length=2, max_length=120)


class RenewalIn(BaseModel):
    new_end_date: date
    new_rent_ghs: int = Field(gt=0, le=200_000)
    advance_months: int = Field(ge=0, le=24)


class RenewalOut(Out):
    id: int
    new_end_date: date
    new_rent_pesewas: int
    advance_months: int
    status: str


class RentalDetailOut(BaseModel):
    rental: RentalOut
    role: str
    payments: list[RentPaymentOut]
    maintenance: list[MaintenanceOut]
    agreements: list[AgreementOut]
    renewals: list[RenewalOut]


class PlanOut(BaseModel):
    plan: str
    label: str
    limit: int
    used: int
    period_end: date | None
    prices: dict[str, int]
    launch_offer: bool
