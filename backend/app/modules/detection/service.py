"""Scoring, evaluation and training for the Phase 3 detectors (build plan §7).

Lifecycle of a model: it scores in shadow; reviewers' decisions become labels; `evaluate`
compares it with the Phase 1 rules on the same labelled cases; if it wins, a reviewer may
propose canary (it acts on a fixed share of cases) and a second reviewer approves; later,
active. Acting means raising a flag for a person, never deciding on its own."""

import hashlib
import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotAllowed, RuleViolation
from app.db import utcnow
from app.modules.audit.log import record, subject_key
from app.modules.compliance.service import rule
from app.modules.enquiries.models import Message
from app.modules.listings.models import Listing
from app.modules.risk.flags import raise_flag
from app.modules.risk.models import Severity

from .detectors import REGISTRY, build_links, connected
from .hooks import enqueue
from .models import DetectionLabel, JobStatus, LabelOutcome, LinkEdge, ModelScore, ModelVersion, ScoreJob
from .text import train_naive_bayes

log = logging.getLogger("afe.detection")

MODEL_WARNING = "Afe's checks think this message may be a scam. Never pay before you view a home, and keep payment on Afe."
MAX_ATTEMPTS = 3


def mode(db: Session, detector: str) -> str:
    return rule(db, f"model_{detector}_mode")


def threshold(db: Session, detector: str) -> int:
    return rule(db, f"model_{detector}_threshold")


def in_canary(db: Session, subject_type: str, subject_id: str) -> bool:
    """A fixed share of subjects, chosen by hash so the same case always gets the same answer."""
    bucket = int(hashlib.sha256(f"{subject_type}:{subject_id}".encode()).hexdigest(), 16) % 100
    return bucket < rule(db, "model_canary_percent")


# --- Scoring ------------------------------------------------------------------------------------------


def score_now(db: Session, detector_name: str, subject) -> ModelScore | None:
    """Score one subject and log it; act on it only in canary or active mode."""
    current = mode(db, detector_name)
    if current == "off":
        return None
    detector = REGISTRY[detector_name]
    result = detector.score(db, subject)
    subject_type, subject_id = subject_key(subject)
    row = ModelScore(
        detector=detector_name,
        version=result.version,
        subject_type=subject_type,
        subject_id=subject_id,
        score=result.score,
        reasons=result.reasons,
        mode=current,
    )
    db.add(row)
    db.flush()
    acts = current == "active" or (current == "canary" and in_canary(db, subject_type, subject_id))
    if acts and result.score >= threshold(db, detector_name):
        target = detector.flag_subject(db, subject)
        if target is not None:
            reason = result.reasons[0] if result.reasons else "no single reason"
            raise_flag(
                db,
                target,
                f"model.{detector_name}",
                Severity.MEDIUM,  # a model flag asks for a look; it never blocks on its own
                f"{detector.label}: {result.score}/100 ({reason})"[:300],
                score=result.score,
                version=result.version,
                mode=current,
                scored=f"{subject_type}:{subject_id}",
            )
            row.acted = True
            if isinstance(subject, Message) and not subject.warning:
                subject.warning = MODEL_WARNING
            db.flush()
    return row


# Detectors that call an outside service: at most this many of their jobs per run, so a slow
# provider can't hold up the other jobs that share the worker. The rest wait for the next run.
PER_RUN = {"scam_text_llm": 20}


def process_pending(db: Session, limit: int = 200) -> dict[str, int]:
    """Run queued scoring jobs. Each job is its own savepoint, so one failure doesn't undo others."""
    counts = {"scored": 0, "skipped": 0, "failed": 0, "deferred": 0}
    taken: dict[str, int] = {}
    jobs = list(
        db.scalars(select(ScoreJob).where(ScoreJob.status == JobStatus.PENDING).order_by(ScoreJob.id).limit(limit))
    )
    for job in jobs:
        cap = PER_RUN.get(job.detector)
        if cap is not None:
            if taken.get(job.detector, 0) >= cap:
                counts["deferred"] += 1
                continue
            taken[job.detector] = taken.get(job.detector, 0) + 1
        detector = REGISTRY.get(job.detector)
        subject = detector.load(db, job.subject_type, job.subject_id) if detector else None
        try:
            with db.begin_nested():
                scored = score_now(db, job.detector, subject) if subject is not None else None
        except Exception as exc:  # noqa: BLE001 - a model failure must not stop the queue
            log.warning("detection job %s failed: %s", job.id, exc)
            job.attempts += 1
            job.error = str(exc)[:300]
            if job.attempts >= MAX_ATTEMPTS:
                job.status, job.done_at = JobStatus.FAILED, utcnow()
                counts["failed"] += 1
            continue
        job.status, job.done_at = JobStatus.DONE, utcnow()
        counts["scored" if scored else "skipped"] += 1
    db.flush()
    return counts


def run_graph(db: Session) -> dict[str, int]:
    """Nightly: rebuild account links, then queue every linked account for scoring."""
    edges = build_links(db)
    users = set()
    for a, b in db.execute(select(LinkEdge.user_a_id, LinkEdge.user_b_id)):
        users.update((a, b))
    from app.modules.accounts.models import User

    for user_id in sorted(users):
        enqueue(db, "accounts", db.get(User, user_id))
    return {"edges": edges, "accounts_queued": len(users)}


# --- Evaluation -----------------------------------------------------------------------------------------


@dataclass
class Tally:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, predicted: bool, actual: bool) -> None:
        if predicted and actual:
            self.tp += 1
        elif predicted:
            self.fp += 1
        elif actual:
            self.fn += 1
        else:
            self.tn += 1

    @property
    def flagged(self) -> int:
        return self.tp + self.fp

    @property
    def precision(self) -> float | None:
        return self.tp / self.flagged if self.flagged else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else None

    def as_dict(self) -> dict:
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn, "flagged": self.flagged,
                "precision": self.precision, "recall": self.recall}


@dataclass
class Evaluation:
    detector: str
    version: str | None
    threshold: int
    labels: int = 0
    fraud: int = 0
    model: Tally = field(default_factory=Tally)
    rules: Tally = field(default_factory=Tally)
    promotable: bool = False
    reason: str = ""


def _at_least(a: float | None, b: float | None) -> bool:
    return (a or 0) >= (b or 0)


def evaluate(db: Session, detector_name: str) -> Evaluation:
    """Compare the newest model version with the Phase 1 rules on every labelled case the model
    scored before a person decided it. A model that flags nothing scores well on accuracy, so we
    use precision and recall, and allow no more false alarms than the rules (plus a small margin)."""
    detector = REGISTRY[detector_name]
    version = db.scalar(
        select(ModelScore.version).where(ModelScore.detector == detector_name).order_by(ModelScore.id.desc())
    )
    report = Evaluation(detector_name, version, threshold(db, detector_name))
    if version is None:
        report.reason = "it hasn't scored anything yet"
        return report
    labels = db.scalars(select(DetectionLabel).where(DetectionLabel.subject_type.in_(detector.label_types),
                                                     DetectionLabel.disputed.is_(False)))
    for lbl in labels:
        score = detector.score_for_label(db, lbl, version)
        if score is None:
            continue
        actual = lbl.outcome == LabelOutcome.FRAUD
        report.labels += 1
        report.fraud += actual
        report.model.add(score >= report.threshold, actual)
        report.rules.add(detector.rule_hit_for_label(db, lbl), actual)

    needed = rule(db, "model_min_labels")
    m, r = report.model, report.rules
    if report.labels < needed:
        report.reason = f"it has {report.labels} labelled cases and needs {needed}"
    elif report.fraud < 5:
        report.reason = f"only {report.fraud} of its labelled cases are fraud; it needs at least 5"
    elif not (_at_least(m.precision, r.precision) and _at_least(m.recall, r.recall)):
        report.reason = "it doesn't beat the rules on both precision and recall"
    elif (m.precision or 0) == (r.precision or 0) and (m.recall or 0) == (r.recall or 0):
        report.reason = "it only matches the rules; it must do better on precision or recall"
    elif m.fp > max(r.fp * 1.25, r.fp + 2):
        # Workload is judged on false alarms: catching more real fraud is the point.
        report.reason = f"it raises {m.fp} false alarms where the rules raise {r.fp}: too much reviewer work"
    else:
        report.promotable = True
        report.reason = "it beats the rules on labelled cases without adding false alarms"
    return report


# --- Training --------------------------------------------------------------------------------------------

MIN_TRAINING_PER_CLASS = 5


def text_examples(db: Session) -> list[tuple[str, bool]]:
    examples = []
    for lbl in db.scalars(select(DetectionLabel).where(DetectionLabel.subject_type.in_(["listings", "users"]),
                                                       DetectionLabel.disputed.is_(False))):
        fraud = lbl.outcome == LabelOutcome.FRAUD
        if lbl.subject_type == "listings":
            listing = db.get(Listing, int(lbl.subject_id))
            if listing:
                examples.append((f"{listing.title}\n{listing.description}", fraud))
        else:
            bodies = db.scalars(
                select(Message.body).where(Message.sender_id == int(lbl.subject_id), Message.created_at <= lbl.created_at)
            ).all()
            if bodies:
                examples.append(("\n".join(bodies), fraud))
    return examples


def train_text(db: Session, reviewer) -> ModelVersion:
    """Train a new scam-wording version from labels. New versions start in whatever mode the
    detector is in, and are evaluated separately from older versions."""
    if reviewer is not None and not reviewer.can_review:
        raise NotAllowed("Only reviewers can train models.")
    examples = text_examples(db)
    fraud = sum(1 for _, f in examples if f)
    legit = len(examples) - fraud
    if fraud < MIN_TRAINING_PER_CLASS or legit < MIN_TRAINING_PER_CLASS:
        raise RuleViolation(
            f"Not enough labelled text yet: {fraud} fraud and {legit} genuine examples; "
            f"training needs {MIN_TRAINING_PER_CLASS} of each."
        )
    count = db.scalar(select(func.count()).select_from(ModelVersion).where(ModelVersion.detector == "scam_text"))
    version = ModelVersion(
        detector="scam_text",
        version=f"nb-{count + 1}",
        params=train_naive_bayes(examples),
        trained_on=len(examples),
        notes=f"{fraud} fraud, {legit} genuine examples",
        created_by_id=getattr(reviewer, "id", None),
    )
    db.add(version)
    db.flush()
    record(db, reviewer, "detection.trained", version, examples=len(examples), fraud=fraud)
    return version


# --- Reading ------------------------------------------------------------------------------------------------


def scores_for(db: Session, subject) -> list[ModelScore]:
    """Newest score from each detector for a subject, for the reviewer's model notes."""
    subject_type, subject_id = subject_key(subject)
    newest = (
        select(func.max(ModelScore.id))
        .where(ModelScore.subject_type == subject_type, ModelScore.subject_id == subject_id)
        .group_by(ModelScore.detector)
    )
    return list(db.scalars(select(ModelScore).where(ModelScore.id.in_(newest)).order_by(ModelScore.detector)))


def message_scores_for_user(db: Session, user) -> list[ModelScore]:
    """The sender's highest-scoring messages, newest first."""
    ids = [str(i) for i in db.scalars(select(Message.id).where(Message.sender_id == user.id))]
    if not ids:
        return []
    return list(
        db.scalars(
            select(ModelScore)
            .where(ModelScore.detector == "scam_text", ModelScore.subject_type == "messages", ModelScore.subject_id.in_(ids))
            .order_by(ModelScore.score.desc(), ModelScore.id.desc())
            .limit(5)
        )
    )


def links_for(db: Session, user) -> tuple[list[LinkEdge], int]:
    edges = list(
        db.scalars(
            select(LinkEdge).where((LinkEdge.user_a_id == user.id) | (LinkEdge.user_b_id == user.id)).order_by(LinkEdge.id)
        )
    )
    return edges, len(connected(db, user.id)) if edges else 1


def summary(db: Session) -> list[dict]:
    rows = []
    for name, detector in REGISTRY.items():
        report = evaluate(db, name)
        counts = dict(
            db.execute(
                select(ScoreJob.status, func.count()).where(ScoreJob.detector == name).group_by(ScoreJob.status)
            ).all()
        )
        rows.append({
            "name": name,
            "label": detector.label,
            "mode": mode(db, name),
            "threshold": report.threshold,
            "version": report.version,
            "scores": db.scalar(select(func.count()).select_from(ModelScore).where(ModelScore.detector == name)),
            "acted": db.scalar(
                select(func.count()).select_from(ModelScore).where(ModelScore.detector == name, ModelScore.acted.is_(True))
            ),
            "pending": counts.get(JobStatus.PENDING, 0),
            "failed": counts.get(JobStatus.FAILED, 0),
            "evaluation": report,
        })
    return rows
