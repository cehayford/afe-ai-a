"""The verification procedure from the build plan (§5), as rules the code enforces."""

from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import NotAllowed, RuleViolation
from app.core.geo import coord, distance_m
from app.db import utcnow
from app.modules.accounts.models import LISTER_ROLES, Role, User
from app.modules.audit.log import record
from app.modules.billing.service import fee_pesewas, fee_settled
from app.modules.detection.hooks import FRAUD_CODES, enqueue, label
from app.modules.identity.models import CheckStatus, IdentityCheck
from app.modules.identity.service import latest_check
from app.modules.listings.models import Listing
from app.modules.media.images import hamming, process_photo
from app.modules.media.storage import storage
from app.modules.notifications.service import notify
from app.modules.risk.flags import open_flags, raise_flag
from app.modules.risk.models import Severity
from app.modules.units.models import AuthorityRecord, AuthorityStatus, Unit

from .models import (
    APPROVAL_CODES,
    CHECKLIST_ITEMS,
    REASON_LABELS,
    AssignmentStatus,
    FieldVisit,
    ReasonCode,
    Verification,
    VerificationStatus,
    VisitAssignment,
    VisitOutcome,
    VisitPhoto,
)

# Phones' clocks drift; allow this much either side when checking photo times.
CLOCK_SKEW = timedelta(minutes=2)

# --- Status ------------------------------------------------------------------------


def current_verification(db: Session, *, party=None, unit=None) -> Verification | None:
    """The latest decision wins: a rejected re-verification removes an earlier badge."""
    column = Verification.party_id if party is not None else Verification.unit_id
    subject_id = (party or unit).id
    latest = db.scalar(
        select(Verification)
        .where(column == subject_id)
        .order_by(Verification.decided_at.desc(), Verification.id.desc())
    )
    return latest if latest is not None and latest.is_current else None


def is_verified(db: Session, *, party=None, unit=None) -> bool:
    return current_verification(db, party=party, unit=unit) is not None


def decision_history(db: Session, *, party=None, unit=None, limit: int = 10) -> list[Verification]:
    column = Verification.party_id if party is not None else Verification.unit_id
    return list(
        db.scalars(
            select(Verification)
            .where(column == (party or unit).id)
            .order_by(Verification.decided_at.desc(), Verification.id.desc())
            .limit(limit)
        )
    )


def people_awaiting_decision(db: Session) -> list[tuple]:
    """Landlords and agents with a passed Ghana Card check newer than their last decision."""
    last_check = (
        select(func.max(IdentityCheck.created_at))
        .where(IdentityCheck.user_id == User.id, IdentityCheck.status == CheckStatus.PASSED)
        .correlate(User)
        .scalar_subquery()
    )
    last_decision = (
        select(func.max(Verification.decided_at))
        .where(Verification.party_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    return list(
        db.execute(
            select(User, last_check.label("last_check"))
            .where(User.role.in_([str(r) for r in LISTER_ROLES]), last_check.is_not(None))
            .where(or_(last_decision.is_(None), last_check > last_decision))
            .order_by(last_check)
        )
    )


def homes_awaiting_decision(db: Session) -> list[tuple]:
    """Homes with a completed field visit newer than their last decision."""
    last_visit = (
        select(func.max(FieldVisit.completed_at))
        .where(FieldVisit.unit_id == Unit.id, FieldVisit.outcome != VisitOutcome.IN_PROGRESS)
        .correlate(Unit)
        .scalar_subquery()
    )
    last_decision = (
        select(func.max(Verification.decided_at))
        .where(Verification.unit_id == Unit.id)
        .correlate(Unit)
        .scalar_subquery()
    )
    return list(
        db.execute(
            select(Unit, last_visit.label("last_visit"))
            .where(last_visit.is_not(None))
            .where(or_(last_decision.is_(None), last_visit > last_decision))
            .order_by(last_visit)
        )
    )


def latest_completed_visit(db: Session, unit) -> FieldVisit | None:
    return db.scalar(
        select(FieldVisit)
        .where(FieldVisit.unit_id == unit.id, FieldVisit.outcome != VisitOutcome.IN_PROGRESS)
        .order_by(FieldVisit.completed_at.desc(), FieldVisit.id.desc())
    )


# --- Field visits ---------------------------------------------------------------------


def _within_radius(unit: Unit, lat, lng) -> float:
    d = distance_m((float(lat), float(lng)), unit.point)
    if d > get_settings().field_visit_radius_m:
        raise RuleViolation(f"You are {d:.0f} m from the unit's pin. Go to the property to continue.")
    return d


def _has_interest(db: Session, person, unit: Unit) -> bool:
    """True if the person registered the home or has an authority record on it."""
    if unit.registered_by_id == person.id:
        return True
    return bool(
        db.scalar(
            select(func.count())
            .select_from(AuthorityRecord)
            .where(AuthorityRecord.unit_id == unit.id, AuthorityRecord.party_id == person.id)
        )
    )


def assign_visit(db: Session, unit: Unit, verifier, reviewer, scheduled_for: date, note: str = "") -> VisitAssignment:
    """Send a verifier to a home. Reviewers choose; verifiers never pick their own homes."""
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can assign visits.")
    if verifier.role != Role.FIELD_VERIFIER or not verifier.is_active:
        raise RuleViolation("Choose an active field verifier.")
    if not unit.area.is_active:
        raise RuleViolation(f"Afe is not open in {unit.area.name}.")
    if not fee_settled(db, unit):
        raise RuleViolation("The verification fee for this home is not paid or waived yet.")
    if _has_interest(db, verifier, unit):
        raise RuleViolation("A verifier cannot visit a home they own or let.")
    if open_assignment(db, unit):
        raise RuleViolation("This home already has an open visit assignment.")
    if get_settings().rotate_verifiers:
        last = db.scalar(
            select(FieldVisit)
            .join(Unit, FieldVisit.unit_id == Unit.id)
            .where(Unit.registered_by_id == unit.registered_by_id, FieldVisit.outcome != VisitOutcome.IN_PROGRESS)
            .order_by(FieldVisit.completed_at.desc(), FieldVisit.id.desc())
        )
        if last is not None and last.verifier_id == verifier.id:
            raise RuleViolation(f"{verifier.name} did the last visit for this landlord. Send a different verifier.")
    assignment = VisitAssignment(
        unit_id=unit.id, verifier_id=verifier.id, assigned_by_id=reviewer.id, scheduled_for=scheduled_for, note=note
    )
    db.add(assignment)
    db.flush()
    record(db, reviewer, "visit.assigned", assignment, verifier=verifier.id, scheduled_for=str(scheduled_for))
    notify(
        db,
        verifier,
        "visit_assigned",
        link=f"/field/assignments/{assignment.id}",
        unit=str(unit),
        when=scheduled_for.strftime("%a %d %b"),
    )
    return assignment


def cancel_assignment(db: Session, assignment: VisitAssignment, reviewer, note: str = "") -> VisitAssignment:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can cancel visits.")
    if assignment.status != AssignmentStatus.OPEN:
        raise RuleViolation("Only open assignments can be cancelled.")
    assignment.status = AssignmentStatus.CANCELLED
    db.flush()
    record(db, reviewer, "visit.assignment_cancelled", assignment, note=note)
    return assignment


def open_assignment(db: Session, unit: Unit, verifier=None) -> VisitAssignment | None:
    q = select(VisitAssignment).where(
        VisitAssignment.unit_id == unit.id, VisitAssignment.status == AssignmentStatus.OPEN
    )
    if verifier is not None:
        q = q.where(VisitAssignment.verifier_id == verifier.id)
    return db.scalar(q.order_by(VisitAssignment.id.desc()))


def open_assignments(db: Session) -> list[VisitAssignment]:
    return list(
        db.scalars(
            select(VisitAssignment)
            .where(VisitAssignment.status == AssignmentStatus.OPEN)
            .order_by(VisitAssignment.scheduled_for, VisitAssignment.id)
        )
    )


def verifier_worklist(db: Session, verifier) -> tuple[list[VisitAssignment], list[FieldVisit]]:
    """What a verifier sees on their phone: open assignments and visits in progress."""
    assignments = list(
        db.scalars(
            select(VisitAssignment)
            .where(VisitAssignment.verifier_id == verifier.id, VisitAssignment.status == AssignmentStatus.OPEN)
            .order_by(VisitAssignment.scheduled_for, VisitAssignment.id)
        )
    )
    in_progress = list(
        db.scalars(
            select(FieldVisit)
            .where(FieldVisit.verifier_id == verifier.id, FieldVisit.outcome == VisitOutcome.IN_PROGRESS)
            .order_by(FieldVisit.started_at)
        )
    )
    return assignments, in_progress


def homes_needing_visit(db: Session) -> list[Unit]:
    """Homes with an authority document on file, no open assignment, no visit in progress,
    and no passed visit recent enough to use for a decision."""
    cutoff = utcnow() - get_settings().field_visit_max_age
    has_authority = select(AuthorityRecord.id).where(
        AuthorityRecord.unit_id == Unit.id, AuthorityRecord.status != AuthorityStatus.REJECTED
    )
    has_open = select(VisitAssignment.id).where(
        VisitAssignment.unit_id == Unit.id, VisitAssignment.status == AssignmentStatus.OPEN
    )
    has_active_visit = select(FieldVisit.id).where(
        FieldVisit.unit_id == Unit.id,
        or_(
            FieldVisit.outcome == VisitOutcome.IN_PROGRESS,
            (FieldVisit.outcome == VisitOutcome.PASSED) & (FieldVisit.completed_at > cutoff),
        ),
    )
    candidates = db.scalars(
        select(Unit)
        .where(has_authority.exists(), ~has_open.exists(), ~has_active_visit.exists())
        .order_by(Unit.created_at, Unit.id)
    )
    # A verified home comes back only in its renewal window (30 days before expiry).
    renew_from = utcnow() + timedelta(days=30)
    return [
        u for u in candidates
        if fee_settled(db, u) and ((v := current_verification(db, unit=u)) is None or v.expires_at <= renew_from)
    ]


def can_visit(db: Session, verifier, unit: Unit) -> bool:
    """The rules assign_visit enforces about the person: no interest in the home, and not the
    verifier who did the last visit for this landlord (rotation)."""
    if _has_interest(db, verifier, unit):
        return False
    if not get_settings().rotate_verifiers:
        return True
    last = db.scalar(
        select(FieldVisit)
        .join(Unit, FieldVisit.unit_id == Unit.id)
        .where(Unit.registered_by_id == unit.registered_by_id, FieldVisit.outcome != VisitOutcome.IN_PROGRESS)
        .order_by(FieldVisit.completed_at.desc(), FieldVisit.id.desc())
    )
    return last is None or last.verifier_id != verifier.id


def homes_awaiting_fee(db: Session) -> list[Unit]:
    """Homes with documents on file whose verification fee is not settled yet."""
    if fee_pesewas(db) == 0:
        return []
    has_authority = select(AuthorityRecord.id).where(
        AuthorityRecord.unit_id == Unit.id, AuthorityRecord.status != AuthorityStatus.REJECTED
    )
    return [
        u for u in db.scalars(select(Unit).where(has_authority.exists()).order_by(Unit.id)) if not fee_settled(db, u)
    ]


def start_visit(db: Session, unit: Unit, verifier, lat, lng) -> FieldVisit:
    if verifier.role != Role.FIELD_VERIFIER:
        raise NotAllowed("Only field verifiers can start a visit.")
    assignment = open_assignment(db, unit, verifier)
    if assignment is None:
        raise RuleViolation("This home is not assigned to you. Ask a reviewer to assign it.")
    d = _within_radius(unit, lat, lng)
    ongoing = db.scalar(
        select(FieldVisit).where(
            FieldVisit.unit_id == unit.id,
            FieldVisit.verifier_id == verifier.id,
            FieldVisit.outcome == VisitOutcome.IN_PROGRESS,
        )
    )
    if ongoing:
        return ongoing  # a double tap or a retry resumes the same visit
    visit = FieldVisit(
        unit_id=unit.id,
        verifier_id=verifier.id,
        assignment_id=assignment.id,
        checkin_lat=coord(lat),
        checkin_lng=coord(lng),
    )
    db.add(visit)
    db.flush()
    record(db, verifier, "visit.started", visit, distance_m=round(d), assignment=assignment.id)
    return visit


def add_visit_photo(
    db: Session,
    visit: FieldVisit,
    verifier,
    raw: bytes,
    lat,
    lng,
    taken_at: datetime,
    caption: str = "",
    client_ref: str | None = None,
) -> VisitPhoto:
    """Photos are captured in the verifier app during the visit, at the property."""
    if visit.verifier_id != verifier.id:
        raise NotAllowed("Only the verifier on this visit can add photos.")
    if client_ref:
        already = db.scalar(
            select(VisitPhoto).where(VisitPhoto.visit_id == visit.id, VisitPhoto.client_ref == client_ref)
        )
        if already:
            return already  # the phone retried after a lost reply
    if visit.outcome != VisitOutcome.IN_PROGRESS:
        raise RuleViolation("This visit is finished. Start a new visit to add photos.")
    if not (visit.started_at - CLOCK_SKEW <= taken_at <= utcnow() + CLOCK_SKEW):
        raise RuleViolation("Photo time is outside this visit.")
    _within_radius(visit.unit, lat, lng)

    processed = process_photo(raw)
    match = _find_duplicate(db, processed.phash, exclude_unit_id=visit.unit_id)
    photo = VisitPhoto(
        visit_id=visit.id,
        client_ref=client_ref,
        image_key=storage.save("public", "units", processed.webp, ".webp"),
        width=processed.width,
        height=processed.height,
        caption=caption,
        taken_at=taken_at,
        lat=coord(lat),
        lng=coord(lng),
        phash=processed.phash,
        dhash=processed.dhash,
        duplicate_of_id=match.id if match else None,
    )
    db.add(photo)
    db.flush()
    if match:
        raise_flag(
            db,
            visit.unit,
            rule="photos.duplicate_of_other_unit",
            severity=Severity.HIGH,
            explanation=f"A visit photo matches a photo of another property ({match.visit.unit}).",
            photo=photo.id,
            matched_photo=match.id,
            matched_unit=match.visit.unit_id,
        )
    record(db, verifier, "visit.photo_added", photo, duplicate_of=match.id if match else None)
    return photo


def _find_duplicate(db: Session, phash: str, exclude_unit_id: int) -> VisitPhoto | None:
    # A linear scan is fine at hundreds of homes. Past ~50,000 photos, move to a BK-tree
    # or an index in the database.
    limit = get_settings().photo_duplicate_distance
    rows = db.execute(
        select(VisitPhoto.id, VisitPhoto.phash).join(FieldVisit).where(FieldVisit.unit_id != exclude_unit_id)
    )
    for photo_id, other_hash in rows:
        if hamming(phash, other_hash) <= limit:
            return db.get(VisitPhoto, photo_id)
    return None


def complete_visit(
    db: Session, visit: FieldVisit, verifier, checklist: dict, notes: str = "",
    travel_minutes: int | None = None, transport_pesewas: int | None = None,
    result: str | None = None, fail_reason: str | None = None,
) -> FieldVisit:
    """A visit passes only when every check is ticked and there are enough photos. The verifier can
    also fail a visit whose checks all passed (their judgement on the day), with a reason code."""
    if visit.verifier_id != verifier.id:
        raise NotAllowed("Only the verifier on this visit can complete it.")
    if visit.outcome != VisitOutcome.IN_PROGRESS:
        raise RuleViolation("This visit is already complete.")
    unknown = set(checklist) - set(CHECKLIST_ITEMS)
    if unknown:
        raise RuleViolation(f"Unknown checklist items: {', '.join(sorted(unknown))}")

    all_ticked = all(checklist.get(item) is True for item in CHECKLIST_ITEMS)
    if result == "pass" and not all_ticked:
        raise RuleViolation("A visit can pass only when every check is yes.")
    passed = all_ticked and result != "fail"
    minimum = get_settings().min_visit_photos
    photo_count = db.scalar(select(func.count()).select_from(VisitPhoto).where(VisitPhoto.visit_id == visit.id))
    if passed and photo_count < minimum:
        raise RuleViolation(f"Take at least {minimum} photos before passing the visit.")
    if fail_reason:
        if passed:
            raise RuleViolation("A reason goes with a failed visit only.")
        if fail_reason not in ReasonCode.__members__ or ReasonCode(fail_reason) in APPROVAL_CODES:
            raise RuleViolation("Choose a reason from the list.")
        notes = f"Fail reason: {fail_reason} ({REASON_LABELS[ReasonCode(fail_reason)]}). {notes}".strip()[:2000]

    visit.checklist = checklist
    visit.notes = notes
    visit.travel_minutes, visit.transport_pesewas = travel_minutes, transport_pesewas
    visit.completed_at = utcnow()
    visit.outcome = VisitOutcome.PASSED if passed else VisitOutcome.FAILED
    if visit.assignment_id:
        assignment = db.get(VisitAssignment, visit.assignment_id)
        if assignment.status == AssignmentStatus.OPEN:
            assignment.status = AssignmentStatus.DONE
    db.flush()
    record(db, verifier, "visit.completed", visit, outcome=visit.outcome, checklist=checklist)
    if visit.assignment_id and assignment.purpose == "qa_recheck":
        _recheck_result(db, visit, assignment)
    enqueue(db, "photos", visit.unit)
    from app.modules.agents.service import on_visit_completed  # agents reads verification, so imported here

    on_visit_completed(db, visit.unit, visit)
    return visit


# --- Decisions ----------------------------------------------------------------------


def _validate_codes(approve: bool, codes: list[str], note: str) -> list[str]:
    if not codes:
        raise RuleViolation("Choose at least one reason code.")
    bad = [c for c in codes if c not in ReasonCode.__members__.values()]
    if bad:
        raise RuleViolation(f"Unknown reason codes: {', '.join(bad)}")
    if approve and any(c not in APPROVAL_CODES for c in codes):
        raise RuleViolation("Use approval codes when approving.")
    if not approve and any(c in APPROVAL_CODES for c in codes):
        raise RuleViolation("Use rejection codes when rejecting.")
    if ReasonCode.OTHER in codes and not note:
        raise RuleViolation("Add a note when using the OTHER reason code.")
    return list(dict.fromkeys(codes))


def _require_no_high_flags(db: Session, subject):
    flags = open_flags(db, subject, min_severity=Severity.HIGH)
    if flags:
        raise RuleViolation("Resolve open high-severity flags first.", reasons=[f.explanation for f in flags])


def _require_reviewer(user):
    if not user.can_review:
        raise NotAllowed("Only reviewers can decide verifications.")


def decide_party(db: Session, party, reviewer, approve: bool, reason_codes: list[str], note: str = "") -> Verification:
    """Verify a landlord or agent's identity (plan §5, step 1)."""
    _require_reviewer(reviewer)
    if reviewer.id == party.id:
        raise RuleViolation("You cannot verify yourself.")
    codes = _validate_codes(approve, reason_codes, note)

    check = latest_check(db, party, passed_only=True)
    if approve:
        if not party.is_lister:
            raise RuleViolation("Only landlords and agents are verified.")
        if check is None:
            raise RuleViolation("There is no passed Ghana Card check for this person.")
        if not check.liveness_passed:
            raise RuleViolation("The Ghana Card check has no selfie liveness result.")
        _require_no_high_flags(db, party)

    now = utcnow()
    verification = Verification(
        party_id=party.id,
        status=VerificationStatus.APPROVED if approve else VerificationStatus.REJECTED,
        reason_codes=codes,
        note=note,
        identity_check_id=check.id if check else None,
        decided_by_id=reviewer.id,
        decided_at=now,
        expires_at=now + get_settings().verification_valid_for if approve else None,
    )
    db.add(verification)
    db.flush()
    record(db, reviewer, "verification.party_decided", verification, status=verification.status, codes=codes)
    _label_decision(db, party, reviewer, approve, codes, verification)
    notify(db, party, "party_verified" if approve else "party_rejected", link="/landlord")
    return verification


def _label_decision(db: Session, subject, reviewer, approve: bool, codes: list[str], verification) -> None:
    """Approvals are genuine examples; rejections count as fraud only for deception reasons,
    not for missing paperwork (build plan §7: every decision is a label)."""
    if approve or FRAUD_CODES & set(codes):
        label(db, subject, fraud=not approve, source="verification", decided_by=reviewer, reasons=codes,
              source_id=verification.id)


def decide_unit(
    db: Session, unit: Unit, reviewer, approve: bool, reason_codes: list[str], note: str = ""
) -> Verification:
    """Verify a home: authority accepted and a recent passed visit by someone else (plan §5)."""
    _require_reviewer(reviewer)
    codes = _validate_codes(approve, reason_codes, note)
    accepted = list(
        db.scalars(
            select(AuthorityRecord.id).where(
                AuthorityRecord.unit_id == unit.id, AuthorityRecord.status == AuthorityStatus.ACCEPTED
            )
        )
    )

    visit = latest_completed_visit(db, unit)
    if approve:
        if not unit.area.is_active:
            raise RuleViolation(f"Afe is not open in {unit.area.name}.")
        if not accepted:
            raise RuleViolation("No accepted ownership or authority document for this unit.")
        if visit is None or visit.outcome != VisitOutcome.PASSED:
            raise RuleViolation("The latest field visit did not pass.")
        if utcnow() - visit.completed_at > get_settings().field_visit_max_age:
            raise RuleViolation("The latest field visit is too old. Schedule a new one.")
        if visit.verifier_id == reviewer.id:
            raise RuleViolation("The verifier who visited cannot also approve the unit.")
        _require_no_high_flags(db, unit)

    now = utcnow()
    verification = Verification(
        unit_id=unit.id,
        status=VerificationStatus.APPROVED if approve else VerificationStatus.REJECTED,
        reason_codes=codes,
        note=note,
        field_visit_id=visit.id if visit else None,
        evidence={"authority_records": accepted},
        decided_by_id=reviewer.id,
        decided_at=now,
        expires_at=now + get_settings().verification_valid_for if approve else None,
    )
    db.add(verification)
    db.flush()
    record(db, reviewer, "verification.unit_decided", verification, status=verification.status, codes=codes)
    _label_decision(db, unit, reviewer, approve, codes, verification)
    from app.modules.agents.service import on_unit_decided  # agents reads verification, so imported here

    on_unit_decided(db, verification)
    if not approve and FRAUD_CODES & set(codes):
        # The home was a deception: its listings and any documents behind it are fraud examples too.
        for listing in db.scalars(select(Listing).where(Listing.unit_id == unit.id)):
            label(db, listing, fraud=True, source="verification", decided_by=reviewer, reasons=codes)
        if {"DOCS_SUSPECT", "OWNER_DENIES"} & set(codes):
            for authority in unit.authority_records:
                label(db, authority, fraud=True, source="verification", decided_by=reviewer, reasons=codes)
    if approve and visit is not None:
        _maybe_schedule_recheck(db, unit, visit, verification, reviewer)
    notify(
        db,
        unit.registered_by,
        "unit_verified" if approve else "unit_rejected",
        link=f"/landlord/homes/{unit.id}",
        unit=str(unit),
    )
    return verification


def _maybe_schedule_recheck(db: Session, unit: Unit, visit: FieldVisit, verification, reviewer) -> None:
    """A fixed share of approvals get an unannounced re-check by a different verifier (plan §5).
    The share is chosen by hash, so it can't be predicted from the outside or gamed by timing."""
    import hashlib

    from app.modules.compliance.service import rule

    bucket = int(hashlib.sha256(f"qa:{verification.id}:{unit.id}".encode()).hexdigest(), 16) % 100
    if bucket >= rule(db, "qa_recheck_percent") or open_assignment(db, unit):
        return
    candidates = [
        v for v in db.scalars(select(User).where(User.role == Role.FIELD_VERIFIER, User.is_active.is_(True)))
        if v.id != visit.verifier_id and not _has_interest(db, v, unit)
    ]
    if not candidates:
        record(db, reviewer, "qa.recheck_skipped", unit, reason="no other verifier")
        return
    load = {
        v.id: db.scalar(select(func.count()).select_from(VisitAssignment).where(
            VisitAssignment.verifier_id == v.id, VisitAssignment.status == AssignmentStatus.OPEN))
        for v in candidates
    }
    checker = min(candidates, key=lambda v: (load[v.id], v.id))
    assignment = VisitAssignment(
        unit_id=unit.id, verifier_id=checker.id, assigned_by_id=reviewer.id,
        scheduled_for=utcnow().date() + timedelta(days=7), purpose="qa_recheck", rechecks_visit_id=visit.id,
        note="Quality re-check: visit unannounced and check the home still matches the listing.",
    )
    db.add(assignment)
    db.flush()
    record(db, reviewer, "qa.recheck_scheduled", assignment, original_verifier=visit.verifier_id)
    notify(db, checker, "visit_assigned", link=f"/field/assignments/{assignment.id}", unit=str(unit),
           when=assignment.scheduled_for.strftime("%a %d %b"))


def _recheck_result(db: Session, visit: FieldVisit, assignment: VisitAssignment) -> None:
    """A failed re-check pauses the home (a high flag blocks publishing) and flags the original
    verifier. A reviewer decides what happens next; nothing is revoked automatically."""
    original = db.get(FieldVisit, assignment.rechecks_visit_id) if assignment.rechecks_visit_id else None
    record(db, visit.verifier, "qa.recheck_completed", visit, outcome=visit.outcome,
           original_visit=original.id if original else None)
    if visit.outcome != VisitOutcome.FAILED:
        return
    raise_flag(db, visit.unit, "qa.recheck_failed", Severity.HIGH,
               "An unannounced re-check found the home doesn't match what was verified.", visit=visit.id)
    if original is not None:
        raise_flag(db, original.verifier, "qa.verifier_reversal", Severity.MEDIUM,
                   f"A re-check of {visit.unit} failed after this verifier passed it.", visit=original.id)


def revoke(db: Session, verification: Verification, reviewer, reason_codes: list[str], note: str = "") -> Verification:
    """Take a badge away, e.g. after an upheld fraud report. Live listings pause at once."""
    from app.modules.listings.service import pause_listings_for  # listings depends on verification

    _require_reviewer(reviewer)
    if verification.status != VerificationStatus.APPROVED:
        raise RuleViolation("Only an approved verification can be revoked.")
    codes = _validate_codes(False, reason_codes, note)
    verification.status = VerificationStatus.REVOKED
    verification.revoked_at = utcnow()
    verification.revoked_by_id = reviewer.id
    db.flush()
    record(db, reviewer, "verification.revoked", verification, codes=codes, note=note)
    pause_listings_for(
        db, party=verification.party, unit=verification.unit, actor=reviewer, reason="verification revoked"
    )
    return verification


def verifier_stats(db: Session) -> list[dict]:
    """Per verifier: visits, pass rate, re-checks of their work and how many failed (plan §5:
    approval and reversal rates are reviewed monthly)."""
    rows = []
    for v in db.scalars(select(User).where(User.role == Role.FIELD_VERIFIER).order_by(User.id)):
        visits = db.execute(
            select(FieldVisit.outcome, func.count()).where(FieldVisit.verifier_id == v.id,
                                                           FieldVisit.outcome != VisitOutcome.IN_PROGRESS)
            .group_by(FieldVisit.outcome)
        ).all()
        by = dict(visits)
        done = sum(by.values())
        mine = select(FieldVisit.id).where(FieldVisit.verifier_id == v.id)
        rechecks = db.scalars(
            select(VisitAssignment.id).where(VisitAssignment.purpose == "qa_recheck",
                                             VisitAssignment.rechecks_visit_id.in_(mine))
        ).all()
        failed_rechecks = db.scalar(
            select(func.count()).select_from(FieldVisit).where(FieldVisit.assignment_id.in_(rechecks),
                                                                FieldVisit.outcome == VisitOutcome.FAILED)
        ) if rechecks else 0
        rows.append({
            "id": v.id, "name": v.name, "active": v.is_active, "visits": done,
            "passed": by.get(VisitOutcome.PASSED, 0), "failed": by.get(VisitOutcome.FAILED, 0),
            "pass_rate": round(by.get(VisitOutcome.PASSED, 0) / done, 2) if done else None,
            "rechecked": len(rechecks), "reversals": failed_rechecks,
        })
    return rows
