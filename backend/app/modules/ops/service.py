"""Trust and safety operations (roadmap workstream C): verification that scales without
losing quality. Re-verification, appeals, reviewer workload, visit routes, label quality
checks, photos seen elsewhere, and the investigation graph."""

import csv
import statistics
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, NotFound, RuleViolation
from app.core.geo import distance_m
from app.db import utcnow
from app.modules.accounts.models import Role, User
from app.modules.audit.log import record
from app.modules.audit.models import AuditEvent
from app.modules.compliance.service import rule
from app.modules.detection.models import DetectionLabel, LinkEdge
from app.modules.listings.models import Listing, ListingStatus
from app.modules.media.images import hamming
from app.modules.notifications.service import notify
from app.modules.risk.flags import raise_flag
from app.modules.risk.models import FlagStatus, RiskFlag, Severity
from app.modules.units.models import Unit
from app.modules.verification.models import FieldVisit, Verification, VerificationStatus, VisitPhoto

from .models import Appeal, AppealKind, AppealStatus, ExternalPhoto, LabelCheck

# --- Re-verification ------------------------------------------------------------------------------

RENEWAL_WINDOW = timedelta(days=30)


def reverify(db: Session) -> dict[str, int]:
    """Daily. Warns people 30 days before a verification expires, and pauses live listings
    once the landlord's or the home's verification has lapsed (build plan §5, step 5)."""
    from app.modules.listings.service import pause_listings_for
    from app.modules.verification.service import current_verification

    now = utcnow()
    counts = {"warned": 0, "paused": 0}
    expiring = db.scalars(select(Verification).where(
        Verification.status == VerificationStatus.APPROVED, Verification.expiry_reminded_at.is_(None),
        Verification.expires_at > now, Verification.expires_at <= now + RENEWAL_WINDOW,
    ))
    for v in expiring:
        latest = current_verification(db, party=v.party) if v.party_id else current_verification(db, unit=v.unit)
        if latest is None or latest.id != v.id:
            continue  # superseded by a newer decision
        who = v.party if v.party_id else v.unit.registered_by
        what = "your identity" if v.party_id else str(v.unit)
        notify(db, who, "verification_expiring", link="/landlord", what=what, when=v.expires_at.strftime("%d %b %Y"))
        v.expiry_reminded_at = now
        counts["warned"] += 1

    for listing in list(db.scalars(select(Listing).where(Listing.status == ListingStatus.LIVE))):
        lister_ok = current_verification(db, party=listing.lister) is not None
        unit_ok = current_verification(db, unit=listing.unit) is not None
        if lister_ok and unit_ok:
            continue
        reason = "Verification expired. Afe will visit again; the listing returns once it's renewed."
        pause_listings_for(db, unit=listing.unit, reason=reason)
        notify(db, listing.lister, "listing_paused_expired", link="/landlord", listing=listing.title)
        counts["paused"] += 1
    db.flush()
    return counts


# --- Appeals (decision B12) -------------------------------------------------------------------------------


def _appeal_target(db: Session, user: User, kind: str, subject_id: int) -> int | None:
    """Check the person may appeal this decision; return who made it."""
    from app.modules.scamcheck.models import FraudReport, ReportStatus

    if kind == AppealKind.VERIFICATION:
        v = db.get(Verification, subject_id)
        owner = v and (v.party_id == user.id or (v.unit_id and v.unit.registered_by_id == user.id))
        if not owner:
            raise NotFound("That decision isn't about you.")
        if v.status not in (VerificationStatus.REJECTED, VerificationStatus.REVOKED):
            raise RuleViolation("Only a rejection or a revocation can be appealed.")
        return v.decided_by_id
    if kind == AppealKind.LISTING:
        listing = db.get(Listing, subject_id)
        if listing is None or listing.lister_id != user.id:
            raise NotFound("That listing isn't yours.")
        if listing.status not in (ListingStatus.PAUSED, ListingStatus.ARCHIVED):
            raise RuleViolation("Only a paused or removed listing can be appealed.")
        return None
    if kind == AppealKind.REPORT:
        report = db.get(FraudReport, subject_id)
        if report is None or report.reported_phone != user.phone or report.status != ReportStatus.UPHELD:
            raise NotFound("There's no upheld report about you with that number.")
        return report.decided_by_id
    raise InvalidInput("Choose what you're appealing.")


def open_appeal(db: Session, user: User, kind: str, subject_id: int, reason: str) -> Appeal:
    if len((reason or "").strip()) < 30:
        raise InvalidInput("Explain what was wrong with the decision, and what evidence you have, in a few sentences.")
    decider = _appeal_target(db, user, kind, subject_id)
    appeal = Appeal(kind=kind, subject_id=subject_id, appellant_id=user.id, original_decider_id=decider,
                    reason=reason.strip()[:4000])
    try:
        with db.begin_nested():
            db.add(appeal)
            db.flush()
    except IntegrityError as exc:
        raise RuleViolation("This decision has already been appealed. Each decision can be appealed once.") from exc
    record(db, user, "appeal.opened", appeal, kind=kind, decision=subject_id)
    return appeal


def decide_appeal(db: Session, reviewer: User, appeal: Appeal, upheld: bool, outcome: str) -> Appeal:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can decide appeals.")
    if appeal.status != AppealStatus.OPEN:
        raise RuleViolation("This appeal is already decided.")
    if reviewer.id == appeal.original_decider_id:
        raise RuleViolation("A different reviewer must decide an appeal against your own decision.")
    if len((outcome or "").strip()) < 20:
        raise InvalidInput("Write the outcome the person will read: what you checked and why.")
    appeal.status = AppealStatus.UPHELD if upheld else AppealStatus.REJECTED
    appeal.outcome, appeal.decided_by_id, appeal.decided_at = outcome.strip()[:500], reviewer.id, utcnow()
    db.flush()
    record(db, reviewer, "appeal.decided", appeal, upheld=upheld)
    notify(db, appeal.appellant, "appeal_decided", link="/account/appeals",
           result="upheld" if upheld else "not upheld", outcome=appeal.outcome[:200])
    return appeal


def appealable(db: Session, user: User) -> list[dict]:
    """Decisions this person can still appeal: their latest rejections, paused listings and
    upheld scam reports about their number, minus ones already appealed."""
    from app.modules.scamcheck.models import FraudReport, ReportStatus

    done = set(db.execute(select(Appeal.kind, Appeal.subject_id).where(Appeal.appellant_id == user.id)).all())
    out = []
    own_units = select(Unit.id).where(Unit.registered_by_id == user.id)
    for v in db.scalars(select(Verification).where(
        (Verification.party_id == user.id) | Verification.unit_id.in_(own_units),
        Verification.status.in_([VerificationStatus.REJECTED, VerificationStatus.REVOKED]),
    ).order_by(Verification.decided_at.desc())):
        what = "Your identity" if v.party_id else f"Home {v.unit}"
        out.append({"kind": AppealKind.VERIFICATION, "subject_id": v.id, "date": v.decided_at,
                    "label": f"{what}: {v.status}"})
    for li in db.scalars(select(Listing).where(Listing.lister_id == user.id, Listing.status == ListingStatus.PAUSED)):
        out.append({"kind": AppealKind.LISTING, "subject_id": li.id, "date": li.updated_at,
                    "label": f"Listing {li.reference} paused: {li.status_reason or 'no reason given'}"})
    if user.phone:
        for r in db.scalars(select(FraudReport).where(FraudReport.reported_phone == user.phone,
                                                      FraudReport.status == ReportStatus.UPHELD)):
            out.append({"kind": AppealKind.REPORT, "subject_id": r.id, "date": r.decided_at,
                        "label": "A scam report about your number was upheld"})
    return [x for x in out if (str(x["kind"]), x["subject_id"]) not in done]


def open_appeals(db: Session) -> list[Appeal]:
    return list(db.scalars(select(Appeal).where(Appeal.status == AppealStatus.OPEN).order_by(Appeal.id)))


def appeals_for(db: Session, user: User) -> list[Appeal]:
    return list(db.scalars(select(Appeal).where(Appeal.appellant_id == user.id).order_by(Appeal.id.desc())))


# --- Reviewer workload -------------------------------------------------------------------------------------

SLA_DAYS = 3
DECISION_ACTIONS = (
    "verification.party_decided", "verification.unit_decided", "listing.published", "risk.flag_resolved",
    "report.decided", "tenancy.dispute_resolved", "appeal.decided", "label.checked",
)


def _age_days(dates) -> tuple[int, float | None, int]:
    dates = [d for d in dates if d is not None]
    now = utcnow()
    ages = [(now - d).total_seconds() / 86400 for d in dates]
    return len(ages), (round(max(ages), 1) if ages else None), sum(a > SLA_DAYS for a in ages)


def workload(db: Session) -> dict:
    from app.modules.scamcheck.models import FraudReport, ReportStatus
    from app.modules.tenancies.models import Dispute, DisputeStatus
    from app.modules.verification import service as verification

    queues = {
        "People to decide": [t for _, t in verification.people_awaiting_decision(db)],
        "Homes to decide": [t for _, t in verification.homes_awaiting_decision(db)],
        "Homes to visit": [u.created_at for u in verification.homes_needing_visit(db)],
        "Listings to publish": list(db.scalars(select(Listing.updated_at).where(Listing.status == ListingStatus.PENDING_REVIEW))),
        "Open flags": list(db.scalars(select(RiskFlag.created_at).where(RiskFlag.status == FlagStatus.OPEN))),
        "Scam reports": list(db.scalars(select(FraudReport.created_at).where(FraudReport.status == ReportStatus.NEW))),
        "Disputes": list(db.scalars(select(Dispute.created_at).where(Dispute.status == DisputeStatus.OPEN))),
        "Appeals": list(db.scalars(select(Appeal.created_at).where(Appeal.status == AppealStatus.OPEN))),
        "Label checks": list(db.scalars(select(LabelCheck.created_at).where(LabelCheck.status == "pending"))),
    }
    rows = []
    for name, dates in queues.items():
        count, oldest, late = _age_days(dates)
        rows.append({"queue": name, "count": count, "oldest_days": oldest, "over_sla": late})

    since = utcnow() - timedelta(days=30)
    first_live = db.execute(
        select(Unit.created_at, func.min(Listing.published_at)).join(Listing, Listing.unit_id == Unit.id)
        .where(Listing.published_at.is_not(None)).group_by(Unit.id)
    ).all()
    days = [(live - made).total_seconds() / 86400 for made, live in first_live if live and live > since]
    by_reviewer = db.execute(
        select(User.display_name, User.username, func.count()).join(AuditEvent, AuditEvent.actor_id == User.id)
        .where(AuditEvent.action.in_(DECISION_ACTIONS), AuditEvent.created_at > utcnow() - timedelta(days=7))
        .group_by(User.id)
    ).all()
    return {
        "sla_days": SLA_DAYS,
        "queues": rows,
        "median_days_to_live": round(statistics.median(days), 1) if days else None,
        "homes_live_last_30_days": len(days),
        "decisions_last_7_days": [{"reviewer": n or u, "decisions": c} for n, u, c in by_reviewer],
    }


# --- Visit routes ---------------------------------------------------------------------------------------------


def plan_routes(db: Session, day: date) -> dict:
    """Suggest a day's routes: each verifier stays in one area and visits nearby homes in a
    short loop. Travel is most of what a verification costs (build plan §5)."""
    from app.modules.verification import service as verification

    per_day = rule(db, "visits_per_verifier_day")
    homes = verification.homes_needing_visit(db)
    verifiers = list(db.scalars(select(User).where(User.role == Role.FIELD_VERIFIER, User.is_active.is_(True))
                                .order_by(User.id)))
    by_area: dict[int, list[Unit]] = {}
    for u in homes:
        by_area.setdefault(u.area_id, []).append(u)
    routes, left = [], []
    free = list(verifiers)
    for area_units in sorted(by_area.values(), key=len, reverse=True):
        # Nearest-neighbour order from the home waiting longest.
        order = [area_units.pop(0)]
        while area_units:
            last = order[-1]
            nxt = min(area_units, key=lambda u: distance_m(last.point, u.point))
            area_units.remove(nxt)
            order.append(nxt)
        while order:
            verifier = next((v for v in free if verification.can_visit(db, v, order[0])), None)
            if verifier is None:
                left += order
                break
            free.remove(verifier)
            stops = [u for u in order if verification.can_visit(db, verifier, u)][:per_day]
            for u in stops:
                order.remove(u)
            metres = sum(distance_m(a.point, b.point) for a, b in zip(stops, stops[1:], strict=False))
            routes.append({"verifier": verifier, "area": stops[0].area.name, "units": stops, "km": round(metres / 1000, 1)})
    return {"day": day, "per_verifier": per_day, "routes": routes, "unplanned": left}


def assign_route(db: Session, reviewer: User, verifier: User, units: list[Unit], day: date) -> tuple[int, list[str]]:
    from app.modules.verification.service import assign_visit

    done, problems = 0, []
    for u in units:
        try:
            with db.begin_nested():
                assign_visit(db, u, verifier, reviewer, day, "Planned route")
            done += 1
        except (RuleViolation, NotAllowed) as exc:
            problems.append(f"{u}: {exc}")
    return done, problems


# --- Label quality ------------------------------------------------------------------------------------------------


def label_checks_for(db: Session, reviewer: User) -> list[tuple[LabelCheck, DetectionLabel]]:
    """Pending checks this reviewer may do: never their own decisions."""
    rows = db.execute(
        select(LabelCheck, DetectionLabel).join(DetectionLabel, DetectionLabel.id == LabelCheck.label_id)
        .where(LabelCheck.status == "pending", DetectionLabel.decided_by_id != reviewer.id).order_by(LabelCheck.id)
    ).all()
    return [(c, lbl) for c, lbl in rows]


def check_label(db: Session, reviewer: User, check: LabelCheck, agree: bool, note: str = "") -> LabelCheck:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can check labels.")
    lbl = db.get(DetectionLabel, check.label_id)
    if lbl.decided_by_id == reviewer.id:
        raise RuleViolation("A label is checked by someone other than the person who decided it.")
    if check.status != "pending":
        raise RuleViolation("This label is already checked.")
    check.status, check.checked_by_id, check.checked_at, check.note = (
        "agreed" if agree else "disagreed", reviewer.id, utcnow(), note[:300])
    if not agree:
        lbl.disputed = True  # left out of training and evaluation until a senior reviewer settles it
    db.flush()
    record(db, reviewer, "label.checked", check, agree=agree)
    return check


# --- Photos seen elsewhere ------------------------------------------------------------------------------------------


def import_external_photos(db: Session, path: str) -> dict[str, int]:
    """Load photo hashes from a permitted crawl of public listing sites (CSV: source,url,phash,dhash)
    and flag Afe homes whose visit photos appear there: the same home listed elsewhere, maybe by
    someone else."""
    counts = {"imported": 0, "matched": 0}
    limit = 10  # of 64 bits: a little looser than the duplicate rule, since other sites recompress
    ours = db.execute(select(VisitPhoto.phash, FieldVisit.unit_id).join(FieldVisit)).all()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            phash = (row.get("phash") or "").strip().lower()
            if len(phash) != 16:
                continue
            photo = ExternalPhoto(source=row.get("source", "")[:60], url=row.get("url", "")[:500], phash=phash,
                                  dhash=(row.get("dhash") or "")[:16])
            match = next((unit_id for our, unit_id in ours if hamming(our, phash) <= limit), None)
            photo.matched_unit_id = match
            db.add(photo)
            counts["imported"] += 1
            if match:
                unit = db.get(Unit, match)
                raise_flag(db, unit, "photos.found_elsewhere", Severity.MEDIUM,
                           f"A photo of this home is on {photo.source or 'another site'}: {photo.url[:150]}",
                           url=photo.url)
                counts["matched"] += 1
    db.flush()
    return counts


# --- Investigation graph ------------------------------------------------------------------------------------------


def person_graph(db: Session, user: User, limit: int = 40) -> dict:
    from app.modules.detection.detectors import connected
    from app.modules.verification.service import current_verification

    ids = sorted(connected(db, user.id))[:limit]
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}
    flags = dict(db.execute(
        select(RiskFlag.subject_id, func.count()).where(
            RiskFlag.subject_type == "users", RiskFlag.subject_id.in_([str(i) for i in ids]),
            RiskFlag.status.in_([FlagStatus.OPEN, FlagStatus.CONFIRMED]))
        .group_by(RiskFlag.subject_id)
    ).all())
    fraud = set(db.scalars(select(DetectionLabel.subject_id).where(
        DetectionLabel.subject_type == "users", DetectionLabel.outcome == "fraud",
        DetectionLabel.subject_id.in_([str(i) for i in ids]))))
    nodes = [{
        "id": u.id, "name": u.name, "role": u.role_label, "active": u.is_active,
        "verified": current_verification(db, party=u) is not None if u.is_lister else None,
        "flags": flags.get(str(u.id), 0), "fraud": str(u.id) in fraud, "focus": u.id == user.id,
    } for u in (people[i] for i in ids if i in people)]
    edges = [{"a": e.user_a_id, "b": e.user_b_id, "kind": e.kind, "evidence": e.evidence}
             for e in db.scalars(select(LinkEdge).where(LinkEdge.user_a_id.in_(ids), LinkEdge.user_b_id.in_(ids)))]
    return {"nodes": nodes, "edges": edges}



def verifier_totals(db: Session) -> dict[str, int]:
    from app.modules.verification.service import verifier_stats

    rows = verifier_stats(db)
    return {"rechecked": sum(r["rechecked"] for r in rows), "reversals": sum(r["reversals"] for r in rows)}
