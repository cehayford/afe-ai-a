"""The two calls other modules make: `enqueue` something to score, and `label` a human
decision. Kept free of heavy imports so any service can call them."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit.log import subject_key

from .models import DetectionLabel, JobStatus, LabelOutcome, ModelScore, ScoreJob

# Rejection reasons that mean someone tried to deceive, not just that paperwork was missing.
FRAUD_CODES = {
    "ID_MISMATCH",
    "DOCS_SUSPECT",
    "OWNER_DENIES",
    "UNIT_NOT_FOUND",
    "DUPLICATE_PHOTOS",
    "DUPLICATE_ACCOUNT",
    "FRAUD_REPORT",
}


def enqueue(db: Session, detector: str, subject) -> None:
    subject_type, subject_id = subject_key(subject)
    exists = db.scalar(
        select(ScoreJob.id).where(
            ScoreJob.detector == detector,
            ScoreJob.subject_type == subject_type,
            ScoreJob.subject_id == subject_id,
            ScoreJob.status == JobStatus.PENDING,
        )
    )
    if not exists:
        db.add(ScoreJob(detector=detector, subject_type=subject_type, subject_id=subject_id))
        db.flush()



def enqueue_text(db: Session, subject) -> None:
    """Queue a listing or message for the wording detectors: the in-house model always, and the
    Claude detector only while its mode isn't off, so nothing is queued to leave Afe by default."""
    from app.modules.compliance.service import rule

    enqueue(db, "scam_text", subject)
    if rule(db, "model_scam_text_llm_mode") != "off":
        enqueue(db, "scam_text_llm", subject)


def latest_scores(db: Session, subject_type: str, subject_id: str) -> dict[str, int]:
    newest = (
        select(ModelScore.detector, func.max(ModelScore.id).label("id"))
        .where(ModelScore.subject_type == subject_type, ModelScore.subject_id == subject_id)
        .group_by(ModelScore.detector)
        .subquery()
    )
    return dict(db.execute(select(ModelScore.detector, ModelScore.score).join(newest, ModelScore.id == newest.c.id)).all())


def label(
    db: Session, subject, fraud: bool, source: str, decided_by=None, reasons: list[str] | None = None, source_id=""
) -> DetectionLabel:
    """Record a human decision as a label, with the model scores the subject had at the time."""
    subject_type, subject_id = subject_key(subject)
    return label_key(db, subject_type, subject_id, fraud, source, decided_by, reasons, source_id)


def label_key(
    db: Session,
    subject_type: str,
    subject_id: str,
    fraud: bool,
    source: str,
    decided_by=None,
    reasons: list[str] | None = None,
    source_id="",
) -> DetectionLabel:
    row = DetectionLabel(
        subject_type=subject_type,
        subject_id=subject_id,
        outcome=LabelOutcome.FRAUD if fraud else LabelOutcome.LEGIT,
        source=source,
        source_id=str(source_id),
        reasons=list(reasons or []),
        decided_by_id=getattr(decided_by, "id", None),
        scores=latest_scores(db, subject_type, subject_id),
    )
    db.add(row)
    db.flush()
    if decided_by is not None and label_sampled(row.id):
        from app.modules.ops.models import LabelCheck

        db.add(LabelCheck(label_id=row.id))
        db.flush()
    return row


LABEL_CHECK_PERCENT = 5


def label_sampled(label_id: int, percent: int = LABEL_CHECK_PERCENT) -> bool:
    """A fixed 5% of reviewer decisions get a second reviewer's check."""
    return int(hashlib.sha256(f"labelcheck:{label_id}".encode()).hexdigest(), 16) % 100 < percent
