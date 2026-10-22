"""The weekly model report: one snapshot per model per ISO week, the seeded set alongside, and
reviewers told once."""

import dataclasses
from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.compliance import service as compliance
from app.modules.detection.hooks import label_key
from app.modules.detection.models import EvaluationSnapshot, ModelScore, ModelVersion
from app.modules.detection.reports import iso_week, take_snapshots, weekly_models
from app.modules.notifications.models import Notification
from tests.conftest import api_login, make_listing
from tests.test_detection import seed_evaluation

MONDAY = datetime(2026, 10, 12, 5, tzinfo=UTC)  # ISO week 2026-W42


def test_iso_week():
    assert iso_week(MONDAY) == "2026-W42"


def test_one_row_per_model_per_week_and_one_notice(db, reviewer):
    seed_evaluation(db, reviewer)
    first, created = take_snapshots(db, MONDAY)
    again, created_again = take_snapshots(db, MONDAY.replace(hour=9))
    assert created and not created_again
    rows = db.scalars(select(EvaluationSnapshot)).all()
    assert len(rows) == len(first) == len(again) == 6
    price = next(r for r in rows if r.detector == "price")
    assert price.week == "2026-W42" and price.promotable and price.labels == 30
    assert price.model["recall"] == 1.0 and price.rules["recall"] == 0.5
    notes = db.scalars(select(Notification).where(Notification.template == "model_report")).all()
    assert len(notes) == 1 and notes[0].user_id == reviewer.id
    assert "1 of 6 models could leave shadow (price)" in notes[0].body


def test_a_broken_seeded_file_is_named_in_the_notice_not_hidden(db, reviewer, tmp_path):
    broken = tmp_path / "cases.json"
    broken.write_text("{not json", encoding="utf-8")
    rows, _ = take_snapshots(db, MONDAY, seeded_path=broken)
    assert all(r.seeded is None for r in rows)
    body = db.scalar(select(Notification.body).where(Notification.template == "model_report"))
    assert "The seeded test set didn't load" in body and "misses" not in body


def test_seeded_results_ride_along(db, reviewer):
    rows, _ = take_snapshots(db, MONDAY)
    by_model = {r.detector: r for r in rows}
    assert by_model["scam_text"].seeded["cases"] >= 12
    assert by_model["photos"].seeded is None  # the seeded set has no photo cases yet


def labelled_text(db, unit, landlord, reviewer, scored=False):
    """Six scam listings and six genuine ones, decided by a reviewer: enough to train on. With
    `scored`, the current wording version scored each one before the decision, so it can be judged."""
    for i in range(6):
        cases = ((True, f"Room {i}", "Send momo commitment fee first, viewing after"),
                 (False, f"Flat {i}", "Quiet compound with a water tank"))
        for fraud, title, text in cases:
            listing = make_listing(db, unit, landlord, title=title, description=text)
            if scored:
                db.add(ModelScore(detector="scam_text", version="features-1", subject_type="listings",
                                  subject_id=str(listing.id), score=90 if fraud else 10, reasons=[], mode="shadow"))
                db.flush()
            label_key(db, "listings", str(listing.id), fraud, "verification", reviewer)


def set_rule(monkeypatch, key, value):
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default=value))


def test_weekly_job_waits_for_monday(db):
    tuesday = datetime(2026, 10, 13, 5, tzinfo=UTC)
    assert weekly_models(db, tuesday) == {"ran": False, "why": "the weekly report runs on Mondays"}
    assert db.scalar(select(EvaluationSnapshot)) is None


def test_weekly_job_reports_and_retrains_once_in_shadow(db, monkeypatch, unit, landlord, reviewer):
    set_rule(monkeypatch, "model_min_labels", 12)
    labelled_text(db, unit, landlord, reviewer, scored=True)
    out = weekly_models(db, MONDAY)
    assert out == {"ran": True, "week": "2026-W42", "snapshots": 6, "trained": "nb-1"}
    again = weekly_models(db, MONDAY.replace(hour=9))
    assert again["trained"] == "already ran this week"
    assert len(db.scalars(select(ModelVersion)).all()) == 1


def test_an_acting_model_is_not_retrained_automatically(db, monkeypatch, unit, landlord, reviewer):
    labelled_text(db, unit, landlord, reviewer)
    key = "model_scam_text_mode"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default="canary"))
    out = weekly_models(db, MONDAY)
    assert out["trained"] == "not trained: the model is acting, so a reviewer retrains it"
    assert db.scalar(select(ModelVersion)) is None


def test_a_version_is_judged_before_it_is_replaced(db, unit, landlord, reviewer):
    labelled_text(db, unit, landlord, reviewer)  # decided, but the current version scored none of them
    out = weekly_models(db, MONDAY)
    assert out["trained"] == (
        "not trained: the current version has 0 of 30 decided cases; it is judged before a new one replaces it"
    )
    assert db.scalar(select(ModelVersion)) is None


def test_too_few_labels_is_reported_not_raised(db, monkeypatch):
    set_rule(monkeypatch, "model_min_labels", 0)
    out = weekly_models(db, MONDAY)
    assert out["ran"] and out["trained"].startswith("not trained: Not enough labelled text")


def test_history_over_the_api(client, db, reviewer):
    seed_evaluation(db, reviewer)
    take_snapshots(db, MONDAY)
    db.flush()
    h = api_login(client, "reviewer")
    rows = client.get("/api/v1/review/detection/history", headers=h).json()["data"]
    price = next(r for r in rows if r["detector"] == "price")
    assert price["week"] == "2026-W42" and price["model"]["recall"] == 1.0 and price["promotable"]
    assert next(r for r in rows if r["detector"] == "scam_text")["seeded"]["cases"] >= 12
    assert client.get("/api/v1/review/detection/history").status_code == 401
