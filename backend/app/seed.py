"""Demo data, loaded by running the real verification flow end to end.

Every step goes through the same services the product uses, so a successful run doubles
as a smoke test of the whole Phase 1 journey. Development only.
"""

import io
import random
from datetime import date, datetime, time, timedelta

from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.totp import now_code
from app.db import utcnow
from app.modules.accounts.models import MFA_ROLES, Role, User
from app.modules.accounts.service import create_user
from app.modules.areas.models import PriceBand, ServiceArea
from app.modules.detection.service import process_pending
from app.modules.enquiries.service import (
    complete_viewing,
    request_viewing,
    respond_viewing,
    save_listing,
    start_enquiry,
)
from app.modules.identity.service import check_ghana_card
from app.modules.listings.service import create_draft, publish, submit_for_review
from app.modules.scamcheck.service import report
from app.modules.tenancies.service import set_payee
from app.modules.units.models import DocumentType, PropertyType, Relationship
from app.modules.units.service import add_authority, confirm_owner_by_phone, register_unit, review_authority
from app.modules.verification.models import CHECKLIST_ITEMS
from app.modules.verification.service import (
    add_visit_photo,
    assign_visit,
    complete_visit,
    decide_party,
    decide_unit,
    start_visit,
)

DEMO_PASSWORD = "afe-demo-password"  # noqa: S105 - development data only
# Authenticator secret shared by the demo landlords and staff. Get the current code with
# `python -m app.cli totp`, or add this secret to an authenticator app.
DEMO_TOTP_SECRET = "AFEDEMOAFEDEMOAFEDEMOAFEDEMOAFED"  # noqa: S105 - development data only

AREAS = [
    ("east-legon", "East Legon", True, [[5.624, -0.176], [5.624, -0.140], [5.658, -0.140], [5.658, -0.176]]),
    ("madina-adenta", "Madina / Adenta", True, [[5.662, -0.190], [5.662, -0.140], [5.712, -0.140], [5.712, -0.190]]),
    ("spintex", "Spintex", False, [[5.628, -0.120], [5.628, -0.070], [5.650, -0.070], [5.650, -0.120]]),
]

# GH₵ per month: (low, median, high) by bedrooms. Placeholders until the W1–4 rent survey.
BANDS = {
    "east-legon": {0: (900, 1300, 1800), 1: (2000, 3000, 4500), 2: (3500, 5000, 7500), 3: (6000, 8500, 12000)},
    "madina-adenta": {0: (500, 750, 1100), 1: (1000, 1500, 2200), 2: (1800, 2600, 3800), 3: (3000, 4200, 6000)},
}

HOMES = [
    {
        "area": "east-legon",
        "address": "GA-492-7424",
        "label": "Flat 2B",
        "lat": 5.6402,
        "lng": -0.1583,
        "type": PropertyType.APARTMENT,
        "beds": 2,
        "rent": 4800,
        "title": "Bright 2-bedroom flat near A&C Mall",
        "desc": "Second-floor flat in a quiet gated compound. Tiled throughout, fitted kitchen, two bathrooms, "
        "water tank and a reliable ECG prepaid meter. Security at the gate day and night.",
    },
    {
        "area": "east-legon",
        "address": "GA-418-3310",
        "label": "Whole property",
        "lat": 5.6331,
        "lng": -0.1662,
        "type": PropertyType.SELF_CONTAINED,
        "beds": 1,
        "rent": 2600,
        "title": "Self-contained 1-bedroom, Lagos Avenue",
        "desc": "Self-contained unit with its own entrance, kitchenette and shower. Walking distance to Lagos "
        "Avenue shops and the trotro stop.",
    },
    {
        "area": "madina-adenta",
        "address": "GA-557-0192",
        "label": "Boys quarters",
        "lat": 5.6874,
        "lng": -0.1661,
        "type": PropertyType.CHAMBER_AND_HALL,
        "beds": 0,
        "rent": 800,
        "title": "Chamber and hall near Madina Zongo Junction",
        "desc": "Chamber and hall in a shared compound with its own kitchen corner and toilet. Five minutes' "
        "walk from the main road. Suits a student or young worker.",
    },
    {
        "area": "madina-adenta",
        "address": "GE-231-4383",
        "label": "Whole property",
        "lat": 5.7021,
        "lng": -0.1705,
        "type": PropertyType.HOUSE,
        "beds": 3,
        "rent": 4000,
        "title": "3-bedroom house near Adenta Barrier",
        "desc": "Detached 3-bedroom house with a small yard, borehole water and parking for two cars. Close "
        "to Adenta Barrier and schools.",
    },
]

# Registered with documents but not yet visited, so the field app and the visit queue have work.
PENDING_HOMES = [
    {
        "area": "east-legon",
        "address": "GA-431-6620",
        "label": "Flat 1A",
        "lat": 5.6455,
        "lng": -0.1520,
        "type": PropertyType.APARTMENT,
        "beds": 1,
        "rent": 3200,
        "title": "",
        "desc": "",
    },
    {
        "area": "madina-adenta",
        "address": "GE-240-1177",
        "label": "Whole property",
        "lat": 5.6960,
        "lng": -0.1650,
        "type": PropertyType.SELF_CONTAINED,
        "beds": 1,
        "rent": 1400,
        "title": "",
        "desc": "",
    },
]

CAPTIONS = ["Living room", "Bedroom", "Kitchen", "Bathroom", "Compound", "Entrance"]


def room_photo(seed: int) -> bytes:
    """A simple drawn "room" so demo photos are distinct images with distinct hashes."""
    rng = random.Random(seed)
    img = Image.new("RGB", (960, 720), tuple(rng.randint(150, 235) for _ in range(3)))
    d = ImageDraw.Draw(img)
    floor_y = rng.randint(450, 560)
    d.rectangle([0, floor_y, 960, 720], fill=tuple(rng.randint(60, 160) for _ in range(3)))
    for _ in range(rng.randint(3, 7)):
        x, y = rng.randint(0, 800), rng.randint(0, floor_y)
        w, h = rng.randint(60, 320), rng.randint(50, 280)
        shape = d.rectangle if rng.random() < 0.6 else d.ellipse
        shape([x, y, x + w, y + h], fill=tuple(rng.randint(0, 255) for _ in range(3)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def demo_document() -> bytes:
    return b"%PDF-1.4\n% Afe demo authority document placeholder\n"


def seed_demo(db: Session) -> int:
    """Load demo areas, people and verified homes. Returns the number of live listings."""
    if db.scalar(select(User).where(User.username == "reviewer")):
        return 0

    areas = {}
    for slug, name, active, boundary in AREAS:
        areas[slug] = ServiceArea(slug=slug, name=name, city="Accra", is_active=active, boundary=boundary)
        db.add(areas[slug])
    db.flush()
    for slug, bands in BANDS.items():
        for bedrooms, (low, med, high) in bands.items():
            db.add(
                PriceBand(
                    area_id=areas[slug].id,
                    bedrooms=bedrooms,
                    low_pesewas=low * 100,
                    median_pesewas=med * 100,
                    high_pesewas=high * 100,
                    as_of=date.today(),
                )
            )

    reviewer = create_user(db, "reviewer", DEMO_PASSWORD, Role.ADMIN, "Efua Mensah (reviewer)", "0200000001")
    verifiers = [
        create_user(db, "verifier", DEMO_PASSWORD, Role.FIELD_VERIFIER, "Kwame Boateng (verifier)", "0200000002"),
        create_user(db, "verifier2", DEMO_PASSWORD, Role.FIELD_VERIFIER, "Akosua Darko (verifier)", "0200000003"),
    ]
    landlords = [
        create_user(db, "ama", DEMO_PASSWORD, Role.LANDLORD, "Ama Owusu", "0244123456"),
        create_user(db, "kofi", DEMO_PASSWORD, Role.AGENT, "Kofi Asante", "0501234567"),
    ]
    renter = create_user(db, "yaa", DEMO_PASSWORD, Role.RENTER, "Yaa Mensah", "0240000009")
    for person in [reviewer, *verifiers, *landlords]:
        assert person.role in MFA_ROLES
        person.totp_secret, person.totp_enabled_at = DEMO_TOTP_SECRET, utcnow()
    for i, person in enumerate(landlords):
        check_ghana_card(db, person, f"GHA-71234567{i}-{i + 3}", person.name, selfie=b"demo-selfie")
        decide_party(db, person, reviewer, True, ["ID_MATCH"])

    photos_needed = get_settings().min_visit_photos
    listings = []
    for i, home in enumerate(HOMES + PENDING_HOMES):
        lister = landlords[i % 2]
        is_agent = lister.role == Role.AGENT
        unit = register_unit(
            db,
            lister,
            areas[home["area"]],
            home["address"],
            home["label"],
            home["lat"],
            home["lng"],
            home["type"],
            home["beds"],
        )
        authority = add_authority(
            db,
            lister,
            unit,
            Relationship.AUTHORISED_AGENT if is_agent else Relationship.OWNER,
            DocumentType.OWNER_AUTHORISATION if is_agent else DocumentType.INDENTURE,
            demo_document(),
            utility_reference=f"ECG-{random.Random(i).randint(10**7, 10**8 - 1)}",
        )
        if is_agent:
            confirm_owner_by_phone(db, authority, reviewer, "0277000111", f"Owner of {home['address']}")
        review_authority(db, authority, reviewer, True)

        # Verifiers rotate: the same verifier never visits the same landlord twice in a row.
        verifier = verifiers[(i // 2) % 2]
        if i >= len(HOMES):
            # Left for the demo: one home assigned to "verifier" for today, one waiting to be assigned.
            if i == len(HOMES):
                assign_visit(db, unit, verifiers[0], reviewer, date.today(), "Demo: open this in the field app.")
            continue
        assign_visit(db, unit, verifier, reviewer, date.today())
        visit = start_visit(db, unit, verifier, home["lat"] + 0.0002, home["lng"])
        for n in range(photos_needed):
            add_visit_photo(
                db,
                visit,
                verifier,
                room_photo(i * 100 + n),
                home["lat"],
                home["lng"],
                utcnow(),
                caption=CAPTIONS[n % len(CAPTIONS)],
            )
        complete_visit(db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, True), notes="Demo visit.")
        decide_unit(
            db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"] + (["OWNER_CONFIRMED"] if is_agent else [])
        )

        listing = create_draft(
            db,
            lister,
            unit,
            home["title"],
            home["desc"],
            home["rent"] * 100,
            6,
            12,
            date.today() + timedelta(days=14 + i * 7),
        )
        submit_for_review(db, listing, lister)
        publish(db, listing, reviewer)
        listings.append(listing)
    first_listing = listings[0]

    # Payout accounts (TestEscrow's demo wallets), so protected payments can be tried at once.
    for person in landlords:
        set_payee(db, person, "momo_mtn", "0" + person.phone[4:], now_code(DEMO_TOTP_SECRET))

    # A renter who has saved a home, asked a question and asked for a viewing.
    save_listing(db, renter, first_listing)
    start_enquiry(db, renter, first_listing, "Hello, is the flat still available from next month? Is water reliable?")
    tomorrow_noon = datetime.combine(date.today() + timedelta(days=2), time(12, 0), tzinfo=utcnow().tzinfo)
    request_viewing(db, renter, first_listing, tomorrow_noon, "I can come after work if midday is hard.")

    # A viewing that has happened, so Ama can offer Yaa a tenancy (Phase 2, when enabled).
    viewed = listings[2]
    viewing = request_viewing(db, renter, viewed, tomorrow_noon, "Weekend works best.")
    respond_viewing(db, viewing, viewed.lister, True)
    viewing.requested_for = utcnow() - timedelta(days=1)
    complete_viewing(db, viewing, viewed.lister, attended=True)

    # Phase 3: scam reports waiting for a reviewer, and the shadow models' first scores.
    report(db, "Asked me to pay GH₵500 'viewing fee' by MoMo before showing the room at Madina.",
           reported_phone="0209998888", amount_lost_pesewas=50_000)
    report(db, "Facebook post with the same photos as an Afe listing, but a different number and a lower rent.",
           reported_reference="AFE-ZZZZZZ")
    process_pending(db)
    # Demo accounts have accepted the current privacy notice, like anyone who signs up.
    from app.modules.accounts.privacy import accept_notice

    for person in db.scalars(select(User)):
        accept_notice(db, person)
    return len(HOMES)
