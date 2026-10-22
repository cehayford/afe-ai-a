from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotAllowed
from app.db import utcnow
from app.modules.audit.log import record, subject_key
from app.modules.detection.hooks import label_key

from .models import SEVERITY_ORDER, FlagStatus, RiskFlag, Severity


def raise_flag(db: Session, subject, rule: str, severity: str, explanation: str, **evidence) -> RiskFlag:
    """Open a flag, or return the open flag already raised by the same rule on the same subject."""
    subject_type, subject_id = subject_key(subject)
    existing = db.scalar(
        select(RiskFlag).where(
            RiskFlag.subject_type == subject_type,
            RiskFlag.subject_id == subject_id,
            RiskFlag.rule == rule,
            RiskFlag.status == FlagStatus.OPEN,
        )
    )
    if existing:
        return existing
    flag = RiskFlag(
        subject_type=subject_type,
        subject_id=subject_id,
        rule=rule,
        severity=severity,
        explanation=explanation[:300],
        evidence=evidence,
    )
    db.add(flag)
    db.flush()
    record(db, None, "risk.flag_raised", flag, rule=rule, severity=severity, flagged=f"{subject_type}#{subject_id}")
    return flag


def open_flags(db: Session, subject, min_severity: str = Severity.LOW) -> list[RiskFlag]:
    allowed = SEVERITY_ORDER[SEVERITY_ORDER.index(Severity(min_severity)) :]
    subject_type, subject_id = subject_key(subject)
    return list(
        db.scalars(
            select(RiskFlag)
            .where(
                RiskFlag.subject_type == subject_type,
                RiskFlag.subject_id == subject_id,
                RiskFlag.status == FlagStatus.OPEN,
                RiskFlag.severity.in_([str(s) for s in allowed]),
            )
            .order_by(RiskFlag.id)
        )
    )


def resolve_flag(db: Session, flag: RiskFlag, reviewer, confirmed_fraud: bool, note: str) -> RiskFlag:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can resolve risk flags.")
    flag.status = FlagStatus.CONFIRMED if confirmed_fraud else FlagStatus.DISMISSED
    flag.resolved_by_id = reviewer.id
    flag.resolved_at = utcnow()
    flag.resolution_note = note
    db.flush()
    # Every reviewer decision is a label for the Phase 3 models.
    record(db, reviewer, "risk.flag_resolved", flag, rule=flag.rule, outcome=flag.status, note=note)
    label_key(db, flag.subject_type, flag.subject_id, confirmed_fraud, "flag", reviewer, [flag.rule], flag.id)
    return flag
