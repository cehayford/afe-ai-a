import pytest
from sqlalchemy import delete, update

from app.core.errors import InvalidInput
from app.core.geo import distance_m, polygon_contains
from app.core.ghana import format_ghs, normalise_digital_address, normalise_ghana_card, normalise_phone
from app.core.security import create_access_token, hash_password, read_access_token, verify_password
from app.modules.audit.log import record
from app.modules.audit.models import AuditEvent
from tests.conftest import EAST_LEGON


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("GA-183-8164", "GA-183-8164"), ("ga1838164", "GA-183-8164"), (" GE 2314 383 2 ", "GE-2314-3832")],
)
def test_digital_address(raw, expected):
    assert normalise_digital_address(raw) == expected


@pytest.mark.parametrize("raw", ["", "G-183-8164", "GA-18-8164", "Accra"])
def test_digital_address_rejects(raw):
    with pytest.raises(InvalidInput):
        normalise_digital_address(raw)


def test_ghana_card_and_phone():
    assert normalise_ghana_card("gha 712345678 3") == "GHA-712345678-3"
    assert normalise_phone("024 412 3456") == "+233244123456"
    assert normalise_phone("+233 24 412 3456") == "+233244123456"
    with pytest.raises(InvalidInput):
        normalise_phone("12345")


def test_money_format():
    assert format_ghs(480_000) == "GH₵4,800"
    assert format_ghs(1_050) == "GH₵10.50"


def test_polygon_and_distance():
    polygon = [tuple(p) for p in EAST_LEGON]
    assert polygon_contains(polygon, (5.64, -0.158))
    assert not polygon_contains(polygon, (5.70, -0.158))  # Madina is outside East Legon
    assert 100 < distance_m((5.6402, -0.1583), (5.6412, -0.1583)) < 120


def test_passwords_and_tokens():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password", stored)
    assert not verify_password("anything", "garbage")
    assert read_access_token(create_access_token(42)) == 42
    assert read_access_token("not-a-token") is None


def test_audit_events_are_append_only(db, landlord):
    db.commit()  # keep the user when the failed changes below are rolled back
    event = record(db, landlord, "test.action", landlord, note="x")
    event.action = "changed"
    with pytest.raises(PermissionError):
        db.flush()
    db.rollback()
    event = record(db, landlord, "test.action", landlord)
    db.delete(event)
    with pytest.raises(PermissionError):
        db.flush()
    db.rollback()
    with pytest.raises(PermissionError):
        db.execute(delete(AuditEvent))
    with pytest.raises(PermissionError):
        db.execute(update(AuditEvent).values(action="changed"))
