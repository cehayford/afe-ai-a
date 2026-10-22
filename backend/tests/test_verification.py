import io
from datetime import timedelta

import pytest
from PIL import Image

from app.core.errors import InvalidInput, NotAllowed, RuleViolation
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.identity.models import CheckStatus
from app.modules.identity.service import check_ghana_card
from app.modules.media.storage import storage
from app.modules.risk.flags import open_flags
from app.modules.units.models import DocumentType, Relationship
from app.modules.units.service import add_authority, register_unit, review_authority
from app.modules.verification.models import CHECKLIST_ITEMS, VisitOutcome
from app.modules.verification.service import (
    add_visit_photo,
    complete_visit,
    current_verification,
    decide_party,
    decide_unit,
    homes_awaiting_decision,
    is_verified,
    people_awaiting_decision,
    start_visit,
)
from tests.conftest import PDF, accept_owner_authority, assign, begin_visit, make_user, passed_visit, photo_bytes

# --- Units: one home, one record --------------------------------------------------------------


def test_unit_is_registered_once(db, unit, landlord):
    with pytest.raises(RuleViolation, match="already registered"):
        register_unit(db, landlord, unit.area, "ga4927424", "Flat 2B", *unit.point, "apartment", 2)


def test_unit_must_be_inside_an_active_area(db, area, landlord):
    with pytest.raises(InvalidInput, match="outside East Legon"):
        register_unit(db, landlord, area, "GA-557-0192", "", 5.6874, -0.1661, "house", 3)
    area.is_active = False
    with pytest.raises(RuleViolation, match="not open"):
        register_unit(db, landlord, area, "GA-418-3310", "", 5.6331, -0.1662, "house", 3)


# --- Identity ------------------------------------------------------------------------------------


def test_ghana_card_is_hashed_not_stored(db, landlord):
    check = check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    assert check.status == CheckStatus.PASSED
    assert "712345678" not in check.card_number_hash
    assert check.masked_card == "GHA-••••••678-3"


def test_same_ghana_card_on_two_accounts_is_blocked_and_flagged(db, landlord):
    other = make_user(db, "impostor", Role.AGENT)
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    second = check_ghana_card(db, other, "GHA-712345678-3", other.name, selfie=b"s")
    assert second.status == CheckStatus.FAILED
    assert [f.rule for f in open_flags(db, landlord)] == ["identity.duplicate_ghana_card"]
    assert [f.rule for f in open_flags(db, other)] == ["identity.duplicate_ghana_card"]


def test_party_approval_needs_passed_check_with_liveness(db, landlord, reviewer):
    with pytest.raises(RuleViolation, match="no passed Ghana Card"):
        decide_party(db, landlord, reviewer, True, ["ID_MATCH"])
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=None)
    with pytest.raises(RuleViolation, match="liveness"):
        decide_party(db, landlord, reviewer, True, ["ID_MATCH"])


def test_decisions_need_matching_reason_codes(db, landlord, reviewer):
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    with pytest.raises(RuleViolation, match="at least one"):
        decide_party(db, landlord, reviewer, True, [])
    with pytest.raises(RuleViolation, match="approval codes"):
        decide_party(db, landlord, reviewer, True, ["ID_MISMATCH"])
    with pytest.raises(RuleViolation, match="note"):
        decide_party(db, landlord, reviewer, False, ["OTHER"])


def test_only_reviewers_decide(db, landlord, verifier):
    with pytest.raises(NotAllowed):
        decide_party(db, landlord, verifier, True, ["ID_MATCH"])


def test_latest_decision_wins_and_badges_expire(db, verified_landlord, reviewer):
    assert is_verified(db, party=verified_landlord)
    decide_party(db, verified_landlord, reviewer, False, ["ID_MISMATCH"])
    assert not is_verified(db, party=verified_landlord)

    v = decide_party(db, verified_landlord, reviewer, True, ["ID_MATCH"])
    assert is_verified(db, party=verified_landlord)
    v.expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    assert current_verification(db, party=verified_landlord) is None


# --- Authority --------------------------------------------------------------------------------------


def test_agent_authority_needs_owner_callback(db, unit, reviewer):
    agent = make_user(db, "kofi", Role.AGENT)
    record = add_authority(db, agent, unit, Relationship.AUTHORISED_AGENT, DocumentType.OWNER_AUTHORISATION, PDF)
    with pytest.raises(RuleViolation, match="owner confirmed"):
        review_authority(db, record, reviewer, True)


def test_owner_needs_ownership_document_not_a_letter(db, unit, landlord, reviewer):
    record = add_authority(db, landlord, unit, Relationship.OWNER, DocumentType.OWNER_AUTHORISATION, PDF)
    with pytest.raises(RuleViolation):
        review_authority(db, record, reviewer, True)


def test_authority_documents_are_private_and_type_checked(db, unit, landlord):
    record = add_authority(db, landlord, unit, Relationship.OWNER, DocumentType.INDENTURE, PDF)
    assert storage.read("private", record.document_key) == PDF
    with pytest.raises(InvalidInput, match="PDF, JPEG or PNG"):
        add_authority(db, landlord, unit, Relationship.OWNER, DocumentType.INDENTURE, b"MZ\x90 executable")
    with pytest.raises(ValueError, match="escapes"):
        storage.path("private", "../../etc/passwd")


# --- Field visits and photos -----------------------------------------------------------------------


def test_visit_must_start_at_the_property(db, unit, verifier):
    with pytest.raises(RuleViolation, match="from the unit's pin"):
        begin_visit(db, unit, verifier, float(unit.lat) + 0.01, float(unit.lng))  # about 1.1 km away


def test_only_field_verifiers_visit(db, unit, landlord):
    with pytest.raises(NotAllowed):
        start_visit(db, unit, landlord, *unit.point)


def test_photos_are_checked_for_place_and_time(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    with pytest.raises(RuleViolation, match="from the unit's pin"):
        add_visit_photo(db, visit, verifier, photo_bytes(1), float(unit.lat) + 0.01, float(unit.lng), utcnow())
    with pytest.raises(RuleViolation, match="outside this visit"):
        add_visit_photo(db, visit, verifier, photo_bytes(1), *unit.point, visit.started_at - timedelta(hours=1))


def test_photo_metadata_is_stripped(db, unit, verifier):
    exif = Image.Exif()
    exif[0x0110] = "Tecno Spark 10"  # camera model
    visit = begin_visit(db, unit, verifier)
    photo = add_visit_photo(db, visit, verifier, photo_bytes(2, exif=exif.tobytes()), *unit.point, utcnow())
    with Image.open(io.BytesIO(storage.read("public", photo.image_key))) as stored:
        assert stored.format == "WEBP"
        assert not stored.getexif()
        assert (stored.width, stored.height) == (photo.width, photo.height)


def test_rejects_files_that_are_not_photos(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    with pytest.raises(InvalidInput):
        add_visit_photo(db, visit, verifier, b"%PDF-1.4 not a photo", *unit.point, utcnow())


def test_passing_a_visit_needs_enough_photos(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    with pytest.raises(RuleViolation, match="at least 4 photos"):
        complete_visit(db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, True))


def test_unticked_checklist_fails_the_visit(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    visit = complete_visit(db, visit, verifier, {"unit_exists": True, "unit_vacant": False})
    assert visit.outcome == VisitOutcome.FAILED


def test_verifier_can_fail_a_visit_whose_checks_passed_with_a_reason(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    with pytest.raises(RuleViolation, match="every check is yes"):
        complete_visit(db, visit, verifier, {"unit_exists": False}, result="pass")
    with pytest.raises(RuleViolation, match="from the list"):
        complete_visit(db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, True), result="fail", fail_reason="VISIT_MATCH")
    # No photos needed to fail; the reason code leads the notes for the reviewer.
    visit = complete_visit(
        db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, True), "Caretaker only.", result="fail", fail_reason="UNIT_MISMATCH"
    )
    assert visit.outcome == VisitOutcome.FAILED
    assert visit.notes == "Fail reason: UNIT_MISMATCH (Unit does not match what was described). Caretaker only."


def test_photo_reused_across_homes_is_flagged(db, area, unit, landlord, verifier):
    other = register_unit(db, landlord, area, "GA-418-3310", "", 5.6331, -0.1662, "house", 2)
    first = begin_visit(db, unit, verifier)
    add_visit_photo(db, first, verifier, photo_bytes(7), *unit.point, utcnow())
    second = begin_visit(db, other, verifier)
    photo = add_visit_photo(db, second, verifier, photo_bytes(7, fmt="PNG"), *other.point, utcnow())
    assert photo.duplicate_of_id is not None
    assert [f.rule for f in open_flags(db, other)] == ["photos.duplicate_of_other_unit"]


# --- Unit decisions -----------------------------------------------------------------------------------


def test_unit_approval_needs_authority_and_visit(db, unit, verified_landlord, reviewer, verifier):
    with pytest.raises(RuleViolation, match="No accepted ownership"):
        decide_unit(db, unit, reviewer, True, ["VISIT_MATCH"])
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    with pytest.raises(RuleViolation, match="did not pass"):
        decide_unit(db, unit, reviewer, True, ["VISIT_MATCH"])
    passed_visit(db, unit, verifier)
    decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    assert is_verified(db, unit=unit)


def test_verifier_cannot_approve_own_visit(db, unit, verified_landlord, reviewer):
    both = make_user(db, "both", Role.FIELD_VERIFIER)
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    passed_visit(db, unit, both)
    both.role = Role.REVIEWER  # a verifier later promoted to reviewer
    with pytest.raises(RuleViolation, match="cannot also approve"):
        decide_unit(db, unit, both, True, ["VISIT_MATCH"])


def test_old_visits_cannot_be_used(db, unit, verified_landlord, reviewer, verifier):
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    visit = passed_visit(db, unit, verifier)
    visit.completed_at = utcnow() - timedelta(days=45)
    db.flush()
    with pytest.raises(RuleViolation, match="too old"):
        decide_unit(db, unit, reviewer, True, ["VISIT_MATCH"])


def test_high_flags_block_approval(db, area, unit, verified_landlord, reviewer, verifier):
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    other = register_unit(db, verified_landlord, area, "GA-418-3310", "", 5.6331, -0.1662, "house", 2)
    passed_visit(db, other, verifier, seed=3)
    passed_visit(db, unit, verifier, seed=3)  # same photos as the other home
    with pytest.raises(RuleViolation, match="high-severity"):
        decide_unit(db, unit, reviewer, True, ["VISIT_MATCH"])


def test_review_queue_shows_new_evidence_only(db, unit, landlord, reviewer, verifier):
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    assert [u.id for u, _ in people_awaiting_decision(db)] == [landlord.id]
    decide_party(db, landlord, reviewer, True, ["ID_MATCH"])
    assert people_awaiting_decision(db) == []

    passed_visit(db, unit, verifier)
    assert [u.id for u, _ in homes_awaiting_decision(db)] == [unit.id]
    decide_unit(db, unit, reviewer, False, ["DOCS_MISSING"])
    assert homes_awaiting_decision(db) == []


# --- Visit assignments ------------------------------------------------------------------------------


def test_visits_need_an_assignment(db, unit, verifier):
    with pytest.raises(RuleViolation, match="not assigned to you"):
        start_visit(db, unit, verifier, *unit.point)
    other = make_user(db, "other-verifier", Role.FIELD_VERIFIER)
    assign(db, unit, other)
    with pytest.raises(RuleViolation, match="not assigned to you"):
        start_visit(db, unit, verifier, *unit.point)


def test_only_reviewers_assign_and_one_open_assignment_per_home(db, unit, verifier, reviewer, landlord):
    from app.modules.verification.service import assign_visit

    with pytest.raises(NotAllowed):
        assign_visit(db, unit, verifier, verifier, utcnow().date())
    assign_visit(db, unit, verifier, reviewer, utcnow().date())
    with pytest.raises(RuleViolation, match="already has an open"):
        assign_visit(db, unit, make_user(db, "v2", Role.FIELD_VERIFIER), reviewer, utcnow().date())
    with pytest.raises(RuleViolation, match="active field verifier"):
        assign_visit(db, unit, landlord, reviewer, utcnow().date())


def test_verifier_cannot_visit_own_home(db, area, reviewer):
    from app.modules.verification.service import assign_visit

    moonlighter = make_user(db, "moonlighter", Role.FIELD_VERIFIER)
    home = register_unit(db, moonlighter, area, "GA-418-3310", "", 5.6331, -0.1662, "house", 2)
    with pytest.raises(RuleViolation, match="own or let"):
        assign_visit(db, home, moonlighter, reviewer, utcnow().date())


def test_verifiers_rotate_between_landlords(db, area, unit, landlord, verifier, reviewer, monkeypatch):
    from app.config import get_settings
    from app.modules.verification.service import assign_visit

    monkeypatch.setattr(get_settings(), "rotate_verifiers", True)
    passed_visit(db, unit, verifier)
    second_home = register_unit(db, landlord, area, "GA-418-3310", "", 5.6331, -0.1662, "house", 2)
    with pytest.raises(RuleViolation, match="did the last visit for this landlord"):
        assign_visit(db, second_home, verifier, reviewer, utcnow().date())
    assign_visit(db, second_home, make_user(db, "akosua", Role.FIELD_VERIFIER), reviewer, utcnow().date())


def test_completing_a_visit_closes_its_assignment(db, unit, verifier):
    from app.modules.verification.models import AssignmentStatus

    assignment = assign(db, unit, verifier)
    visit = passed_visit(db, unit, verifier)
    assert visit.assignment_id == assignment.id
    assert assignment.status == AssignmentStatus.DONE


def test_retries_are_safe(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    assert start_visit(db, unit, verifier, *unit.point).id == visit.id  # double tap resumes
    first = add_visit_photo(db, visit, verifier, photo_bytes(5), *unit.point, utcnow(), client_ref="abc-1")
    again = add_visit_photo(db, visit, verifier, photo_bytes(5), *unit.point, utcnow(), client_ref="abc-1")
    assert again.id == first.id and len(visit.photos) == 1


def test_phone_clock_drift_is_tolerated(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    add_visit_photo(db, visit, verifier, photo_bytes(6), *unit.point, utcnow() + timedelta(seconds=90))
    with pytest.raises(RuleViolation, match="outside this visit"):
        add_visit_photo(db, visit, verifier, photo_bytes(7), *unit.point, utcnow() + timedelta(minutes=10))


def test_homes_needing_visit(db, unit, landlord, verifier, reviewer):
    from app.modules.verification.service import homes_needing_visit

    assert homes_needing_visit(db) == []  # no documents yet
    add_authority(db, landlord, unit, Relationship.OWNER, DocumentType.INDENTURE, PDF)
    assert homes_needing_visit(db) == [unit]
    assign(db, unit, verifier)
    assert homes_needing_visit(db) == []
