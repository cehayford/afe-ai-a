"""The worker: one long-running process for the frequent jobs (python -m app.cli worker).

Starting a new container every minute for each job costs more than the jobs do, so in staging and
production one small always-on task runs them on their intervals instead. The daily jobs stay on
the scheduler. Each job runs in its own transaction, and a failing job is logged (one JSON line,
counted by a CloudWatch alarm) without stopping the others.

On the free development server there is no scheduler, so `worker --with-daily` also runs the
daily jobs, once a day during their UTC hour (Accra time is UTC). The days they ran are kept in
a small state file, so restarting the worker during that hour doesn't run a job twice.
"""

import importlib
import json
import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.db import SessionLocal

log = logging.getLogger("afe.worker")


@dataclass(frozen=True)
class Job:
    name: str
    every_seconds: int
    target: str  # "module:function", imported when the job first runs

    def load(self) -> Callable:
        module, func = self.target.split(":")
        return getattr(importlib.import_module(module), func)


JOBS = (
    Job("publish-outbox", 60, "app.modules.tenancies.service:publish_outbox"),
    Job("score-pending", 60, "app.modules.detection.service:process_pending"),
    Job("run-agents", 60, "app.modules.agents.service:run_pending"),
    Job("run-due", 300, "app.modules.tenancies.service:run_due"),
    Job("retry-messages", 300, "app.modules.notifications.service:retry_failed"),
    Job("expire-whatsapp", 300, "app.modules.notifications.service:expire_undelivered"),
    Job("send-alerts", 300, "app.modules.alerts.service:send_alerts"),
    Job("remind-viewings", 300, "app.modules.enquiries.service:send_viewing_reminders"),
)


@dataclass(frozen=True)
class DailyJob(Job):
    at_hour: int = 0  # UTC


def detect_graph(db):
    from app.modules.detection.service import process_pending, run_graph

    return {"graph": run_graph(db), "scored": process_pending(db, limit=5000)}


def pilot_report(db):
    from app.modules.tenancies.service import send_pilot_report

    return send_pilot_report(db) or "protected payments are off"


def weekly_models(db):
    from app.modules.detection.reports import weekly_models as run

    return run(db)


# Same hours as the EventBridge schedules in infra/terraform/staging/operations.tf.
DAILY_JOBS = (
    DailyJob("reconcile", 86400, "app.modules.tenancies.service:nightly_reconcile", at_hour=2),
    DailyJob("detect-graph", 86400, "app.worker:detect_graph", at_hour=3),
    DailyJob("reverify", 86400, "app.modules.ops.service:reverify", at_hour=4),
    DailyJob("rent-reminders", 86400, "app.modules.rentals.service:send_rent_reminders", at_hour=7),
    DailyJob("pilot-report", 86400, "app.worker:pilot_report", at_hour=8),
    DailyJob("weekly-models", 86400, "app.worker:weekly_models", at_hour=5),
    DailyJob("whatsapp-health", 86400, "app.modules.notifications.alarms:whatsapp_health", at_hour=6),
)


def _run(job: Job, session_factory) -> None:
    try:
        with session_factory.begin() as db:
            result = job.load()(db)
        log.info(json.dumps({"event": "worker_job_done", "job": job.name, "result": result}, default=str))
        if job.name == "reconcile" and result:
            # Differences between the ledger and the partner need a person (docs/runbooks.md).
            log.error(json.dumps({"event": "worker_job_failed", "job": job.name, "differences": len(result)}))
    except Exception as exc:  # noqa: BLE001 - one job's failure must not stop the others
        log.error(json.dumps({"event": "worker_job_failed", "job": job.name, "type": type(exc).__name__}),
                  exc_info=exc)


def tick(last_run: dict[str, float], now: float, jobs=JOBS, session_factory=SessionLocal) -> list[str]:
    """Run every job that is due. Returns the names of the jobs that ran (whether or not they failed)."""
    ran = []
    for job in jobs:
        if now - last_run.get(job.name, float("-inf")) < job.every_seconds:
            continue
        last_run[job.name] = now
        ran.append(job.name)
        _run(job, session_factory)
    return ran


def tick_daily(last_day: dict[str, str], now: datetime, jobs=DAILY_JOBS, session_factory=SessionLocal) -> list[str]:
    """Run each daily job once per UTC day, during its hour. If the worker is down for the whole
    hour, that day's run is skipped (as a missed EventBridge schedule would be), never doubled."""
    ran, today = [], now.date().isoformat()
    for job in jobs:
        if now.hour != job.at_hour or last_day.get(job.name) == today:
            continue
        last_day[job.name] = today
        ran.append(job.name)
        _run(job, session_factory)
    return ran


def _load_state(path: Path | None) -> dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
    except (OSError, ValueError):
        return {}


def _save_state(path: Path | None, state: dict[str, str]) -> None:
    if path:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(path)


def run_forever(poll_seconds: float = 5.0, with_daily: bool = False, state_file: str = "") -> None:
    """Run until the container is stopped. ECS sends SIGTERM first: finish the current job, then exit."""
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_run: dict[str, float] = {}
    state_path = Path(state_file) if state_file else None
    last_day = _load_state(state_path)
    daily = DAILY_JOBS if with_daily else ()
    log.info(json.dumps({"event": "worker_started", "jobs": [j.name for j in (*JOBS, *daily)]}))
    while not stopping:
        tick(last_run, time.monotonic())
        if with_daily and tick_daily(last_day, datetime.now(UTC)):
            _save_state(state_path, last_day)
        time.sleep(poll_seconds)
