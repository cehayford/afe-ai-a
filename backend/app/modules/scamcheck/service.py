"""'Check before you pay' (plan §1). Wording rule (decision B12): Afe only ever says a
person or listing is, or is not, verified by Afe. It never calls anyone a scammer."""

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, RuleViolation
from app.core.ghana import normalise_phone
from app.db import utcnow
from app.modules.accounts.models import User
from app.modules.audit.log import record
from app.modules.detection.hooks import label
from app.modules.listings.models import Listing, ListingStatus
from app.modules.verification.service import current_verification

from .models import Channel, FraudReport, Lookup, ReportStatus

_REFERENCE = re.compile(r"^AFE-?([2-9A-HJ-NP-Z]{6})$", re.IGNORECASE)

ADVICE = [
    "Never pay before you have viewed the home.",
    "Never pay a viewing or inspection fee.",
    "Pay through Afe when protected payments open, so your money is held until you move in.",
]


@dataclass
class CheckResult:
    verified: bool
    headline: str
    details: list[str] = field(default_factory=list)
    listings: list[Listing] = field(default_factory=list)
    advice: list[str] = field(default_factory=lambda: list(ADVICE))


def check(db: Session, query: str, channel: str = Channel.WEB) -> CheckResult:
    query = (query or "").strip()
    ref = _REFERENCE.match(query.replace(" ", ""))
    if ref:
        reference = f"AFE-{ref.group(1).upper()}"
        result = _check_reference(db, reference)
        kind, logged = "reference", reference
    else:
        try:
            phone = normalise_phone(query)
        except InvalidInput:
            db.add(Lookup(channel=channel, query_kind="invalid", query=query[:20], result="invalid"))
            db.flush()
            return CheckResult(
                False, "Enter a Ghana phone number or an Afe listing reference like AFE-7K3M9Q.", advice=[]
            )
        result = _check_phone(db, phone)
        kind, logged = "phone", phone
    db.add(
        Lookup(channel=channel, query_kind=kind, query=logged, result="verified" if result.verified else "not_verified")
    )
    db.flush()
    return result


def _check_phone(db: Session, phone: str) -> CheckResult:
    person = db.scalar(select(User).where(User.phone == phone))
    verification = current_verification(db, party=person) if person else None
    if verification is None:
        return CheckResult(
            False,
            "This number is not verified by Afe.",
            ["That does not mean the person is dishonest. It means Afe has not checked them."],
        )
    live = list(db.scalars(select(Listing).where(Listing.lister_id == person.id, Listing.status == ListingStatus.LIVE)))
    return CheckResult(
        True,
        f"This number belongs to a landlord or agent verified by Afe on {verification.decided_at:%d %b %Y}.",
        [f"Verified until {verification.expires_at:%d %b %Y}."],
        listings=live,
    )


def _check_reference(db: Session, reference: str) -> CheckResult:
    listing = db.scalar(select(Listing).where(Listing.reference == reference))
    if listing is None:
        return CheckResult(False, f"{reference} is not an Afe listing.", ["Check the reference for typing mistakes."])
    if listing.status != ListingStatus.LIVE:
        return CheckResult(False, f"{reference} is not live on Afe right now.", ["Do not pay anyone for this listing."])
    return CheckResult(True, f"{reference} is a live listing verified by Afe.", listings=[listing])


def report(
    db: Session,
    what_happened: str,
    reported_phone: str = "",
    reported_reference: str = "",
    amount_lost_pesewas: int | None = None,
    reporter_contact: str = "",
    channel: str = Channel.WEB,
) -> FraudReport:
    if len(what_happened.strip()) < 10:
        raise InvalidInput("Tell us what happened in a sentence or two.")
    phone = normalise_phone(reported_phone) if reported_phone else ""
    fraud_report = FraudReport(
        channel=channel,
        reported_phone=phone,
        reported_reference=reported_reference.strip().upper()[:10],
        what_happened=what_happened.strip(),
        amount_lost_pesewas=amount_lost_pesewas,
        reporter_contact=reporter_contact.strip(),
    )
    db.add(fraud_report)
    db.flush()
    return fraud_report


def open_reports(db: Session) -> list[FraudReport]:
    return list(db.scalars(select(FraudReport).where(FraudReport.status == ReportStatus.NEW).order_by(FraudReport.id)))


def report_matches(db: Session, fraud_report: FraudReport) -> tuple[User | None, Listing | None]:
    """The Afe account and listing a report points at, if any."""
    user = (
        db.scalar(select(User).where(User.phone == fraud_report.reported_phone)) if fraud_report.reported_phone else None
    )
    listing = (
        db.scalar(select(Listing).where(Listing.reference == fraud_report.reported_reference))
        if fraud_report.reported_reference
        else None
    )
    return user, listing


def decide_report(db: Session, reviewer, fraud_report: FraudReport, upheld: bool, note: str) -> FraudReport:
    """A reviewer decides whether a report holds up. An upheld report on an Afe account or
    listing becomes a fraud label (build plan §7: reports are the main source of fraud examples)
    and a flag for the trust team; it never removes anyone by itself."""
    from app.modules.risk.flags import raise_flag
    from app.modules.risk.models import Severity

    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can decide reports.")
    if fraud_report.status != ReportStatus.NEW:
        raise RuleViolation("This report is already decided.")
    if len(note.strip()) < 10:
        raise InvalidInput("Say what you checked; the note stays with the report.")
    fraud_report.status = ReportStatus.UPHELD if upheld else ReportStatus.NOT_UPHELD
    fraud_report.decided_by_id, fraud_report.decided_at = reviewer.id, utcnow()
    fraud_report.decision_note = note.strip()[:300]
    db.flush()
    record(db, reviewer, "report.decided", fraud_report, upheld=upheld)
    if upheld:
        user, listing = report_matches(db, fraud_report)
        for subject in (user, listing):
            if subject is not None:
                label(db, subject, fraud=True, source="report", decided_by=reviewer, source_id=fraud_report.id)
                raise_flag(
                    db, subject, "report.upheld", Severity.HIGH,
                    f"A scam report was upheld: {fraud_report.what_happened[:180]}", report=fraud_report.id,
                )
    return fraud_report
