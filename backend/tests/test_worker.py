"""The worker runs frequent jobs on their intervals, each in its own transaction."""

import logging

from app import worker
from app.worker import JOBS, Job, tick


class Sessions:
    """Stands in for SessionLocal: records that each job got its own transaction."""

    def __init__(self):
        self.opened = 0

    def begin(self):
        sessions = self

        class Tx:
            def __enter__(self):
                sessions.opened += 1
                return "db"

            def __exit__(self, *exc):
                return False

        return Tx()


calls = []


def ok_job(db):
    calls.append(db)
    return {"done": 1}


def bad_job(db):
    raise RuntimeError("partner down")


def test_every_frequent_job_is_importable():
    for job in JOBS:
        assert callable(job.load()), job.name
    assert {j.name for j in JOBS} == {
        "publish-outbox", "score-pending", "run-agents", "run-due", "retry-messages", "expire-whatsapp",
        "send-alerts", "remind-viewings"}


def test_jobs_run_on_their_intervals_and_a_failure_does_not_stop_the_rest(caplog):
    calls.clear()
    jobs = (Job("fast", 60, f"{__name__}:ok_job"), Job("broken", 60, f"{__name__}:bad_job"),
            Job("slow", 300, f"{__name__}:ok_job"))
    sessions, last = Sessions(), {}
    with caplog.at_level(logging.INFO, logger="afe.worker"):
        assert tick(last, 1000, jobs, sessions) == ["fast", "broken", "slow"]
    assert sessions.opened == 3 and len(calls) == 2
    assert "worker_job_failed" in caplog.text and "partner down" in caplog.text
    assert tick(last, 1030, jobs, sessions) == []
    assert tick(last, 1060, jobs, sessions) == ["fast", "broken"]
    assert tick(last, 1300, jobs, sessions) == ["fast", "broken", "slow"]


def test_one_real_tick_against_the_database(db, monkeypatch):
    class Real:
        def begin(self):
            class Tx:
                def __enter__(self):
                    return db

                def __exit__(self, *exc):
                    return False

            return Tx()

    assert tick({}, 0, worker.JOBS, Real()) == [j.name for j in worker.JOBS]


def test_daily_jobs_run_once_a_day_at_their_hour():
    from datetime import UTC, datetime

    from app.worker import DAILY_JOBS, DailyJob, tick_daily

    calls.clear()
    jobs = (DailyJob("early", 86400, f"{__name__}:ok_job", at_hour=2),
            DailyJob("late", 86400, f"{__name__}:ok_job", at_hour=8))
    last = {}
    assert tick_daily(last, datetime(2026, 9, 24, 1, 59, tzinfo=UTC), jobs, Sessions()) == []
    assert tick_daily(last, datetime(2026, 9, 24, 2, 0, tzinfo=UTC), jobs, Sessions()) == ["early"]
    assert tick_daily(last, datetime(2026, 9, 24, 2, 40, tzinfo=UTC), jobs, Sessions()) == []  # a restart
    assert tick_daily(last, datetime(2026, 9, 24, 8, 30, tzinfo=UTC), jobs, Sessions()) == ["late"]
    assert tick_daily(last, datetime(2026, 9, 24, 23, 0, tzinfo=UTC), jobs, Sessions()) == []
    assert tick_daily({}, datetime(2026, 9, 24, 23, 0, tzinfo=UTC), jobs, Sessions()) == []  # never catches up
    assert tick_daily(last, datetime(2026, 9, 25, 2, 30, tzinfo=UTC), jobs, Sessions()) == ["early"]
    for job in DAILY_JOBS:
        assert callable(job.load()), job.name


def test_real_daily_jobs_run_against_the_database(db):
    from datetime import UTC, datetime

    from app.worker import DAILY_JOBS, tick_daily

    class Real:
        def begin(self):
            class Tx:
                def __enter__(self):
                    return db

                def __exit__(self, *exc):
                    return False

            return Tx()

    last = {}
    for job in DAILY_JOBS:
        assert tick_daily(last, datetime(2026, 9, 24, job.at_hour, 5, tzinfo=UTC), DAILY_JOBS, Real()) == [job.name]


def test_worker_state_survives_a_restart(tmp_path):
    from app.worker import _load_state, _save_state

    path = tmp_path / "daily.json"
    assert _load_state(path) == {}
    _save_state(path, {"reconcile": "2026-09-24"})
    assert _load_state(path) == {"reconcile": "2026-09-24"}
    path.write_text("not json")
    assert _load_state(path) == {}
