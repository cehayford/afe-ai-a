"""The weekly model report (Trust Engine, Stage 0): every detector's evaluation against the rules
and its results on the seeded test set, kept once per ISO week and sent to reviewers."""

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, RuleViolation
from app.db import utcnow
from app.modules.accounts.models import REVIEWER_ROLES, User
from app.modules.compliance.service import rule

from .detectors import REGISTRY
from .models import EvaluationSnapshot
from .seeded import DEFAULT_PATH, evaluate_seeded, load_cases
from .service import evaluate, mode, train_text

log = logging.getLogger("afe.detection")


def iso_week(when: datetime) -> str:
    year, week, _ = when.isocalendar()
    return f"{year}-W{week:02d}"


def take_snapshots(
    db: Session, now: datetime | None = None, seeded_path: Path = DEFAULT_PATH
) -> tuple[list[EvaluationSnapshot], bool]:
    """Evaluate every detector and keep one row per detector for this week. Running it again in the
    same week updates those rows instead of adding more, and reviewers are told only the first time.
    Returns the rows and whether this call created them."""
    now = now or utcnow()
    week = iso_week(now)
    try:
        seeded = {r.detector: r.as_dict() for r in evaluate_seeded(db, load_cases(seeded_path))}
    except InvalidInput as exc:
        # A broken seeded file mustn't stop the report, but it mustn't read as a perfect score either.
        log.warning("seeded test set didn't load: %s", exc)
        seeded = None
    created, rows = False, []
    for name in REGISTRY:
        report = evaluate(db, name)
        row = db.scalar(
            select(EvaluationSnapshot).where(EvaluationSnapshot.detector == name, EvaluationSnapshot.week == week)
        )
        if row is None:
            row = EvaluationSnapshot(detector=name, week=week)
            db.add(row)
            created = True
        row.version, row.labels, row.fraud = report.version, report.labels, report.fraud
        row.model, row.rules = report.model.as_dict(), report.rules.as_dict()
        row.promotable, row.reason = report.promotable, report.reason[:300]
        row.seeded = seeded.get(name) if seeded is not None else None
        rows.append(row)
    db.flush()
    if created:
        _tell_reviewers(db, rows, week, seeded_loaded=seeded is not None)
    return rows, created


def _tell_reviewers(db: Session, rows: list[EvaluationSnapshot], week: str, seeded_loaded: bool) -> None:
    from app.modules.notifications.service import notify_on

    ready = [r.detector for r in rows if r.promotable]
    missed = sum(len((r.seeded or {}).get("missed", [])) for r in rows)
    seeded = (f"{missed} misses on the seeded test set" if seeded_loaded
              else "The seeded test set didn't load; run python -m app.cli eval-seeded to see why")
    summary = f"{len(ready)} of {len(rows)} models could leave shadow" + (f" ({', '.join(ready)})" if ready else "")
    for person in db.scalars(select(User).where(User.role.in_(REVIEWER_ROLES), User.is_active.is_(True))):
        notify_on(db, person, "model_report", {"in_app"}, link="/review/detection", week=week, summary=summary,
                  seeded=seeded)


def weekly_models(db: Session, now: datetime | None = None, force: bool = False) -> dict:
    """Mondays: take the weekly report, then retrain the in-house wording model while it's in shadow.
    A model that is already acting (canary or active) is retrained only by a reviewer, because a new
    version would act before anyone had judged it. A version is also kept until it has enough decided
    cases to be judged: evaluation counts only the newest version's scores, so replacing it every week
    would reset its count and it could never leave shadow. Runs at most once a week."""
    now = now or utcnow()
    if now.weekday() != 0 and not force:
        return {"ran": False, "why": "the weekly report runs on Mondays"}
    rows, first_run = take_snapshots(db, now)
    if not first_run:
        trained = "already ran this week"
    elif mode(db, "scam_text") not in ("off", "shadow"):
        trained = "not trained: the model is acting, so a reviewer retrains it"
    else:
        current, needed = evaluate(db, "scam_text"), rule(db, "model_min_labels")
        if current.labels < needed:
            trained = (f"not trained: the current version has {current.labels} of {needed} decided cases; "
                       "it is judged before a new one replaces it")
        else:
            try:
                trained = train_text(db, None).version
            except RuleViolation as exc:
                trained = f"not trained: {exc}"
    return {"ran": True, "week": iso_week(now), "snapshots": len(rows), "trained": trained}
