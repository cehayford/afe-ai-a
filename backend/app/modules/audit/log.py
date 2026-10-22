from sqlalchemy.orm import Session

from .models import AuditEvent


def subject_key(subject) -> tuple[str, str]:
    return subject.__tablename__, str(subject.id)


def record(db: Session, actor, action: str, subject, **data) -> AuditEvent:
    """Write one audit event in the same transaction as the change it records."""
    subject_type, subject_id = subject_key(subject)
    event = AuditEvent(
        actor_id=getattr(actor, "id", None),
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        data=data,
    )
    db.add(event)
    db.flush()
    return event
