import pytest
from sqlalchemy import func, select

from app.core.errors import RuleViolation
from app.modules.accounts.models import Role
from app.modules.identity.service import check_ghana_card
from app.modules.listings.models import ListingStatus
from app.modules.listings.service import (
    listing_photos,
    publish,
    publish_blockers,
    submit_for_review,
    verification_panel,
)
from app.modules.risk.flags import open_flags
from app.modules.risk.rules import scam_language
from app.modules.scamcheck.models import Lookup
from app.modules.scamcheck.service import check
from app.modules.verification.service import current_verification, decide_party, revoke
from tests.conftest import make_listing, make_user


def live_listing(db, unit, lister, reviewer, **overrides):
    listing = make_listing(db, unit, lister, **overrides)
    submit_for_review(db, listing, lister)
    return publish(db, listing, reviewer)


def test_listing_on_unverified_home_cannot_go_live(db, unit, verified_landlord, reviewer):
    listing = make_listing(db, unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    with pytest.raises(RuleViolation) as exc:
        publish(db, listing, reviewer)
    assert "The home has not been verified by an Afe visit." in exc.value.reasons


def test_lister_without_authority_cannot_publish(db, verified_unit, reviewer):
    agent = make_user(db, "stranger", Role.AGENT)
    check_ghana_card(db, agent, "GHA-799999999-1", agent.name, selfie=b"s")
    decide_party(db, agent, reviewer, True, ["ID_MATCH"])
    listing = make_listing(db, verified_unit, agent)
    assert "The lister has no accepted authority to let this home." in publish_blockers(db, listing)


def test_verified_listing_goes_live_with_afe_photos_and_panel(db, verified_unit, verified_landlord, reviewer):
    listing = live_listing(db, verified_unit, verified_landlord, reviewer)
    assert listing.status == ListingStatus.LIVE
    assert len(listing_photos(db, listing)) == 4
    lines = [line.text for line in verification_panel(db, listing)]
    assert lines == ["Landlord's Ghana Card checked", "Indenture sighted", "Visited by Afe", "Photos taken by Afe"]


def test_one_active_listing_per_home(db, verified_unit, verified_landlord, reviewer):
    live_listing(db, verified_unit, verified_landlord, reviewer)
    second = make_listing(db, verified_unit, verified_landlord)  # drafts don't count
    with pytest.raises(RuleViolation, match="already has an active listing"):
        submit_for_review(db, second, verified_landlord)


def test_revoking_a_badge_pauses_live_listings(db, verified_unit, verified_landlord, reviewer):
    listing = live_listing(db, verified_unit, verified_landlord, reviewer)
    revoke(db, current_verification(db, party=verified_landlord), reviewer, ["FRAUD_REPORT"])
    db.refresh(listing)
    assert listing.status == ListingStatus.PAUSED


def test_scam_language_and_bait_price_are_flagged_and_block(db, verified_unit, verified_landlord, reviewer):
    listing = make_listing(
        db,
        verified_unit,
        verified_landlord,
        rent_pesewas=150_000,
        advance_months=12,
        description="Many people are interested. Pay the viewing fee first, then WhatsApp me on 024 412 3456.",
    )
    submit_for_review(db, listing, verified_landlord)
    assert {f.rule for f in open_flags(db, listing)} == {
        "language.pay_before_viewing",
        "language.move_off_platform",
        "language.urgency",
        "language.phone_number_in_text",
        "price.far_below_area",
        "compliance.advance_above_cap",
    }
    with pytest.raises(RuleViolation):
        publish(db, listing, reviewer)


@pytest.mark.parametrize(
    "text", ["Send the momo make I hold the room for you", "commitment fee of 200 cedis", "Please chat me on WhatsApp"]
)
def test_ghanaian_scam_phrasing(text):
    assert scam_language(text)


def test_ordinary_listing_text_is_clean():
    assert scam_language("Two bedrooms, tiled floors, water tank, close to the trotro station.") == []


def test_check_before_you_pay(db, verified_unit, verified_landlord, reviewer):
    listing = live_listing(db, verified_unit, verified_landlord, reviewer)
    ok = check(db, "024 412 3456")
    assert ok.verified and ok.listings == [listing]
    unknown = check(db, "0551112222")
    assert not unknown.verified
    assert "not verified by Afe" in unknown.headline
    assert "scam" not in unknown.headline.lower()
    assert check(db, listing.reference.lower()).verified
    assert not check(db, "AFE-222222").verified
    assert not check(db, "hello").verified
    assert db.scalar(select(func.count()).select_from(Lookup)) == 5
