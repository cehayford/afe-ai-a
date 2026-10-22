"""Whole-system checks: demo data, the public API over it, reviewer tools, migrations."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select

from app.db import Base
from app.modules.listings.models import Listing, ListingStatus
from app.modules.notifications.models import Notification
from app.seed import DEMO_PASSWORD, seed_demo
from tests.conftest import api_login


def test_seed_demo_runs_the_full_flow(db):
    assert seed_demo(db) == 4
    assert len(db.scalars(select(Listing).where(Listing.status == ListingStatus.LIVE)).all()) == 4
    assert db.scalar(select(Notification).where(Notification.template == "viewing_requested")) is not None
    assert seed_demo(db) == 0  # idempotent


def test_public_api_over_demo_data(client, db):
    seed_demo(db)
    db.commit()
    found = client.get("/api/v1/properties/search").json()
    assert found["meta"]["count"] == 4 and all(li["cover_url"] for li in found["data"])
    madina = client.get("/api/v1/properties/search", params={"area": "madina-adenta", "bedrooms": 0}).json()
    assert [li["area_slug"] for li in madina["data"]] == ["madina-adenta"]

    ref = found["data"][0]["reference"]
    detail = client.get(f"/api/v1/properties/{ref}").json()["data"]
    assert detail["verification"][-1]["text"] == "Photos taken by Afe"
    assert client.get(detail["photos"][0]["url"]).headers["content-type"] == "image/webp"
    assert client.get("/api/v1/check", params={"q": "0244123456"}).json()["data"]["verified"]

    listing = db.scalar(select(Listing).where(Listing.reference == ref))
    listing.status = ListingStatus.PAUSED
    db.commit()
    assert client.get(f"/api/v1/properties/{ref}").status_code == 404


def test_reviewer_tools_over_demo_data(client, db):
    seed_demo(db)
    db.commit()
    efua = api_login(client, "reviewer", DEMO_PASSWORD)
    queue = client.get("/api/v1/review/queue", headers=efua).json()["data"]
    visits = [a for a in queue["assignments"] if a["purpose"] == "verification"]
    rechecks = [a for a in queue["assignments"] if a["purpose"] == "qa_recheck"]
    assert len(queue["homes_to_visit"]) == 1 and len(visits) == 1
    assert len(rechecks) <= 1  # the demo's approvals may draw an unannounced re-check (15%)

    home_id = visits[0]["unit"]["id"]
    home = client.get(f"/api/v1/review/units/{home_id}", headers=efua).json()["data"]
    doc = client.get(f"/api/v1/review/authority/{home['authorities'][0]['id']}/document", headers=efua)
    assert doc.status_code == 200 and doc.content.startswith(b"%PDF") and doc.headers["cache-control"] == "no-store"
    codes = client.get("/api/v1/review/reason-codes", headers=efua).json()["data"]
    assert {"code": "ID_MATCH", "label": "Ghana Card checked and name matches", "approval": True} in codes
    assert len(client.get("/api/v1/review/verifiers", headers=efua).json()["data"]) == 2

    ama = api_login(client, "ama", DEMO_PASSWORD)
    assert (
        client.get(f"/api/v1/review/authority/{home['authorities'][0]['id']}/document", headers=ama).status_code == 403
    )


def test_field_worklist_over_demo_data(client, db):
    seed_demo(db)
    db.commit()
    kwame = api_login(client, "verifier", DEMO_PASSWORD)
    work = client.get("/api/v1/verify/worklist", headers=kwame).json()["data"]
    visits = [a for a in work["assignments"] if a["purpose"] == "verification"]
    assert [a["unit"]["digital_address"] for a in visits] == ["GA-431-6620"]
    # Re-checks go to a different verifier from the one who passed the home.
    assert all(a["purpose"] == "qa_recheck" for a in work["assignments"] if a not in visits)
    a = visits[0]
    assert client.get(f"/api/v1/verify/assignments/{a['id']}", headers=kwame).json()["data"]["landlord_phone"]
    akosua = api_login(client, "verifier2", DEMO_PASSWORD)
    assert client.get(f"/api/v1/verify/assignments/{a['id']}", headers=akosua).status_code == 404


def test_migrations_match_the_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []
