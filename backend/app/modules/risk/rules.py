"""Phase 1 detection rules (plan §7). Simple, explainable, and logged, so Phase 3 models
have something to beat. Each rule returns hits; evaluate_listing turns hits into flags."""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.ghana import format_ghs
from app.modules.areas.models import PriceBand

from .flags import raise_flag
from .models import Severity


@dataclass(frozen=True)
class Hit:
    rule: str
    severity: str
    explanation: str
    evidence: dict


# (rule id, severity, what it means, patterns). Ghanaian English and Pidgin phrasing.
SCAM_PATTERNS: list[tuple[str, str, str, list[str]]] = [
    (
        "language.pay_before_viewing",
        Severity.HIGH,
        "Asks for money before a viewing",
        [
            r"\bpay (?:first|before (?:you )?(?:view|see|inspect)\w*)",
            r"\b(?:viewing|inspection|commitment|booking|registration) fee\b",
            r"\bsend (?:the |small )?(?:money|momo|cash)\b.*\b(?:before|first|then)\b",
            r"\bsend (?:the |small )?(?:money|momo|cash) make (?:i|we)\b",
            r"\bdeposit (?:first|to secure|to reserve)\b",
        ],
    ),
    (
        "language.move_off_platform",
        Severity.MEDIUM,
        "Tries to move the conversation or payment off Afe",
        [
            r"\b(?:whatsapp|watsapp|wa) me\b",
            r"\bchat me (?:up )?on (?:whatsapp|telegram)\b",
            r"\b(?:call|text|dm) me on\b",
            r"\bmomo (?:me|number)\b",
            r"\bpay (?:directly|to me|to my (?:number|account))\b",
        ],
    ),
    (
        "language.urgency",
        Severity.LOW,
        "Uses pressure or urgency",
        [
            r"\b(?:today only|first come,? first served|hurry|urgent(?:ly)?)\b",
            r"\bmany (?:people|clients|tenants) (?:are )?(?:interested|waiting|calling)\b",
            r"\b(?:before|or) (?:someone|somebody) (?:else )?(?:takes|pays|grabs) it\b",
        ],
    ),
]

_COMPILED = [
    (rule, sev, meaning, [re.compile(p, re.IGNORECASE) for p in pats]) for rule, sev, meaning, pats in SCAM_PATTERNS
]
_PHONE = re.compile(r"(?:\+?233|0)\s?[2-5]\d(?:[\s-]?\d){7}")


def scam_language(text: str) -> list[Hit]:
    text = text or ""
    hits = []
    for rule, severity, meaning, patterns in _COMPILED:
        matched = [m.group(0) for p in patterns if (m := p.search(text))]
        if matched:
            hits.append(Hit(rule, severity, f"{meaning}: “{matched[0]}”", {"matches": matched}))
    if phone := _PHONE.search(text):
        hits.append(
            Hit(
                "language.phone_number_in_text",
                Severity.MEDIUM,
                "Puts a phone number in the listing text instead of using Afe messages",
                {"match": phone.group(0)},
            )
        )
    return hits


def price_anomaly(db: Session, rent_pesewas: int, area, bedrooms: int) -> Hit | None:
    """Flag rent far below the area's range: the classic bait price."""
    band = db.scalar(
        select(PriceBand)
        .where(PriceBand.area_id == area.id, PriceBand.bedrooms == bedrooms)
        .order_by(PriceBand.as_of.desc())
    )
    if band is None:
        return None
    ratio = get_settings().price_anomaly_ratio
    if rent_pesewas >= int(band.low_pesewas * ratio):
        return None
    return Hit(
        "price.far_below_area",
        Severity.HIGH,
        (
            f"Rent {format_ghs(rent_pesewas)} is below {int(ratio * 100)}% of the usual low of "
            f"{format_ghs(band.low_pesewas)} for a {bedrooms}-bedroom in {area.name}"
        ),
        {"rent": rent_pesewas, "band_low": band.low_pesewas, "band_id": band.id},
    )


def advance_rent(advance_months: int, min_lease_months: int) -> Hit | None:
    """Act 220 caps advance rent at six months for tenancies over six months. How Afe
    enforces it is decision B10 (counsel); until then it is a reviewer flag, not a block."""
    cap = get_settings().advance_cap_months
    if min_lease_months > 6 and advance_months > cap:
        return Hit(
            "compliance.advance_above_cap",
            Severity.MEDIUM,
            f"Asks for {advance_months} months in advance; Act 220 caps advance rent at {cap}",
            {"advance_months": advance_months},
        )
    return None


def evaluate_listing(db: Session, listing) -> list:
    hits = scam_language(f"{listing.title}\n{listing.description}")
    for extra in (
        price_anomaly(db, listing.rent_pesewas, listing.unit.area, listing.unit.bedrooms),
        advance_rent(listing.advance_months, listing.min_lease_months),
    ):
        if extra:
            hits.append(extra)
    return [raise_flag(db, listing, h.rule, h.severity, h.explanation, **h.evidence) for h in hits]
