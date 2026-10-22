"""What Afe charges right now. Public, so every page can say plainly what's free."""

from fastapi import APIRouter

from app.core.envelope import ok
from app.deps import DB
from app.modules.billing.service import fee_pesewas
from app.modules.compliance.service import charges_free, free_until, rule

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("")
def pricing(db: DB):
    free = charges_free(db)
    return ok({
        "launch_offer": free,
        "free_until": free_until(db).isoformat(),
        "verification_fee_pesewas": fee_pesewas(db),
        "protection_fee_bps": 0 if free else rule(db, "protection_fee_bps"),
        "featured_fee_pesewas": 0 if free else rule(db, "featured_fee_pesewas"),
        "featured_days": rule(db, "featured_days"),
    })
