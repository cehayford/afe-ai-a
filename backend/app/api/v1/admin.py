"""Admin-only: staff accounts."""

from fastapi import APIRouter
from sqlalchemy import select

from app.core.envelope import Envelope, ok
from app.core.errors import NotAllowed
from app.deps import DB, Reviewer
from app.modules.accounts import staff
from app.modules.accounts.models import User
from app.modules.areas import service as areas
from app.modules.areas.models import PriceBand, ServiceArea

from .. import schemas as s
from .common import get_or_404

router = APIRouter(prefix="/admin", tags=["admin"])


def _out(user) -> s.StaffOut:
    out = s.StaffOut.model_validate(user)
    out.mfa_enabled = user.totp_enabled_at is not None
    return out


@router.get("/staff", response_model=Envelope[list[s.StaffOut]])
def list_staff(db: DB, user: Reviewer):
    return ok([_out(u) for u in staff.list_staff(db, user)])


@router.post("/staff", response_model=Envelope[s.StaffOut], status_code=201)
def add_staff(db: DB, user: Reviewer, body: s.StaffIn):
    return ok(_out(staff.add_staff(db, user, body.name, body.phone, body.role)))


@router.post("/staff/{user_id}/role", response_model=Envelope[s.StaffOut])
def change_role(db: DB, user: Reviewer, user_id: int, body: s.StaffRoleIn):
    return ok(_out(staff.change_role(db, user, get_or_404(db, User, user_id, "Person"), body.role)))


@router.post("/staff/{user_id}/active", response_model=Envelope[s.StaffOut])
def set_active(db: DB, user: Reviewer, user_id: int, body: s.StaffActiveIn):
    return ok(_out(staff.set_active(db, user, get_or_404(db, User, user_id, "Person"), body.active)))


@router.post("/people/{user_id}/active", response_model=Envelope[s.UserOut])
def suspend(db: DB, user: Reviewer, user_id: int, body: s.SuspendIn):
    """Suspend or restore a renter, landlord or agent (see docs/runbooks.md)."""
    person = get_or_404(db, User, user_id, "Person")
    return ok(s.UserOut.of(staff.suspend_account(db, user, person, body.active, body.reason)))



# --- Areas (roadmap workstream H) ------------------------------------------------------------------


def _area_out(db, area) -> s.AreaAdminOut:
    sizes = sorted(set(db.scalars(select(PriceBand.bedrooms).where(PriceBand.area_id == area.id))))
    out = s.AreaAdminOut.model_validate(area)
    out.missing, out.surveyed_sizes = areas.readiness(db, area), sizes
    return out


@router.get("/areas", response_model=Envelope[list[s.AreaAdminOut]])
def list_areas(db: DB, user: Reviewer):
    if user.role != "admin":
        raise NotAllowed("Only an Afe admin can open areas.")
    return ok([_area_out(db, a) for a in db.scalars(select(ServiceArea).order_by(ServiceArea.name))])


@router.post("/areas", response_model=Envelope[s.AreaAdminOut], status_code=201)
def create_area(db: DB, user: Reviewer, body: s.AreaIn):
    return ok(_area_out(db, areas.create_area(db, user, body.name, body.slug, body.city, body.boundary)))


@router.post("/areas/{area_id}/price-survey", response_model=Envelope[s.AreaAdminOut])
def price_survey(db: DB, user: Reviewer, area_id: int, body: list[s.PriceSurveyRow]):
    area = get_or_404(db, ServiceArea, area_id, "Area")
    areas.load_price_survey(db, user, area, [r.model_dump() for r in body])
    return ok(_area_out(db, area))


@router.post("/areas/{area_id}/open", response_model=Envelope[s.AreaAdminOut])
def open_area(db: DB, user: Reviewer, area_id: int, body: s.AreaOpenIn):
    return ok(_area_out(db, areas.set_open(db, user, get_or_404(db, ServiceArea, area_id, "Area"), body.open)))
