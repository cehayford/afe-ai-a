"""The JSON API, driven the way the field-verifier and landlord apps will use it."""

from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.areas.models import ServiceArea
from tests.conftest import EAST_LEGON, PDF, PIN, make_user, photo_bytes
from tests.conftest import api_login as login


def test_auth(client, db):
    make_user(db, "ama", Role.LANDLORD, phone="0244123456")
    db.commit()
    wrong = client.post("/api/v1/auth/signin/password", json={"login": "ama", "password": "wrong-password"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "sign_in_failed"
    by_phone = login(client, "024 412 3456")
    me = client.get("/api/v1/me", headers=by_phone).json()
    assert me["data"]["user"]["username"] == "ama" and me["error"] is None
    res = client.get("/api/v1/me")
    assert res.status_code == 401
    assert res.json() == {
        "data": None,
        "meta": {},
        "error": {"code": "not_authenticated", "message": "Sign in to continue.", "reasons": []},
    }


def test_full_verification_journey_over_the_api(client, db):
    db.add(ServiceArea(slug="east-legon", name="East Legon", city="Accra", is_active=True, boundary=EAST_LEGON))
    make_user(db, "ama", Role.LANDLORD, phone="0244123456")
    make_user(db, "kwame", Role.FIELD_VERIFIER)
    make_user(db, "efua", Role.REVIEWER)
    db.commit()
    ama, kwame, efua = login(client, "ama"), login(client, "kwame"), login(client, "efua")

    # Landlord: Ghana Card, home, authority document, draft listing.
    kyc = client.post(
        "/api/v1/kyc/ghana-card",
        headers=ama,
        data={"card_number": "GHA-712345678-3", "full_name": "Ama Owusu"},
        files={"selfie": ("selfie.jpg", photo_bytes(99), "image/jpeg")},
    )
    assert kyc.json()["data"]["status"] == "passed"
    unit = client.post(
        "/api/v1/properties/units",
        headers=ama,
        json={
            "area_slug": "east-legon",
            "digital_address": "GA-492-7424",
            "unit_label": "Flat 2B",
            "lat": PIN[0],
            "lng": PIN[1],
            "property_type": "apartment",
            "bedrooms": 2,
        },
    )
    assert unit.status_code == 201, unit.text
    unit_id = unit.json()["data"]["unit"]["id"]
    authority = client.post(
        f"/api/v1/kyc/units/{unit_id}/authority",
        headers=ama,
        data={"relationship": "owner", "document_type": "indenture"},
        files={"document": ("indenture.pdf", PDF, "application/pdf")},
    )
    assert authority.status_code == 201, authority.text
    listing = client.post(
        "/api/v1/properties/listings",
        headers=ama,
        json={
            "unit_id": unit_id,
            "title": "Bright 2-bedroom flat",
            "description": "Quiet gated compound with a water tank.",
            "rent_ghs": 4800,
            "advance_months": 6,
            "available_from": "2026-11-01",
        },
    ).json()["data"]

    # A landlord cannot do verifier or reviewer work.
    assert (
        client.post(
            "/api/v1/verify/visits", headers=ama, json={"unit_id": unit_id, "lat": PIN[0], "lng": PIN[1]}
        ).status_code
        == 403
    )

    # Reviewer sends the verifier; the verifier sees it on their worklist.
    not_yet = client.post(
        "/api/v1/verify/visits", headers=kwame, json={"unit_id": unit_id, "lat": PIN[0], "lng": PIN[1]}
    )
    assert not_yet.status_code == 409 and "not assigned" in not_yet.json()["error"]["message"]
    kwame_id = client.get("/api/v1/me", headers=kwame).json()["data"]["user"]["id"]
    assigned = client.post(
        f"/api/v1/review/units/{unit_id}/assignments",
        headers=efua,
        json={"verifier_id": kwame_id, "scheduled_for": utcnow().date().isoformat()},
    )
    assert assigned.status_code == 201, assigned.text
    work = client.get("/api/v1/verify/worklist", headers=kwame).json()["data"]
    assert [a["unit"]["id"] for a in work["assignments"]] == [unit_id]
    assert work["assignments"][0]["landlord_phone"] == "+233244123456"

    # Field verifier: visit with photos taken at the property.
    visit = client.post("/api/v1/verify/visits", headers=kwame, json={"unit_id": unit_id, "lat": PIN[0], "lng": PIN[1]})
    assert visit.status_code == 201, visit.text
    visit_id = visit.json()["data"]["id"]
    for n in range(4):
        photo = client.post(
            f"/api/v1/verify/visits/{visit_id}/photos",
            headers=kwame,
            data={"lat": PIN[0], "lng": PIN[1], "taken_at": utcnow().isoformat(), "caption": f"Room {n}"},
            files={"photo": (f"p{n}.jpg", photo_bytes(n), "image/jpeg")},
        )
        assert photo.status_code == 201, photo.text
        assert photo.json()["meta"] == {"duplicate": False}
    done = client.post(
        f"/api/v1/verify/visits/{visit_id}/complete",
        headers=kwame,
        json={
            "checklist": {
                k: True
                for k in (
                    "met_landlord_or_caretaker",
                    "ghana_card_seen_in_person",
                    "unit_exists",
                    "unit_vacant",
                    "matches_description",
                )
            }
        },
    )
    assert done.json()["data"]["outcome"] == "passed"

    # Reviewer: queue, decisions, authority, publish.
    queue = client.get("/api/v1/review/queue", headers=efua).json()["data"]
    assert [p["name"] for p in queue["people"]] == ["Ama"] and len(queue["homes_to_decide"]) == 1
    blocked = client.post(f"/api/v1/review/listings/{listing['id']}/publish", headers=efua)
    assert blocked.status_code == 409  # listing is still a draft

    assert client.post(f"/api/v1/properties/listings/{listing['id']}/submit", headers=ama).status_code == 200
    blocked = client.post(f"/api/v1/review/listings/{listing['id']}/publish", headers=efua).json()
    assert blocked["error"]["code"] == "rule_violation"
    assert "The landlord or agent is not currently verified." in blocked["error"]["reasons"]

    person_id = queue["people"][0]["id"]
    assert (
        client.post(
            f"/api/v1/review/people/{person_id}/decision",
            headers=efua,
            json={"approve": True, "reason_codes": ["ID_MATCH"]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/review/authority/{authority.json()['data']['id']}/decision", headers=efua, json={"accept": True}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/review/units/{unit_id}/decision",
            headers=efua,
            json={"approve": True, "reason_codes": ["DOCS_SIGHTED", "VISIT_MATCH"]},
        ).status_code
        == 200
    )
    live = client.post(f"/api/v1/review/listings/{listing['id']}/publish", headers=efua)
    assert live.status_code == 200 and live.json()["data"]["status"] == "live"

    # Public: search, detail with Afe photos and the verification panel, check before you pay.
    found = client.get("/api/v1/properties/search", params={"area": "east-legon", "bedrooms": 2}).json()
    assert found["meta"]["count"] == 1
    detail = client.get(f"/api/v1/properties/{listing['reference']}").json()["data"]
    assert len(detail["photos"]) == 4 and "/media/units/" in detail["photos"][0]["url"]
    assert [v["text"] for v in detail["verification"]][-1] == "Photos taken by Afe"
    assert client.get("/api/v1/check", params={"q": "0244123456"}).json()["data"]["verified"] is True
    assert (
        client.post(
            "/api/v1/check/reports", json={"what_happened": "Asked me to pay a viewing fee by MoMo."}
        ).status_code
        == 201
    )


def test_validation_errors_use_the_envelope(client, db):
    make_user(db, "ama", Role.LANDLORD)
    db.commit()
    res = client.post("/api/v1/properties/units", headers=login(client, "ama"), json={"area_slug": "x"})
    body = res.json()
    assert res.status_code == 422 and body["error"]["code"] == "invalid_input" and body["error"]["reasons"]


def test_cookies_never_authenticate_the_api(client, db):
    """The API is bearer-only; the frontend keeps tokens server-side."""
    make_user(db, "kwame", Role.FIELD_VERIFIER)
    db.commit()
    client.cookies.set("afe_access", "anything")
    assert client.get("/api/v1/verify/worklist").status_code == 401
