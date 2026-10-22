from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ghana import normalise_ghana_card, pii_hash
from app.modules.audit.log import record
from app.modules.risk.flags import raise_flag
from app.modules.risk.models import Severity

from .models import CheckStatus, IdentityCheck
from .providers import get_provider


def check_ghana_card(db: Session, user, card_number: str, full_name: str, selfie: bytes | None = None) -> IdentityCheck:
    """Run a Ghana Card check. A card already verified on another account fails the check
    and raises a high-severity flag on both accounts: one person, one account."""
    card = normalise_ghana_card(card_number)
    card_hash = pii_hash(card)
    last4 = card.replace("GHA-", "").replace("-", "")[-4:]
    provider = get_provider()

    other = db.scalar(
        select(IdentityCheck).where(
            IdentityCheck.card_number_hash == card_hash,
            IdentityCheck.status == CheckStatus.PASSED,
            IdentityCheck.user_id != user.id,
        )
    )
    if other:
        check = IdentityCheck(
            user_id=user.id,
            provider=provider.name,
            status=CheckStatus.FAILED,
            card_number_hash=card_hash,
            card_last4=last4,
            failure_reason="This Ghana Card is already verified on another Afe account.",
        )
        db.add(check)
        db.flush()
        for account in (user, other.user):
            raise_flag(
                db,
                account,
                rule="identity.duplicate_ghana_card",
                severity=Severity.HIGH,
                explanation="The same Ghana Card was used on two Afe accounts.",
                accounts=[user.id, other.user_id],
            )
    else:
        result = provider.verify_ghana_card(card, full_name, selfie)
        passed = result.passed and result.name_matches
        check = IdentityCheck(
            user_id=user.id,
            provider=provider.name,
            provider_reference=result.reference,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            card_number_hash=card_hash,
            card_last4=last4,
            name_on_card=result.name_on_card,
            name_matches=result.name_matches,
            liveness_passed=result.liveness_passed,
            failure_reason=result.failure_reason or ("" if passed else "Name does not match the card."),
        )
        db.add(check)
        db.flush()
    record(db, user, "identity.checked", check, status=check.status, provider=check.provider)
    return check


def latest_check(db: Session, user, passed_only: bool = False) -> IdentityCheck | None:
    q = select(IdentityCheck).where(IdentityCheck.user_id == user.id)
    if passed_only:
        q = q.where(IdentityCheck.status == CheckStatus.PASSED)
    return db.scalar(q.order_by(IdentityCheck.created_at.desc(), IdentityCheck.id.desc()))
