"""The trust & safety back office: queues, decisions, assignments, documents and flags."""

import mimetypes
from datetime import date, timedelta
from pathlib import PurePosixPath

from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import select

from app.core.envelope import Envelope, ok
from app.core.errors import NotFound
from app.deps import DB, Reviewer
from app.modules.accounts.models import LISTER_ROLES, Role, User
from app.modules.agents import service as agents
from app.modules.audit.log import record
from app.modules.billing.service import fee_settled, waive_fee
from app.modules.compliance import service as compliance
from app.modules.compliance.models import ComplianceRule
from app.modules.detection import service as detection
from app.modules.detection.detectors import REGISTRY
from app.modules.detection.models import EvaluationSnapshot, ModelVersion
from app.modules.identity.service import latest_check
from app.modules.listings import service as listings
from app.modules.listings.models import Listing, ListingStatus
from app.modules.media.storage import storage
from app.modules.ops import service as ops
from app.modules.ops.models import Appeal, LabelCheck
from app.modules.reviews.models import Review
from app.modules.reviews.service import hide_review, reviews_about
from app.modules.risk.flags import open_flags, resolve_flag
from app.modules.risk.models import FlagStatus, RiskFlag
from app.modules.scamcheck import service as scamcheck
from app.modules.scamcheck.models import FraudReport
from app.modules.tenancies import service as tenancies
from app.modules.tenancies.models import Dispute, Tenancy, TenancyStatus
from app.modules.units import service as units
from app.modules.units.models import AuthorityRecord, Unit
from app.modules.verification import service as verification
from app.modules.verification.models import APPROVAL_CODES, REASON_LABELS, ReasonCode, Verification, VisitAssignment

from .. import schemas as s
from .common import get_or_404
from .tenancies import dispute_out, tenancy_out
from .verify import visit_detail_out

router = APIRouter(prefix="/review", tags=["review"])


def _home_row(unit: Unit, last_visit=None) -> s.QueueHomeOut:
    return s.QueueHomeOut(
        id=unit.id, address=str(unit), area=unit.area.name, landlord=unit.registered_by.name, last_visit=last_visit
    )


@router.get("/queue")
def queue(db: DB, user: Reviewer):
    pending = db.scalars(select(Listing).where(Listing.status == ListingStatus.PENDING_REVIEW).order_by(Listing.id))
    flags = db.scalars(select(RiskFlag).where(RiskFlag.status == FlagStatus.OPEN).order_by(RiskFlag.id))
    return ok(
        {
            "people": [
                s.QueuePersonOut(id=u.id, name=u.name, role=u.role_label, phone=u.phone, last_check=t)
                for u, t in verification.people_awaiting_decision(db)
            ],
            "homes_to_decide": [_home_row(u, t) for u, t in verification.homes_awaiting_decision(db)],
            "homes_to_visit": [_home_row(u) for u in verification.homes_needing_visit(db)],
            "homes_awaiting_fee": [_home_row(u) for u in verification.homes_awaiting_fee(db)],
            "assignments": [s.AssignmentOut.of(a) for a in verification.open_assignments(db)],
            "listings": [
                {
                    "listing": s.ListingOut.of(li),
                    "lister": li.lister.name,
                    "blockers": listings.publish_blockers(db, li),
                }
                for li in pending
            ],
            "flags": [s.FlagOut.model_validate(f) for f in flags],
        }
    )


@router.get("/reason-codes", response_model=Envelope[list[s.ReasonCodeOut]])
def reason_codes(user: Reviewer):
    return ok([s.ReasonCodeOut(code=c, label=REASON_LABELS[c], approval=c in APPROVAL_CODES) for c in ReasonCode])


@router.get("/verifiers", response_model=Envelope[list[s.UserOut]])
def verifiers(db: DB, user: Reviewer):
    rows = db.scalars(select(User).where(User.role == Role.FIELD_VERIFIER, User.is_active).order_by(User.display_name))
    return ok([s.UserOut.of(u) for u in rows])


# --- People -------------------------------------------------------------------------------------------


@router.get("/people/{user_id}", response_model=Envelope[s.PersonReviewOut])
def person(db: DB, user: Reviewer, user_id: int):
    party = get_or_404(db, User, user_id, "Person")
    if party.role not in LISTER_ROLES:
        raise NotFound("Only landlords and agents are verified.")
    check = latest_check(db, party)
    current = verification.current_verification(db, party=party)
    return ok(
        s.PersonReviewOut(
            user=s.UserOut.of(party),
            identity=s.IdentityCheckOut.model_validate(check) if check else None,
            current=s.VerificationOut.of(current) if current else None,
            history=[s.VerificationOut.of(v) for v in verification.decision_history(db, party=party)],
            flags=[s.FlagOut.model_validate(f) for f in open_flags(db, party)],
            model_notes=[
                *model_notes(db, detection.scores_for(db, party), "Account"),
                *model_notes(db, detection.message_scores_for_user(db, party), "Message"),
            ],
            links=links_out(db, party),
            reviews=[_review_out(db, r) for r in reviews_about(db, party.id)],
        )
    )


def _review_out(db, r: Review) -> s.ReviewModerationOut:
    listing = db.get(Listing, r.listing_id)
    return s.ReviewModerationOut(
        id=r.id, rating=r.rating, body=r.body, author_name=r.author.name, listing_reference=listing.reference if listing else "",
        created_at=r.created_at, hidden=r.hidden,
    )


@router.post("/people/{user_id}/decision", response_model=Envelope[s.VerificationOut])
def decide_person(db: DB, user: Reviewer, user_id: int, body: s.DecisionIn):
    v = verification.decide_party(
        db, get_or_404(db, User, user_id, "Person"), user, body.approve, body.reason_codes, body.note
    )
    return ok(s.VerificationOut.of(v))


# --- Homes -------------------------------------------------------------------------------------------------


@router.get("/units/{unit_id}", response_model=Envelope[s.HomeReviewOut])
def home(db: DB, user: Reviewer, unit_id: int):
    unit = get_or_404(db, Unit, unit_id, "Home")
    visit = verification.latest_completed_visit(db, unit)
    current = verification.current_verification(db, unit=unit)
    assignment = verification.open_assignment(db, unit)
    return ok(
        s.HomeReviewOut(
            unit=s.UnitOut.model_validate(unit),
            registered_by=s.UserOut.of(unit.registered_by),
            authorities=[s.AuthorityOut.model_validate(a) for a in unit.authority_records],
            visit=visit_detail_out(visit) if visit else None,
            current=s.VerificationOut.of(current) if current else None,
            history=[s.VerificationOut.of(v) for v in verification.decision_history(db, unit=unit)],
            flags=[s.FlagOut.model_validate(f) for f in open_flags(db, unit)],
            fee_settled=fee_settled(db, unit),
            open_assignment=s.AssignmentOut.of(assignment) if assignment else None,
            model_notes=home_model_notes(db, unit),
        )
    )


@router.post("/units/{unit_id}/decision", response_model=Envelope[s.VerificationOut])
def decide_home(db: DB, user: Reviewer, unit_id: int, body: s.DecisionIn):
    v = verification.decide_unit(
        db, get_or_404(db, Unit, unit_id, "Home"), user, body.approve, body.reason_codes, body.note
    )
    return ok(s.VerificationOut.of(v))


@router.post("/units/{unit_id}/assignments", response_model=Envelope[s.AssignmentOut], status_code=201)
def assign(db: DB, user: Reviewer, unit_id: int, body: s.AssignIn):
    a = verification.assign_visit(
        db,
        get_or_404(db, Unit, unit_id, "Home"),
        get_or_404(db, User, body.verifier_id, "Verifier"),
        user,
        body.scheduled_for,
        body.note,
    )
    return ok(s.AssignmentOut.of(a))


@router.post("/units/{unit_id}/fee-waiver", response_model=Envelope[s.PaymentOut], status_code=201)
def fee_waiver(db: DB, user: Reviewer, unit_id: int, body: s.WaiverIn):
    return ok(s.PaymentOut.of(waive_fee(db, get_or_404(db, Unit, unit_id, "Home"), user, body.note)))


@router.post("/assignments/{assignment_id}/cancel", response_model=Envelope[s.AssignmentOut])
def cancel_assignment(db: DB, user: Reviewer, assignment_id: int):
    a = verification.cancel_assignment(db, get_or_404(db, VisitAssignment, assignment_id, "Assignment"), user)
    return ok(s.AssignmentOut.of(a))


# --- Authority documents ---------------------------------------------------------------------------------------


@router.get("/authority/{authority_id}/document", response_class=Response)
def authority_document(db: DB, user: Reviewer, authority_id: int):
    """Stream a private document to a reviewer. Every read is logged (Statement §8.6)."""
    authority = get_or_404(db, AuthorityRecord, authority_id, "Document")
    try:
        content = storage.read("private", authority.document_key)
    except FileNotFoundError as exc:
        raise NotFound("The document file is missing.") from exc
    record(db, user, "authority.document_viewed", authority)
    db.commit()  # the read is logged even if sending the file fails
    suffix = PurePosixPath(authority.document_key).suffix
    return Response(
        content,
        media_type=mimetypes.guess_type(f"x{suffix}")[0] or "application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="authority-{authority.id}{suffix}"',
        },
    )


@router.post("/authority/{authority_id}/owner-confirmation", response_model=Envelope[s.AuthorityOut])
def owner_confirmation(db: DB, user: Reviewer, authority_id: int, body: s.OwnerConfirmIn):
    a = units.confirm_owner_by_phone(
        db, get_or_404(db, AuthorityRecord, authority_id, "Document"), user, body.owner_phone, body.owner_name
    )
    return ok(s.AuthorityOut.model_validate(a))


@router.post("/authority/{authority_id}/decision", response_model=Envelope[s.AuthorityOut])
def authority_decision(db: DB, user: Reviewer, authority_id: int, body: s.AuthorityReviewIn):
    a = units.review_authority(
        db, get_or_404(db, AuthorityRecord, authority_id, "Document"), user, body.accept, body.note
    )
    return ok(s.AuthorityOut.model_validate(a))


# --- Listings, verifications, flags --------------------------------------------------------------------------------


@router.post("/listings/{listing_id}/publish", response_model=Envelope[s.ListingOut])
def publish(db: DB, user: Reviewer, listing_id: int):
    return ok(s.ListingOut.of(listings.publish(db, get_or_404(db, Listing, listing_id, "Listing"), user)))


@router.post("/verifications/{verification_id}/revoke", response_model=Envelope[s.VerificationOut])
def revoke(db: DB, user: Reviewer, verification_id: int, body: s.RevokeIn):
    v = verification.revoke(
        db, get_or_404(db, Verification, verification_id, "Verification"), user, body.reason_codes, body.note
    )
    return ok(s.VerificationOut.of(v))


@router.post("/flags/{flag_id}/resolve", response_model=Envelope[s.FlagOut])
def resolve(db: DB, user: Reviewer, flag_id: int, body: s.FlagResolveIn):
    flag = resolve_flag(db, get_or_404(db, RiskFlag, flag_id, "Flag"), user, body.confirmed_fraud, body.note)
    return ok(s.FlagOut.model_validate(flag))


# --- Phase 2: money, disputes and rules ------------------------------------------------------------


@router.get("/tenancies", response_model=Envelope[list[s.TenancyOut]])
def money_queue(db: DB, user: Reviewer):
    """Tenancies that need a person: releases waiting for approval and open disputes."""
    rows = db.scalars(
        select(Tenancy).where(Tenancy.status.in_([TenancyStatus.RELEASE_PENDING, TenancyStatus.DISPUTED]))
        .order_by(Tenancy.funded_at)
    )
    return ok([tenancy_out(db, t, user) for t in rows])


@router.post("/tenancies/{reference}/release", response_model=Envelope[s.TenancyOut])
def approve_release(db: DB, user: Reviewer, reference: str, body: s.EvidenceIn):
    t = tenancies.approve_release(db, user, tenancies.get_by_reference(db, reference, lock=True), body.note)
    return ok(tenancy_out(db, t, user))


@router.get("/disputes", response_model=Envelope[list[s.DisputeOut]])
def disputes(db: DB, user: Reviewer):
    return ok([dispute_out(d) for d in tenancies.open_disputes(db)])


@router.post("/disputes/{dispute_id}/decision", response_model=Envelope[s.DisputeOut])
def decide_dispute(db: DB, user: Reviewer, dispute_id: int, body: s.DisputeDecisionIn):
    d = tenancies.resolve_dispute(db, user, get_or_404(db, Dispute, dispute_id, "Dispute"), body.decision, body.note)
    return ok(dispute_out(d))


@router.get("/finance", response_model=Envelope[dict])
def finance(db: DB, user: Reviewer):
    return ok(tenancies.finance_summary(db), mismatches=tenancies.reconcile(db))


def _rules_out(db) -> list[s.RuleOut]:
    out = []
    for row in compliance.all_rules(db):
        out.append(s.RuleOut(
            key=row["key"], label=row["label"], value=row["value"], version=row["version"], source=row["source"],
            pending=[s.RulePendingOut(id=p.id, value=p.value["v"], version=p.version, source=p.source,
                                      proposed_by_name=p.proposed_by.name, proposed_at=p.proposed_at)
                     for p in row["pending"]],
        ))
    return out


@router.get("/rules", response_model=Envelope[list[s.RuleOut]])
def rules(db: DB, user: Reviewer):
    return ok(_rules_out(db))


@router.post("/rules", response_model=Envelope[list[s.RuleOut]], status_code=201)
def propose_rule(db: DB, user: Reviewer, body: s.RuleProposeIn):
    compliance.propose(db, user, body.key, body.value, body.source)
    return ok(_rules_out(db))


@router.post("/rules/{rule_id}/approve", response_model=Envelope[list[s.RuleOut]])
def approve_rule(db: DB, user: Reviewer, rule_id: int):
    compliance.approve(db, get_or_404(db, ComplianceRule, rule_id, "Rule"), user)
    return ok(_rules_out(db))


@router.post("/rules/{rule_id}/reject", response_model=Envelope[list[s.RuleOut]])
def reject_rule(db: DB, user: Reviewer, rule_id: int):
    compliance.reject(db, get_or_404(db, ComplianceRule, rule_id, "Rule"), user)
    return ok(_rules_out(db))


@router.post("/rules/{key}/rollback", response_model=Envelope[list[s.RuleOut]], status_code=201)
def rollback_rule(db: DB, user: Reviewer, key: str):
    compliance.rollback(db, key, user)
    return ok(_rules_out(db))


@router.post("/reviews/{review_id}/hide", response_model=Envelope[dict])
def hide(db: DB, user: Reviewer, review_id: int, body: s.EvidenceIn):
    hide_review(db, user, get_or_404(db, Review, review_id, "Review"), body.note)
    return ok({"hidden": True})



# --- Phase 3: detection --------------------------------------------------------------------------------


def model_notes(db, scores, subject: str) -> list[s.ModelNoteOut]:
    out = []
    for row in scores:
        detector = REGISTRY.get(row.detector)
        out.append(s.ModelNoteOut(
            detector=row.detector, label=detector.label if detector else row.detector,
            subject=f"{subject} #{row.subject_id}" if subject == "Message" else subject, version=row.version,
            score=row.score, threshold=detection.threshold(db, row.detector), reasons=row.reasons, mode=row.mode,
            acted=row.acted, created_at=row.created_at,
        ))
    return out


def home_model_notes(db, unit) -> list[s.ModelNoteOut]:
    notes = model_notes(db, detection.scores_for(db, unit), "Home")
    for authority in unit.authority_records:
        notes += model_notes(db, detection.scores_for(db, authority), f"Document #{authority.id}")
    for listing in db.scalars(select(Listing).where(Listing.unit_id == unit.id)):
        notes += model_notes(db, detection.scores_for(db, listing), f"Listing {listing.reference}")
    return notes


def links_out(db, user) -> list[s.LinkOut]:
    edges, _ = detection.links_for(db, user)
    out = []
    for e in edges:
        other = db.get(User, e.user_b_id if e.user_a_id == user.id else e.user_a_id)
        out.append(s.LinkOut(other_user_id=other.id, other_name=other.name, kind=e.kind, evidence=e.evidence))
    return out


def _detector_out(row) -> s.DetectorOut:
    ev = row["evaluation"]
    return s.DetectorOut(
        **{k: row[k] for k in ("name", "label", "mode", "threshold", "version", "scores", "acted", "pending", "failed")},
        evaluation=s.EvaluationOut(
            version=ev.version, labels=ev.labels, fraud=ev.fraud, model=s.TallyOut(**ev.model.as_dict()),
            rules=s.TallyOut(**ev.rules.as_dict()), promotable=ev.promotable, reason=ev.reason,
        ),
    )


@router.get("/detection", response_model=Envelope[list[s.DetectorOut]])
def detectors(db: DB, user: Reviewer):
    """Every model, its mode, and how it compares with the Phase 1 rules on labelled cases."""
    versions = db.scalars(select(ModelVersion).order_by(ModelVersion.id.desc()).limit(10))
    return ok([_detector_out(row) for row in detection.summary(db)],
              versions=[s.ModelVersionOut.model_validate(v).model_dump(mode="json") for v in versions])


@router.get("/detection/history", response_model=Envelope[list[s.SnapshotOut]])
def detection_history(db: DB, user: Reviewer):
    """The weekly model reports, newest week first: the last 12 weeks for every model."""
    rows = db.scalars(
        select(EvaluationSnapshot)
        .order_by(EvaluationSnapshot.week.desc(), EvaluationSnapshot.detector)
        .limit(12 * len(REGISTRY))
    )
    return ok([s.SnapshotOut.model_validate(r) for r in rows])


@router.get("/agents/copilot", response_model=Envelope[s.CopilotNumbersOut])
def copilot_numbers(db: DB, user: Reviewer):
    """The reviewer copilot's shadow numbers for the last 7 days. What it suggested on each case stays hidden."""
    return ok(s.CopilotNumbersOut(**agents.numbers(db)))


@router.post("/detection/scam_text/train", response_model=Envelope[s.ModelVersionOut], status_code=201)
def train(db: DB, user: Reviewer):
    return ok(s.ModelVersionOut.model_validate(detection.train_text(db, user)))


def _report_out(db, report: FraudReport) -> s.ReportOut:
    matched_user, matched_listing = scamcheck.report_matches(db, report)
    out = s.ReportOut.model_validate(report)
    if matched_user:
        out.matched_user_id, out.matched_user_name = matched_user.id, matched_user.name
    if matched_listing:
        out.matched_listing_title = matched_listing.title
    return out


@router.get("/reports", response_model=Envelope[list[s.ReportOut]])
def reports(db: DB, user: Reviewer):
    """Scam reports from "Check before you pay", waiting for a decision."""
    return ok([_report_out(db, r) for r in scamcheck.open_reports(db)])


@router.post("/reports/{report_id}/decision", response_model=Envelope[s.ReportOut])
def decide_report(db: DB, user: Reviewer, report_id: int, body: s.ReportDecisionIn):
    report = scamcheck.decide_report(db, user, get_or_404(db, FraudReport, report_id, "Report"), body.upheld, body.note)
    return ok(_report_out(db, report))


@router.get("/verifier-stats", response_model=Envelope[list[dict]])
def verifier_stats(db: DB, user: Reviewer):
    """For the monthly review of verifiers: pass rates, re-checks and reversals (plan §5)."""
    return ok(verification.verifier_stats(db))



# --- Trust and safety operations (workstream C) ---------------------------------------------------


@router.get("/workload", response_model=Envelope[dict])
def workload(db: DB, user: Reviewer):
    return ok(ops.workload(db))


def _stop(u) -> s.RouteStopOut:
    return s.RouteStopOut(unit_id=u.id, address=str(u), landlord=u.registered_by.name, lat=float(u.lat), lng=float(u.lng))


@router.get("/visit-plan", response_model=Envelope[s.VisitPlanOut])
def visit_plan(db: DB, user: Reviewer, day: date | None = None):
    plan = ops.plan_routes(db, day or date.today() + timedelta(days=1))
    return ok(s.VisitPlanOut(
        day=plan["day"], per_verifier=plan["per_verifier"],
        routes=[s.RouteOut(verifier_id=r["verifier"].id, verifier_name=r["verifier"].name, area=r["area"], km=r["km"],
                           stops=[_stop(u) for u in r["units"]]) for r in plan["routes"]],
        unplanned=[_stop(u) for u in plan["unplanned"]],
    ))


@router.post("/visit-plan/assign", response_model=Envelope[dict])
def assign_route(db: DB, user: Reviewer, body: s.AssignRouteIn):
    verifier = get_or_404(db, User, body.verifier_id, "Verifier")
    homes = [get_or_404(db, Unit, i, "Home") for i in body.unit_ids]
    done, problems = ops.assign_route(db, user, verifier, homes, body.day)
    return ok({"assigned": done, "problems": problems})


def _appeal_out(a) -> s.AppealOut:
    out = s.AppealOut.model_validate(a)
    out.appellant_name = a.appellant.name
    return out


@router.get("/appeals", response_model=Envelope[list[s.AppealOut]])
def appeals(db: DB, user: Reviewer):
    return ok([_appeal_out(a) for a in ops.open_appeals(db)])


@router.post("/appeals/{appeal_id}/decision", response_model=Envelope[s.AppealOut])
def decide_appeal(db: DB, user: Reviewer, appeal_id: int, body: s.AppealDecisionIn):
    return ok(_appeal_out(ops.decide_appeal(db, user, get_or_404(db, Appeal, appeal_id, "Appeal"), body.upheld,
                                            body.outcome)))


@router.get("/label-checks", response_model=Envelope[list[s.LabelCheckOut]])
def label_checks(db: DB, user: Reviewer):
    return ok([
        s.LabelCheckOut(id=c.id, subject=f"{lbl.subject_type[:-1]} #{lbl.subject_id}", outcome=lbl.outcome,
                        source=lbl.source, reasons=lbl.reasons, decided_at=lbl.created_at)
        for c, lbl in ops.label_checks_for(db, user)
    ])


@router.post("/label-checks/{check_id}", response_model=Envelope[dict])
def check_label(db: DB, user: Reviewer, check_id: int, body: s.LabelCheckIn):
    ops.check_label(db, user, get_or_404(db, LabelCheck, check_id, "Check"), body.agree, body.note)
    return ok({"checked": True})


@router.get("/people/{user_id}/graph", response_model=Envelope[dict])
def person_graph(db: DB, user: Reviewer, user_id: int):
    """Everyone linked to this person, how, and what Afe already decided about them."""
    return ok(ops.person_graph(db, get_or_404(db, User, user_id, "Person")))



@router.get("/targets", response_model=Envelope[list[s.TargetOut]])
def targets(db: DB, user: Reviewer):
    """The build plan's §13 targets, now."""
    from app.modules.insights.service import targets as compute

    return ok([s.TargetOut(**t) for t in compute(db)])
