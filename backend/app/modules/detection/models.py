from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class JobStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


_PENDING_SQL = text("status = 'pending'")


class ScoreJob(Base):
    """Something to score. Requests only add a row (cheap); `python -m app.cli score-pending`
    does the scoring, so a slow model never slows a page."""

    __tablename__ = "detection_jobs"
    __table_args__ = (
        Index(
            "uq_detection_jobs_one_pending",
            "detector",
            "subject_type",
            "subject_id",
            unique=True,
            sqlite_where=_PENDING_SQL,
            postgresql_where=_PENDING_SQL,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    detector: Mapped[str] = mapped_column(String(20))
    subject_type: Mapped[str] = mapped_column(String(60))
    subject_id: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10), default=JobStatus.PENDING, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    done_at: Mapped[datetime | None]


class ModelScore(Base):
    """One model score, logged whatever the model's mode. In shadow nothing acts on it;
    it's kept to compare with what reviewers decide (build plan §7)."""

    __tablename__ = "model_scores"
    __table_args__ = (Index("ix_model_scores_subject", "detector", "subject_type", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    detector: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(40))
    subject_type: Mapped[str] = mapped_column(String(60))
    subject_id: Mapped[str] = mapped_column(String(40))
    score: Mapped[int] = mapped_column(comment="0-100")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String(10), comment="Mode when scored: shadow, canary or active")
    acted: Mapped[bool] = mapped_column(default=False, comment="True when this score raised a flag")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class LabelOutcome(StrEnum):
    FRAUD = "fraud"
    LEGIT = "legit"


class DetectionLabel(Base):
    """A human decision, kept as a training and evaluation label. Written by reviewer
    decisions, flag resolutions and upheld scam reports."""

    __tablename__ = "detection_labels"
    __table_args__ = (Index("ix_detection_labels_subject", "subject_type", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(60))
    subject_id: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(30), comment="verification, flag, report or authority")
    source_id: Mapped[str] = mapped_column(String(40), default="")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    scores: Mapped[dict] = mapped_column(JSON, default=dict, comment="Latest model scores when decided")
    disputed: Mapped[bool] = mapped_column(default=False, server_default="0",
                                           comment="A second reviewer disagreed; left out of training and evaluation")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class LinkKind(StrEnum):
    GHANA_CARD = "ghana_card"
    PAYOUT_ACCOUNT = "payout_account"
    PHOTO = "photo"
    PHONE_IN_MESSAGE = "phone_in_message"
    DEVICE = "device"


class LinkEdge(Base):
    """Two accounts that share something they shouldn't (build plan §7, linking accounts).
    Rebuilt nightly by `python -m app.cli detect-graph`."""

    __tablename__ = "link_edges"
    __table_args__ = (Index("uq_link_edges", "user_a_id", "user_b_id", "kind", "evidence", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[str] = mapped_column(String(80), comment="What is shared, never the raw value")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ModelVersion(Base):
    """A trained model's parameters. Scoring uses the newest version; older ones stay for
    comparison and rollback."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    detector: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    trained_on: Mapped[int] = mapped_column(default=0, comment="Labelled examples used")
    notes: Mapped[str] = mapped_column(String(300), default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class EvaluationSnapshot(Base):
    """One detector's evaluation for one ISO week (the weekly model report). Kept so reviewers can
    see a model improving or slipping; the live numbers are on the Models page."""

    __tablename__ = "evaluation_snapshots"
    __table_args__ = (Index("uq_evaluation_snapshots_week", "detector", "week", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    detector: Mapped[str] = mapped_column(String(20))
    week: Mapped[str] = mapped_column(String(8), comment="ISO week, e.g. 2026-W42")
    version: Mapped[str | None] = mapped_column(String(40))
    labels: Mapped[int] = mapped_column(default=0)
    fraud: Mapped[int] = mapped_column(default=0)
    model: Mapped[dict] = mapped_column(JSON, default=dict)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    promotable: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(String(300), default="")
    seeded: Mapped[dict | None] = mapped_column(JSON, comment="Results on the seeded test set, if it ran")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
