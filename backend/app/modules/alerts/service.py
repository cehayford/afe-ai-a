"""Saved searches and new-listing alerts (roadmap workstream B).

A renter saves a search; when a verified home that matches goes live, `send-alerts` (every 5
minutes) tells them once per home. Every alert shows in the Afe inbox; at most
MAX_PAID_ALERTS_PER_DAY also go by SMS or WhatsApp, because each of those costs money."""

import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import InvalidInput, NotFound, RuleViolation
from app.core.ghana import format_ghs
from app.db import utcnow
from app.modules.accounts.service import set_whatsapp_opt_in
from app.modules.areas.models import ServiceArea
from app.modules.audit.log import record
from app.modules.listings.models import Listing, ListingStatus
from app.modules.notifications.service import notify_on

from .models import AlertSent, SavedSearch

MAX_ACTIVE_SEARCHES = 5
MAX_PAID_ALERTS_PER_DAY = 3
CHANNELS = ("sms", "whatsapp", "in_app")
LOOKBACK = timedelta(days=7)


# --- Understanding a search ----------------------------------------------------------------------


@dataclass
class Criteria:
    area: ServiceArea | None = None
    bedrooms: int | None = None
    max_rent_pesewas: int | None = None


_BEDS = re.compile(r"\b(\d)\s*(?:-|\s)?(?:bed(?:room)?s?|bd|br)\b", re.I)
_SINGLE = re.compile(r"\b(?:single room|chamber(?: and| &)? hall|self[- ]contain(?:ed)?)\b", re.I)
_MAX = re.compile(r"\b(?:under|below|max(?:imum)?|less than|up to|<)\s*(?:gh[₵cs]?\s*)?([\d][\d,]*)", re.I)
_AMOUNT = re.compile(r"(?:gh[₵cs]?\s*)([\d][\d,]*)|\b([\d][\d,]{2,})\s*(?:gh[₵cs]?|cedis?)\b", re.I)


def parse_query(db: Session, text: str) -> Criteria:
    """Read "2 bed East Legon under 5000" or "single room madina GH₵800" into search criteria."""
    c = Criteria()
    if m := _BEDS.search(text):
        c.bedrooms = min(int(m.group(1)), 3)
    elif _SINGLE.search(text):
        c.bedrooms = 0
    if m := _MAX.search(text) or _AMOUNT.search(text):
        amount = int((m.group(1) or m.group(2)).replace(",", ""))
        if 50 <= amount <= 200_000:
            c.max_rent_pesewas = amount * 100
    lowered = f" {text.lower()} "
    for area in db.scalars(select(ServiceArea).where(ServiceArea.is_active.is_(True))):
        names = {area.name.lower(), area.slug.replace("-", " ")}
        names |= {part.strip() for part in area.name.lower().split("/")}
        if any(n and f" {n} " in lowered.replace(",", " ") for n in names):
            c.area = area
            break
    return c


def describe(bedrooms: int | None, area: ServiceArea | None, max_rent_pesewas: int | None) -> str:
    size = {None: "Homes", 0: "Single rooms", 1: "1-bedroom homes", 3: "Homes with 3+ bedrooms"}.get(
        bedrooms, f"{bedrooms}-bedroom homes"
    )
    where = f" in {area.name}" if area else " in any area"
    price = f" up to {format_ghs(max_rent_pesewas)}/month" if max_rent_pesewas else ""
    return f"{size}{where}{price}"


def describe_search(s: SavedSearch) -> str:
    return describe(s.bedrooms, s.area, s.max_rent_pesewas)


# --- Managing searches ---------------------------------------------------------------------------------


def searches_for(db: Session, user) -> list[SavedSearch]:
    return list(db.scalars(
        select(SavedSearch).where(SavedSearch.user_id == user.id, SavedSearch.active.is_(True)).order_by(SavedSearch.id)
    ))


def save_search(db: Session, user, criteria: Criteria, channel: str = "") -> SavedSearch:
    channel = channel or ("sms" if user.phone else "in_app")
    if channel not in CHANNELS:
        raise InvalidInput("Choose SMS, WhatsApp or the Afe inbox.")
    if channel in ("sms", "whatsapp") and not user.phone:
        raise InvalidInput("Add a phone number to get alerts by SMS or WhatsApp.")
    if criteria.area is None and criteria.bedrooms is None and criteria.max_rent_pesewas is None:
        raise InvalidInput("Choose an area, a size or a price, so alerts are useful.")
    if channel == "whatsapp":
        set_whatsapp_opt_in(db, user, True, "alert")  # they asked for WhatsApp messages
    existing = searches_for(db, user)
    for s in existing:
        if (s.area_id, s.bedrooms, s.max_rent_pesewas) == (
            criteria.area.id if criteria.area else None, criteria.bedrooms, criteria.max_rent_pesewas
        ):
            s.channel = channel
            db.flush()
            return s
    if len(existing) >= MAX_ACTIVE_SEARCHES:
        raise RuleViolation(f"You can keep {MAX_ACTIVE_SEARCHES} alerts. Remove one to add another.")
    s = SavedSearch(user_id=user.id, area_id=criteria.area.id if criteria.area else None, bedrooms=criteria.bedrooms,
                    max_rent_pesewas=criteria.max_rent_pesewas, channel=channel)
    db.add(s)
    db.flush()
    record(db, user, "alerts.saved", s, channel=channel)
    return s


def stop_search(db: Session, user, search_id: int) -> None:
    s = db.get(SavedSearch, search_id)
    if s is None or s.user_id != user.id or not s.active:
        raise NotFound("That alert isn't on your account.")
    s.active = False
    db.flush()


def stop_all(db: Session, user) -> int:
    rows = searches_for(db, user)
    for s in rows:
        s.active = False
    db.flush()
    return len(rows)


# --- Sending --------------------------------------------------------------------------------------------


def matches(s: SavedSearch, listing: Listing) -> bool:
    unit = listing.unit
    if s.area_id is not None and unit.area_id != s.area_id:
        return False
    if s.bedrooms is not None and not (unit.bedrooms >= 3 if s.bedrooms >= 3 else unit.bedrooms == s.bedrooms):
        return False
    return not (s.max_rent_pesewas and listing.rent_pesewas > s.max_rent_pesewas)


def send_alerts(db: Session) -> dict[str, int]:
    """Tell each saved search about matching homes published since it was saved (last 7 days)."""
    now = utcnow()
    listings = list(db.scalars(
        select(Listing).where(Listing.status == ListingStatus.LIVE, Listing.published_at > now - LOOKBACK)
        .order_by(Listing.published_at)
    ))
    counts = {"alerts": 0, "paid": 0, "inbox_only": 0}
    if not listings:
        return counts
    already = set(db.execute(select(AlertSent.search_id, AlertSent.listing_id)).all())
    paid_today: dict[int, int] = dict(db.execute(
        select(SavedSearch.user_id, func.count())
        .join(AlertSent, AlertSent.search_id == SavedSearch.id)
        .where(AlertSent.created_at > now - timedelta(days=1), AlertSent.channel != "in_app")
        .group_by(SavedSearch.user_id)
    ).all())
    frontend = get_settings().frontend_url
    for s in db.scalars(select(SavedSearch).where(SavedSearch.active.is_(True))):
        user = s.user
        if not user.is_active:
            continue
        for listing in listings:
            if listing.published_at < s.created_at or (s.id, listing.id) in already or not matches(s, listing):
                continue
            if listing.lister_id == user.id:
                continue
            channel = s.channel
            if channel != "in_app" and paid_today.get(user.id, 0) >= MAX_PAID_ALERTS_PER_DAY:
                channel = "in_app"
                counts["inbox_only"] += 1
            try:
                with db.begin_nested():
                    db.add(AlertSent(search_id=s.id, listing_id=listing.id, channel=channel))
                    db.flush()
            except IntegrityError:
                continue
            notify_on(
                db, user, "search_alert", {channel, "in_app"}, link=f"/homes/{listing.reference}",
                title=listing.title, rent=listing.rent_display, area=listing.unit.area.name,
                url=f"{frontend}/homes/{listing.reference}",
            )
            s.alerts_sent += 1
            s.last_alert_at = now
            counts["alerts"] += 1
            if channel != "in_app":
                counts["paid"] += 1
                paid_today[user.id] = paid_today.get(user.id, 0) + 1
    db.flush()
    return counts
