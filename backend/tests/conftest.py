import io
import os
import random
import tempfile
from datetime import date, timedelta
from pathlib import Path

# Settings are read once at import, so configure the environment before importing the app.
_TMP = Path(tempfile.mkdtemp(prefix="afe-tests-"))
os.environ.update(
    AFE_DEBUG="1",
    AFE_SECRET_KEY="test-secret-key-that-is-at-least-32-chars",
    AFE_DATABASE_URL=f"sqlite:///{_TMP / 'unused.db'}",
    AFE_MEDIA_ROOT=str(_TMP / "media"),
    AFE_PRIVATE_MEDIA_ROOT=str(_TMP / "private"),
    AFE_PASSWORD_SCRYPT_N="16",  # speed only; production uses 2**14 or more
    AFE_KYC_PROVIDER="app.modules.identity.providers.FakeKycProvider",
    # Rotation is tested on its own (test_verification); other tests reuse one verifier.
    AFE_ROTATE_VERIFIERS="0",
    # Two-step sign-in is tested on its own (test_auth); other tests sign in with one step.
    AFE_MFA_ENFORCED="0",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402, F401
from app.db import Base, get_db, utcnow  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.accounts.models import Role, User  # noqa: E402
from app.modules.accounts.service import create_user  # noqa: E402
from app.modules.areas.models import PriceBand, ServiceArea  # noqa: E402
from app.modules.identity.service import check_ghana_card  # noqa: E402
from app.modules.listings.service import create_draft  # noqa: E402
from app.modules.units.models import DocumentType, PropertyType, Relationship  # noqa: E402
from app.modules.units.service import add_authority, register_unit, review_authority  # noqa: E402
from app.modules.verification.models import CHECKLIST_ITEMS  # noqa: E402
from app.modules.verification.service import (  # noqa: E402
    add_visit_photo,
    assign_visit,
    complete_visit,
    decide_party,
    decide_unit,
    open_assignment,
    start_visit,
)

EAST_LEGON = [[5.624, -0.176], [5.624, -0.140], [5.658, -0.140], [5.658, -0.176]]
PIN = (5.6402, -0.1583)
PASSWORD = "x-test-password"
PDF = b"%PDF-1.4 test document"


@pytest.fixture(autouse=True)
def _clear_outbox():
    from app.modules.notifications.providers import fake_outbox

    fake_outbox.clear()


@pytest.fixture
def db():
    """In-memory SQLite by default. Set AFE_TEST_DATABASE_URL (e.g. a CI PostgreSQL
    service) to run the same tests against PostgreSQL; each test gets fresh tables."""
    url = os.environ.get("AFE_TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def _fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        yield session
    if url:
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db):
    app = create_app()

    def _db():
        yield db
        db.commit()

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c


def photo_bytes(seed: int, fmt: str = "JPEG", exif: bytes | None = None) -> bytes:
    rng = random.Random(seed)
    img = Image.new("RGB", (800, 600), tuple(rng.randint(120, 240) for _ in range(3)))
    d = ImageDraw.Draw(img)
    for _ in range(6):
        x, y = rng.randint(0, 700), rng.randint(0, 500)
        d.rectangle(
            [x, y, x + rng.randint(50, 300), y + rng.randint(50, 300)],
            fill=tuple(rng.randint(0, 255) for _ in range(3)),
        )
    buf = io.BytesIO()
    img.save(buf, format=fmt, **({"exif": exif} if exif else {}))
    return buf.getvalue()


def make_user(db, username, role, phone=None):
    return create_user(db, username, PASSWORD, role, username.title(), phone)


@pytest.fixture
def area(db):
    a = ServiceArea(slug="east-legon", name="East Legon", city="Accra", is_active=True, boundary=EAST_LEGON)
    db.add(a)
    db.flush()
    db.add(
        PriceBand(
            area_id=a.id,
            bedrooms=2,
            low_pesewas=350_000,
            median_pesewas=500_000,
            high_pesewas=750_000,
            as_of=date.today(),
        )
    )
    db.flush()
    return a


@pytest.fixture
def reviewer(db):
    return make_user(db, "reviewer", Role.REVIEWER)


@pytest.fixture
def verifier(db):
    return make_user(db, "verifier", Role.FIELD_VERIFIER)


@pytest.fixture
def landlord(db):
    return make_user(db, "ama", Role.LANDLORD, phone="0244123456")


@pytest.fixture
def verified_landlord(db, landlord, reviewer):
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"selfie")
    decide_party(db, landlord, reviewer, True, ["ID_MATCH"])
    return landlord


@pytest.fixture
def unit(db, area, landlord):
    return register_unit(db, landlord, area, "GA-492-7424", "Flat 2B", PIN[0], PIN[1], PropertyType.APARTMENT, 2)


def accept_owner_authority(db, unit, party, reviewer):
    record = add_authority(db, party, unit, Relationship.OWNER, DocumentType.INDENTURE, PDF)
    return review_authority(db, record, reviewer, True)


def assign(db, unit, verifier):
    boss = db.scalar(select(User).where(User.username == "assigner")) or make_user(db, "assigner", Role.REVIEWER)
    return open_assignment(db, unit, verifier) or assign_visit(db, unit, verifier, boss, date.today())


def begin_visit(db, unit, verifier, lat=None, lng=None):
    """Assign the home to the verifier (as a reviewer would), then check in."""
    assign(db, unit, verifier)
    return start_visit(db, unit, verifier, lat if lat is not None else unit.lat, lng if lng is not None else unit.lng)


def passed_visit(db, unit, verifier, seed=0):
    visit = begin_visit(db, unit, verifier)
    for n in range(4):
        add_visit_photo(db, visit, verifier, photo_bytes(seed * 10 + n), *unit.point, utcnow())
    return complete_visit(db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, True))


@pytest.fixture
def verified_unit(db, unit, verified_landlord, reviewer, verifier):
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    passed_visit(db, unit, verifier)
    decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    return unit


def make_listing(db, unit, lister, **overrides):
    fields = dict(
        title="2-bedroom flat",
        description="Quiet compound with water tank.",
        rent_pesewas=480_000,
        advance_months=6,
        min_lease_months=12,
        available_from=date.today() + timedelta(days=14),
    )
    fields.update(overrides)
    return create_draft(db, lister, unit, **fields)


def api_login(client, username, password=PASSWORD) -> dict:
    res = client.post("/api/v1/auth/signin/password", json={"login": username, "password": password})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "signed_in", data
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
def charges_on(monkeypatch):
    """End the launch offer, so Afe's charges apply (the default is free until 5 Jun 2027)."""
    import dataclasses

    from app.modules.compliance import service as compliance

    key = "free_period_until"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default="2026-01-01"))
