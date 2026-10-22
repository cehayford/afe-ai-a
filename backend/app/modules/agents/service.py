"""Agent runs (spec: the reviewer copilot): a completed visit queues a run, the worker runs it in shadow, and a
reviewer's decision is recorded against it. Nothing here can change a verification."""

import logging
from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.modules.units.models import Unit
from app.modules.verification.models import FieldVisit, Verification, VerificationStatus

from . import copilot, gateway
from .models import AgentRun, RunStatus

COPILOT = "copilot"
MAX_ATTEMPTS = 3
# Calls each worker pass makes. The worker runs its jobs one after another in one transaction each, so one call a
# pass keeps the other jobs on time and means a stopped worker loses at most the call in flight.
PER_PASS = 1
log = logging.getLogger("afe.agents")


def _quietly(db: Session, what: str, fn, *args) -> None:
    """The copilot never blocks a reviewer or a verifier: if its own step fails, that step is undone and logged, and
    the visit or decision goes on."""
    try:
        with db.begin_nested():
            fn(db, *args)
    except Exception:  # noqa: BLE001 - nothing in the copilot may stop a person's work
        log.exception("Reviewer copilot: %s failed; the person's work went on", what)


def on_visit_completed(db: Session, unit: Unit, visit: FieldVisit) -> None:
    _quietly(db, "queueing a run", queue_copilot, unit, visit)


def on_unit_decided(db: Session, verification: Verification) -> None:
    _quietly(db, "recording a decision", record_decision, verification)


def queue_copilot(db: Session, unit: Unit, visit: FieldVisit) -> AgentRun | None:
    """A completed visit puts the home in "homes to decide": queue one copilot run for it, unless the copilot is off."""
    if gateway.level(db, COPILOT) == "off":
        return None
    existing = db.scalar(select(AgentRun).where(AgentRun.agent == COPILOT, AgentRun.visit_id == visit.id))
    if existing is not None:
        return existing
    run = AgentRun(agent=COPILOT, unit_id=unit.id, visit_id=visit.id)
    db.add(run)
    db.flush()
    return run


def _decided_since(db: Session, run: AgentRun) -> bool:
    visit = db.get(FieldVisit, run.visit_id)
    return db.scalar(
        select(Verification.id)
        .where(Verification.unit_id == run.unit_id, Verification.decided_at >= visit.completed_at)
        .limit(1)
    ) is not None


def _finish(run: AgentRun, status: RunStatus, now) -> RunStatus:
    run.status, run.finished_at = status, now
    return status


def _spend(run: AgentRun, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    run.input_tokens += input_tokens
    run.output_tokens += output_tokens
    run.cost_usd = round(run.cost_usd + cost_usd, 6)


def _attempt(db: Session, run: AgentRun, client, now) -> str:
    packet = copilot.packet(db, db.get(Unit, run.unit_id), db.get(FieldVisit, run.visit_id), now=now)
    run.packet, run.packet_sha256 = packet, copilot.fingerprint(packet)
    run.attempts += 1
    run.last_attempt_at = now
    run.model, run.prompt_version = get_settings().agent_copilot_model, copilot.PROMPT_VERSION
    try:
        s = copilot.suggest(packet, client=client)
    except copilot.NoAnswer as exc:
        _spend(run, exc.input_tokens, exc.output_tokens, exc.cost_usd)
        run.error = str(exc)[:300]
        if exc.refused:
            return _finish(run, RunStatus.REFUSED, now)
        return _finish(run, RunStatus.FAILED, now) if run.attempts >= MAX_ATTEMPTS else "retry"
    except copilot.FAILURES as exc:
        run.error = f"{type(exc).__name__}: {exc}"[:300]
        return _finish(run, RunStatus.FAILED, now) if run.attempts >= MAX_ATTEMPTS else "retry"
    _spend(run, s.input_tokens, s.output_tokens, s.cost_usd)
    answer = s.answer
    run.model, run.decision, run.reason_codes = s.model, answer.decision, list(answer.reason_codes)
    run.summary, run.concerns, run.error = answer.summary, [c.model_dump() for c in answer.concerns], ""
    return _finish(run, RunStatus.DONE, now)


def run_pending(db: Session, limit: int = PER_PASS, now=None, client=None) -> dict[str, int]:
    """The worker's pass (every minute): queued copilot runs, oldest first. Switched off, they're cancelled; a home
    decided meanwhile makes them too late; past today's token budget they wait for tomorrow."""
    now = now or utcnow()
    counts = dict.fromkeys(("done", "failed", "refused", "too_late", "cancelled", "retry", "waiting"), 0)
    level = gateway.level(db, COPILOT)
    calls = 0
    for run in list(db.scalars(
        select(AgentRun).where(AgentRun.agent == COPILOT, AgentRun.status == RunStatus.QUEUED).order_by(AgentRun.id)
    )):
        if level == "off":
            counts[_finish(run, RunStatus.CANCELLED, now)] += 1
        elif _decided_since(db, run):
            counts[_finish(run, RunStatus.TOO_LATE, now)] += 1
        elif calls >= limit or gateway.over_budget(db, COPILOT, now):
            counts["waiting"] += 1
        else:
            calls += 1
            try:
                with db.begin_nested():
                    outcome = _attempt(db, run, client, now)
            except Exception as exc:  # noqa: BLE001 - one bad run counts as an attempt; it never stalls the queue
                log.exception("Reviewer copilot run %s failed unexpectedly", run.id)
                run.attempts += 1
                run.last_attempt_at, run.error = now, f"{type(exc).__name__}: {exc}"[:300]
                outcome = _finish(run, RunStatus.FAILED, now) if run.attempts >= MAX_ATTEMPTS else "retry"
            counts[outcome] += 1
            db.flush()
    db.flush()
    return counts


def record_decision(db: Session, verification: Verification) -> AgentRun | None:
    """A reviewer decided a home: note it on the copilot's run for the visit they decided on, and whether the copilot
    agreed. Only a finished run counts; one still waiting is marked too late on the next pass."""
    if verification.unit_id is None or verification.field_visit_id is None:
        return None
    run = db.scalar(select(AgentRun).where(AgentRun.agent == COPILOT, AgentRun.visit_id == verification.field_visit_id))
    if run is None or run.status != RunStatus.DONE:
        return None
    run.reviewer_decision = "approve" if verification.status == VerificationStatus.APPROVED else "reject"
    run.reviewer_codes = list(verification.reason_codes)
    result = copilot.compare(run.decision, run.reason_codes, run.reviewer_decision, run.reviewer_codes)
    run.agrees, run.false_approval = result.agrees, result.false_approval
    db.flush()
    return run


def numbers(db: Session, days: int = 7, now=None) -> dict:
    """The copilot's shadow numbers over the last `days`, for the reviewers' Models page and copilot-report. What it
    suggested on each case isn't included."""
    now = now or utcnow()
    runs = list(db.scalars(
        select(AgentRun).where(AgentRun.agent == COPILOT, AgentRun.created_at > now - timedelta(days=days))
    ))
    statuses = Counter(r.status for r in runs)
    decided = [r for r in runs if r.reviewer_decision]
    overlaps = [copilot.compare(r.decision, r.reason_codes, r.reviewer_decision, r.reviewer_codes).overlap for r in decided]
    return {
        "level": gateway.level(db, COPILOT),
        "days": days,
        "runs": len(runs),
        "done": statuses[RunStatus.DONE],
        "failed": statuses[RunStatus.FAILED],
        "refused": statuses[RunStatus.REFUSED],
        "too_late": statuses[RunStatus.TOO_LATE],
        "decided": len(decided),
        "agreement": round(sum(bool(r.agrees) for r in decided) / len(decided), 3) if decided else None,
        "false_approvals": sum(bool(r.false_approval) for r in decided),
        "code_overlap": round(sum(overlaps) / len(overlaps), 3) if overlaps else None,
        "cost_usd": round(sum(r.cost_usd for r in runs), 4),
    }
