"""Check before you pay, and scam reports."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.core.envelope import Envelope, ok
from app.deps import DB
from app.modules.accounts.service import rate_limit
from app.modules.listings.service import listing_photos
from app.modules.scamcheck import service as scamcheck
from app.modules.scamcheck.models import Channel

from .. import schemas as s
from .common import client_address

# Enough for a renter checking every number they're sent; too few to scrape who is on Afe.
CHECKS_PER_HOUR = 60
REPORTS_PER_HOUR = 5

router = APIRouter(prefix="/check", tags=["check"])


@router.get("", response_model=Envelope[s.CheckOut])
def check(db: DB, request: Request, q: Annotated[str, Query(max_length=20)]):
    rate_limit(db, f"check:{client_address(request)}", CHECKS_PER_HOUR, timedelta(hours=1),
               "You've checked a lot of numbers in the last hour. Try again later.")
    result = scamcheck.check(db, q, channel=Channel.WEB)
    return ok(
        s.CheckOut(
            verified=result.verified,
            headline=result.headline,
            details=result.details,
            advice=result.advice,
            listings=[s.ListingOut.of(li, next(iter(listing_photos(db, li)), None)) for li in result.listings],
        )
    )


@router.post("/reports", response_model=Envelope[dict], status_code=201)
def report(db: DB, request: Request, body: s.ReportIn):
    rate_limit(db, f"report:{client_address(request)}", REPORTS_PER_HOUR, timedelta(hours=1),
               "Thanks. You've sent several reports already; we'll be in touch if we need more.")
    created = scamcheck.report(
        db,
        body.what_happened,
        body.reported_phone,
        body.reported_reference,
        int(body.amount_lost_ghs * 100) if body.amount_lost_ghs is not None else None,
        body.reporter_contact,
    )
    return ok({"id": created.id})
