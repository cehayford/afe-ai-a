"""Workstream C: re-verification, appeals, workload, visit routes, label checks, photos
seen elsewhere and the investigation graph."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import RuleViolation
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.detection import hooks
from app.modules.detection.models import DetectionLabel
from app.modules.identity.service import check_ghana_card
from app.modules.listings.models import ListingStatus
from app.modules.listings.service import publish, submit_for_review
from app.modules.notifications.providers import fake_outbox
from app.modules.ops import service as ops
from app.modules.ops.models import AppealStatus, LabelCheck
from app.modules.risk.flags import open_flags
from app.modules.units.service import register_unit
from app.modules.verification import service as verification
from app.modules.verification.models import VisitAssignment
from tests.conftest import PIN, accept_owner_authority, api_login, make_listing, make_user


@pytest.fixture
def live(db, verified_unit, verified_landlord, reviewer):
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    return publish(db, listing, reviewer)


# --- Re-verification -----------------------------------------------------------------------------------


def test_verified_homes_only_return_to_the_visit_queue_for_renewal(db, verified_unit):
    assert verified_unit not in verification.homes_needing_visit(db)
    visit = verification.latest_completed_visit(db, verified_unit)
    visit.completed_at -= timedelta(days=60)  # the visit is old, but the home is still verified
    db.flush()
    assert verified_unit not in verification.homes_needing_visit(db)
    current = verification.current_verification(db, unit=verified_unit)
    current.expires_at = utcnow() + timedelta(days=10)
    db.flush()
    assert verified_unit in verification.homes_needing_visit(db)


def test_reverify_warns_then_pauses(db, live, verified_landlord, verified_unit):
    current = verification.current_verification(db, unit=verified_unit)
    current.expires_at = utcnow() + timedelta(days=20)
    db.flush()
    assert ops.reverify(db) == {"warned": 1, "paused": 0}
    assert "ends on" in fake_outbox.last("sms", verified_landlord.phone).body
    assert ops.reverify(db)["warned"] == 0  # once
    current.expires_at = utcnow() - timedelta(minutes=1)
    db.flush()
    assert ops.reverify(db)["paused"] == 1
    assert live.status == ListingStatus.PAUSED and "expired" in live.status_reason


# --- Appeals -------------------------------------------------------------------------------------------------


def test_appeals(db, landlord, reviewer):
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    v = verification.decide_party(db, landlord, reviewer, False, ["ID_MISMATCH"], "Face does not match")
    items = ops.appealable(db, landlord)
    assert [(i["kind"], i["subject_id"]) for i in items] == [("verification", v.id)]
    reason = "The photo was taken in poor light; I can come to the office with my card."
    appeal = ops.open_appeal(db, landlord, "verification", v.id, reason)
    with pytest.raises(RuleViolation, match="already been appealed"):
        ops.open_appeal(db, landlord, "verification", v.id, reason)
    assert ops.appealable(db, landlord) == []
    with pytest.raises(RuleViolation, match="different reviewer"):
        ops.decide_appeal(db, reviewer, appeal, True, "Checked again in person at the office.")
    second = make_user(db, "reviewer2", Role.REVIEWER)
    ops.decide_appeal(db, second, appeal, True, "Checked the card in person at the office; it matches.")
    assert appeal.status == AppealStatus.UPHELD
    assert "upheld" in fake_outbox.last("sms", landlord.phone).body


def test_only_your_own_decisions_can_be_appealed(db, landlord, reviewer):
    other = make_user(db, "kojo", Role.LANDLORD)
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    v = verification.decide_party(db, landlord, reviewer, False, ["ID_MISMATCH"], "Face does not match")
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        ops.open_appeal(db, other, "verification", v.id, "This is not my decision but I want to appeal it anyway.")


# --- Workload and routes --------------------------------------------------------------------------------------


def test_workload(db, live):
    data = ops.workload(db)
    queues = {q["queue"]: q for q in data["queues"]}
    assert set(queues) >= {"Homes to visit", "Open flags", "Appeals", "Label checks"}
    assert data["homes_live_last_30_days"] == 1 and data["median_days_to_live"] is not None


def test_visit_routes(db, area, landlord, reviewer, verifier):
    homes = []
    for n, addr in enumerate(("GA-492-7424", "GA-492-7425", "GA-492-7426")):
        u = register_unit(db, landlord, area, addr, "", PIN[0] + n * 0.001, PIN[1], "house", 2)
        accept_owner_authority(db, u, landlord, reviewer)
        homes.append(u)
    plan = ops.plan_routes(db, date.today() + timedelta(days=1))
    assert len(plan["routes"]) == 1
    route = plan["routes"][0]
    assert route["verifier"].id == verifier.id and len(route["units"]) == 3 and route["km"] > 0
    done, problems = ops.assign_route(db, reviewer, verifier, route["units"], plan["day"])
    assert done == 3 and problems == []  # rotation compares with the last *completed* visit
    assert db.scalar(select(VisitAssignment).where(VisitAssignment.verifier_id == verifier.id))


# --- Label quality ----------------------------------------------------------------------------------------------


def test_disputed_labels_leave_training(db, monkeypatch, landlord, reviewer):
    monkeypatch.setattr(hooks, "label_sampled", lambda label_id, percent=5: True)
    lbl = hooks.label(db, landlord, fraud=True, source="verification", decided_by=reviewer)
    check = db.scalar(select(LabelCheck).where(LabelCheck.label_id == lbl.id))
    assert check.status == "pending"
    assert ops.label_checks_for(db, reviewer) == []  # not your own decision
    with pytest.raises(RuleViolation):
        ops.check_label(db, reviewer, check, True)
    second = make_user(db, "reviewer2", Role.REVIEWER)
    ops.check_label(db, second, check, False, "The card photo looked genuine to me")
    assert db.get(DetectionLabel, lbl.id).disputed


# --- Photos seen elsewhere ----------------------------------------------------------------------------------------


def test_external_photo_matches_flag_the_home(db, tmp_path, verified_unit):
    from app.modules.verification.models import FieldVisit, VisitPhoto

    ours = db.scalar(select(VisitPhoto.phash).join(FieldVisit).where(FieldVisit.unit_id == verified_unit.id))
    path = tmp_path / "crawl.csv"
    path.write_text(f"source,url,phash,dhash\nTonaton,https://example.com/1,{ours},\nJiji,https://example.com/2,0000000000000000,\n",
                    encoding="utf-8")
    assert ops.import_external_photos(db, str(path)) == {"imported": 2, "matched": 1}
    assert "photos.found_elsewhere" in [f.rule for f in open_flags(db, verified_unit)]


# --- Graph and API ---------------------------------------------------------------------------------------------------


def test_person_graph_and_api(client, db, landlord, reviewer):
    other = make_user(db, "impostor", Role.AGENT)
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    check_ghana_card(db, other, "GHA-712345678-3", other.name, selfie=b"s")
    from app.modules.detection.service import run_graph

    run_graph(db)
    graph = ops.person_graph(db, landlord)
    assert {n["id"] for n in graph["nodes"]} == {landlord.id, other.id}
    assert graph["edges"][0]["kind"] == "ghana_card"
    db.commit()
    h = api_login(client, "reviewer")
    assert client.get(f"/api/v1/review/people/{landlord.id}/graph", headers=h).status_code == 200
    assert client.get("/api/v1/review/workload", headers=h).json()["data"]["sla_days"] == 3
    assert client.get("/api/v1/review/visit-plan", headers=h).status_code == 200
    assert client.get("/api/v1/me/appealable", headers=api_login(client, "ama")).json()["data"] == []
