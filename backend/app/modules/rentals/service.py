"""Landlord and agent tools (roadmap workstream G).

A landlord keeps a register of their tenants and rent, with receipts, due-date reminders,
maintenance requests, agreements both sides sign in the app, and renewals within the
advance-rent cap. Tenants who came through Afe join the register automatically once the
protected payment is released. Plans limit how many tenants a landlord can keep (B19)."""

import calendar
import hashlib
import secrets
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, NotFound, RuleViolation
from app.core.ghana import format_ghs, normalise_phone
from app.db import utcnow
from app.modules.accounts.models import User
from app.modules.audit.log import record
from app.modules.compliance.service import charges_free, free_until, rule
from app.modules.notifications.service import notify_on

from .models import Agreement, Maintenance, Plan, Renewal, Rental, RentalStatus, RentPayment, Subscription

PLAN_LIMITS = {Plan.FREE: 1, Plan.STANDARD: 10, Plan.PRO: 50}
PLAN_LABELS = {Plan.FREE: "Free: 1 tenant", Plan.STANDARD: "Standard: up to 10 tenants", Plan.PRO: "Pro: up to 50 tenants"}
WELCOME_FREE_DAYS = 90
METHODS = ("momo", "bank", "cash", "afe")


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year, month = d.year + month // 12, month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


# --- Plans ---------------------------------------------------------------------------------------------


def current_plan(db: Session, user: User) -> str:
    sub = db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if sub and sub.plan != Plan.FREE and sub.period_end and sub.period_end >= utcnow().date():
        return sub.plan
    return Plan.FREE


def plan_price(db: Session, plan: str) -> int:
    return {Plan.STANDARD: rule(db, "plan_standard_pesewas"), Plan.PRO: rule(db, "plan_pro_pesewas")}.get(plan, 0)


def subscribe(db: Session, user: User, plan: str):
    """Returns the payment to check out, or None when the plan starts free (launch offer, or
    the first 90 days for landlords who joined during it)."""
    from app.modules.billing.service import start_subscription_payment

    if not user.is_lister:
        raise NotAllowed("Plans are for landlords and agents.")
    if plan not in (Plan.STANDARD, Plan.PRO):
        raise InvalidInput("Choose Standard or Pro.")
    sub = db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    today = utcnow().date()
    free_end = None
    if charges_free(db):
        free_end = free_until(db)
    elif sub is None and user.created_at.date() < free_until(db):
        free_end = today + timedelta(days=WELCOME_FREE_DAYS)
    if free_end:
        activate(db, user, plan, free_end)
        return None
    return start_subscription_payment(db, user, plan, plan_price(db, plan))


def activate(db: Session, user: User, plan: str, until: date) -> Subscription:
    sub = db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if sub is None:
        sub = Subscription(user_id=user.id)
        db.add(sub)
    start = max(sub.period_end or utcnow().date(), utcnow().date()) if sub.plan == plan else utcnow().date()
    sub.plan, sub.period_end, sub.updated_at = plan, max(until, start), utcnow()
    db.flush()
    record(db, user, "plan.activated", sub, plan=plan, until=str(sub.period_end))
    return sub


# --- Tenants -------------------------------------------------------------------------------------------------


def rentals_for(db: Session, landlord: User) -> list[Rental]:
    return list(db.scalars(select(Rental).where(Rental.landlord_id == landlord.id).order_by(Rental.status, Rental.next_due_date)))


def homes_rented(db: Session, tenant: User) -> list[Rental]:
    return list(db.scalars(select(Rental).where(Rental.tenant_user_id == tenant.id).order_by(Rental.id.desc())))


def get_rental(db: Session, rental_id: int, user: User) -> Rental:
    r = db.get(Rental, rental_id)
    if r is None or user.id not in (r.landlord_id, r.tenant_user_id):
        raise NotFound("Tenant record not found.")
    return r


def _active_count(db: Session, landlord: User) -> int:
    return db.scalar(select(func.count()).select_from(Rental).where(
        Rental.landlord_id == landlord.id, Rental.status == RentalStatus.ACTIVE, Rental.tenancy_id.is_(None)))


def add_rental(db: Session, landlord: User, *, tenant_name: str, tenant_phone: str, rent_pesewas: int,
               pay_every_months: int, start_date: date, end_date: date, unit=None) -> Rental:
    if not landlord.is_lister:
        raise NotAllowed("Only landlords and agents keep tenant records.")
    plan = current_plan(db, landlord)
    if _active_count(db, landlord) >= PLAN_LIMITS[Plan(plan)]:
        raise RuleViolation(f"Your plan ({PLAN_LABELS[Plan(plan)]}) is full. Choose a bigger plan to add more tenants.")
    if unit is not None and unit.registered_by_id != landlord.id:
        raise NotFound("That home isn't on your account.")
    if len(tenant_name.strip()) < 2 or rent_pesewas <= 0 or not 1 <= pay_every_months <= 24:
        raise InvalidInput("Enter the tenant's name, the rent, and how many months each payment covers.")
    if end_date <= start_date:
        raise InvalidInput("The end date must be after the start date.")
    phone = normalise_phone(tenant_phone) if tenant_phone else ""
    tenant_user = db.scalar(select(User).where(User.phone == phone, User.is_active.is_(True))) if phone else None
    r = Rental(landlord_id=landlord.id, unit_id=unit.id if unit else None, tenant_name=tenant_name.strip()[:120],
               tenant_phone=phone, tenant_user_id=tenant_user.id if tenant_user else None, rent_pesewas=rent_pesewas,
               pay_every_months=pay_every_months, start_date=start_date, end_date=end_date, next_due_date=start_date)
    db.add(r)
    db.flush()
    record(db, landlord, "rental.added", r)
    return r


def from_afe_tenancy(db: Session, t) -> Rental:
    """A protected payment was released: the tenancy joins the landlord's register, with the
    advance already paid through Afe (outside plan limits: Afe tenancies are always kept)."""
    existing = db.scalar(select(Rental).where(Rental.tenancy_id == t.id))
    if existing:
        return existing
    start = t.move_in_date
    r = Rental(landlord_id=t.landlord_id, unit_id=t.unit_id, tenancy_id=t.id, tenant_name=t.tenant.name,
               tenant_phone=t.tenant.phone or "", tenant_user_id=t.tenant_id, rent_pesewas=t.rent_pesewas,
               pay_every_months=max(t.advance_months, 1), start_date=start, end_date=add_months(start, t.lease_months),
               next_due_date=add_months(start, t.advance_months or 1))
    db.add(r)
    db.flush()
    if t.advance_months:
        _payment(db, r, t.rent_pesewas * t.advance_months, start, "afe", t.advance_months,
                 f"Advance paid through Afe ({t.reference})", None)
        r.next_due_date = add_months(start, t.advance_months)
    db.flush()
    return r


def end_rental(db: Session, landlord: User, r: Rental) -> Rental:
    if r.landlord_id != landlord.id:
        raise NotFound("Tenant record not found.")
    r.status = RentalStatus.ENDED
    db.flush()
    record(db, landlord, "rental.ended", r)
    return r


# --- Rent ------------------------------------------------------------------------------------------------------


def _payment(db, r, amount, paid_on, method, covers, note, by) -> RentPayment:
    p = RentPayment(rental_id=r.id, receipt_no=f"AFE-R-{secrets.token_hex(4).upper()}", amount_pesewas=amount,
                    paid_on=paid_on, method=method, covers_months=covers, note=note[:300],
                    recorded_by_id=getattr(by, "id", None))
    db.add(p)
    db.flush()
    return p


def record_payment(db: Session, landlord: User, r: Rental, amount_pesewas: int, paid_on: date, method: str,
                   covers_months: int, note: str = "") -> RentPayment:
    if r.landlord_id != landlord.id:
        raise NotFound("Tenant record not found.")
    if method not in METHODS[:3]:
        raise InvalidInput("Choose MoMo, bank or cash.")
    if amount_pesewas <= 0 or not 1 <= covers_months <= 24:
        raise InvalidInput("Enter the amount and the months it covers.")
    if paid_on > utcnow().date():
        raise InvalidInput("The payment date can't be in the future.")
    p = _payment(db, r, amount_pesewas, paid_on, method, covers_months, note, landlord)
    r.next_due_date = add_months(r.next_due_date, covers_months)
    db.flush()
    record(db, landlord, "rental.payment_recorded", p, amount=amount_pesewas)
    if r.tenant_user is not None:
        notify_on(db, r.tenant_user, "rent_receipt", {"in_app"}, link=f"/account/home/{r.id}",
                  amount=format_ghs(amount_pesewas), landlord=landlord.name, receipt=p.receipt_no)
    return p


def payments_for(db: Session, r: Rental) -> list[RentPayment]:
    return list(db.scalars(select(RentPayment).where(RentPayment.rental_id == r.id).order_by(RentPayment.paid_on.desc())))


def receipt_pdf(db: Session, r: Rental, p: RentPayment) -> bytes:
    from app.modules.documents.render import rent_receipt

    return rent_receipt(r, p)


def invoice_pdf(db: Session, r: Rental) -> bytes:
    """The next rent due, as an invoice the landlord can send and the tenant can keep."""
    from app.modules.documents.render import rent_invoice

    if r.status != RentalStatus.ACTIVE:
        raise RuleViolation("This tenancy has ended, so there's no rent to invoice.")
    return rent_invoice(r)


def send_rent_reminders(db: Session) -> dict[str, int]:
    """Daily: 7 days before rent is due, remind the landlord, and the tenant too if they have
    their own Afe account. Once more when it's 3 days overdue."""
    today = utcnow().date()
    counts = {"due_soon": 0, "overdue": 0}
    for r in db.scalars(select(Rental).where(Rental.status == RentalStatus.ACTIVE, Rental.next_due_date <= today + timedelta(days=7),
                                             Rental.next_due_date < Rental.end_date)):
        overdue = r.next_due_date <= today - timedelta(days=3)
        if r.reminded_for == r.next_due_date and not overdue:
            continue
        if overdue and r.reminded_for == r.next_due_date + timedelta(days=3):
            continue
        amount = format_ghs(r.rent_pesewas * r.pay_every_months)
        when = r.next_due_date.strftime("%d %b")
        template = "rent_overdue" if overdue else "rent_due"
        notify_on(db, r.landlord, template, {"in_app", "sms"}, link=f"/landlord/rentals/{r.id}",
                  tenant=r.tenant_name, amount=amount, when=when)
        if r.tenant_user is not None and not overdue:
            notify_on(db, r.tenant_user, "rent_due_tenant", {"in_app", "sms"}, link=f"/account/home/{r.id}",
                      amount=amount, when=when, landlord=r.landlord.name)
        r.reminded_for = r.next_due_date + timedelta(days=3) if overdue else r.next_due_date
        counts["overdue" if overdue else "due_soon"] += 1
    db.flush()
    return counts


# --- Maintenance ---------------------------------------------------------------------------------------------


def raise_maintenance(db: Session, user: User, r: Rental, title: str, details: str, photo: bytes | None = None) -> Maintenance:
    if user.id not in (r.landlord_id, r.tenant_user_id):
        raise NotFound("Tenant record not found.")
    if len(title.strip()) < 3 or len(details.strip()) < 10:
        raise InvalidInput("Say what needs fixing and where.")
    key = ""
    if photo:
        from app.modules.media.images import process_photo
        from app.modules.media.storage import storage

        key = storage.save("private", "maintenance", process_photo(photo).webp, ".webp")
    m = Maintenance(rental_id=r.id, raised_by_id=user.id, title=title.strip()[:120], details=details.strip()[:4000], photo_key=key)
    db.add(m)
    db.flush()
    if user.id != r.landlord_id:
        notify_on(db, r.landlord, "maintenance_raised", {"in_app", "sms"}, link=f"/landlord/rentals/{r.id}",
                  tenant=r.tenant_name, title=m.title)
    return m


def update_maintenance(db: Session, landlord: User, m: Maintenance, status: str, note: str = "") -> Maintenance:
    r = db.get(Rental, m.rental_id)
    if r.landlord_id != landlord.id:
        raise NotFound("Request not found.")
    if status not in ("open", "in_progress", "done"):
        raise InvalidInput("Choose open, in progress or done.")
    m.status, m.landlord_note, m.updated_at = status, note.strip()[:500], utcnow()
    db.flush()
    if r.tenant_user is not None:
        notify_on(db, r.tenant_user, "maintenance_updated", {"in_app"}, link=f"/account/home/{r.id}",
                  title=m.title, status=status.replace("_", " "))
    return m


def maintenance_for(db: Session, r: Rental) -> list[Maintenance]:
    return list(db.scalars(select(Maintenance).where(Maintenance.rental_id == r.id).order_by(Maintenance.id.desc())))


# --- Agreements -------------------------------------------------------------------------------------------------


def agreement_text(r: Rental) -> str:
    home = str(r.unit) if r.unit else "the home agreed between the parties"
    return "\n".join([
        f"Tenancy agreement between {r.landlord.name} (landlord) and {r.tenant_name} (tenant) for {home}.",
        f"Term: {r.start_date:%d %B %Y} to {r.end_date:%d %B %Y}.",
        f"Rent: {format_ghs(r.rent_pesewas)} a month, paid {r.pay_every_months} month(s) at a time.",
        "Under the Rent Act, 1963 (Act 220), advance rent may not exceed six months for a tenancy of more than six "
        "months. The landlord gives a receipt for every payment. Either side may raise a repair request on Afe.",
        "Notice: either side gives at least one month's written notice before the end of the term if they do not "
        "wish to renew.",
    ])


def create_agreement(db: Session, landlord: User, r: Rental) -> Agreement:
    if r.landlord_id != landlord.id:
        raise NotFound("Tenant record not found.")
    if r.tenant_user_id is None:
        raise RuleViolation("The tenant needs an Afe account with the phone number on this record to sign.")
    body = agreement_text(r)
    a = Agreement(rental_id=r.id, body=body, body_hash=hashlib.sha256(body.encode()).hexdigest())
    db.add(a)
    db.flush()
    record(db, landlord, "agreement.created", a)
    notify_on(db, r.tenant_user, "agreement_to_sign", {"in_app", "sms"}, link=f"/account/home/{r.id}", landlord=landlord.name)
    return a


def sign_agreement(db: Session, user: User, a: Agreement, typed_name: str) -> Agreement:
    """Sign by typing your full name. The name must match your Afe account; the signature is tied
    to the exact text by its hash, and every signature is in the audit log."""
    from app.modules.tenancies.service import names_match

    r = db.get(Rental, a.rental_id)
    if user.id not in (r.landlord_id, r.tenant_user_id):
        raise NotFound("Agreement not found.")
    if hashlib.sha256(a.body.encode()).hexdigest() != a.body_hash:
        raise RuleViolation("This agreement has changed since it was prepared. Prepare a new one.")
    if not names_match(user.name, typed_name) and user.name.strip().lower() != typed_name.strip().lower():
        raise InvalidInput(f"Type your full name as it is on your Afe account ({user.name}).")
    now = utcnow()
    if user.id == r.landlord_id:
        if a.landlord_signed_at:
            raise RuleViolation("You've already signed.")
        a.landlord_signed_name, a.landlord_signed_at = typed_name.strip(), now
    else:
        if a.tenant_signed_at:
            raise RuleViolation("You've already signed.")
        a.tenant_signed_name, a.tenant_signed_at = typed_name.strip(), now
    db.flush()
    record(db, user, "agreement.signed", a, hash=a.body_hash)
    return a


def agreement_pdf(a: Agreement) -> bytes:
    from app.core.pdf import text_pdf

    lines = a.body.split("\n")
    for who, name, at in (("Landlord", a.landlord_signed_name, a.landlord_signed_at), ("Tenant", a.tenant_signed_name, a.tenant_signed_at)):
        lines.append(f"{who}: signed by {name} on {at:%d %B %Y at %H:%M} UTC." if at else f"{who}: not signed yet.")
    lines.append(f"Document fingerprint (SHA-256): {a.body_hash}")
    return text_pdf("Tenancy agreement", lines)


def agreements_for(db: Session, r: Rental) -> list[Agreement]:
    return list(db.scalars(select(Agreement).where(Agreement.rental_id == r.id).order_by(Agreement.id.desc())))


# --- Renewals ---------------------------------------------------------------------------------------------------


def offer_renewal(db: Session, landlord: User, r: Rental, new_end_date: date, new_rent_pesewas: int, advance_months: int) -> Renewal:
    if r.landlord_id != landlord.id:
        raise NotFound("Tenant record not found.")
    if new_end_date <= r.end_date:
        raise InvalidInput("The new end date must be after the current one.")
    months = (new_end_date.year - r.end_date.year) * 12 + new_end_date.month - r.end_date.month
    cap = rule(db, "advance_cap_months_long" if months > 6 else "advance_cap_months_short")
    if not 0 <= advance_months <= cap:
        raise RuleViolation(f"The law caps advance rent at {cap} months for a {months}-month renewal.")
    if new_rent_pesewas <= 0:
        raise InvalidInput("Enter the new rent.")
    rn = Renewal(rental_id=r.id, new_end_date=new_end_date, new_rent_pesewas=new_rent_pesewas, advance_months=advance_months)
    db.add(rn)
    db.flush()
    record(db, landlord, "renewal.offered", rn)
    if r.tenant_user is not None:
        notify_on(db, r.tenant_user, "renewal_offered", {"in_app", "sms"}, link=f"/account/home/{r.id}",
                  landlord=landlord.name, rent=format_ghs(new_rent_pesewas), until=new_end_date.strftime("%d %b %Y"))
    return rn


def decide_renewal(db: Session, tenant: User, rn: Renewal, accept: bool) -> Renewal:
    r = db.get(Rental, rn.rental_id)
    if r.tenant_user_id != tenant.id:
        raise NotFound("Renewal not found.")
    if rn.status != "offered":
        raise RuleViolation("This renewal is already decided.")
    rn.status, rn.decided_at = ("accepted" if accept else "declined"), utcnow()
    if accept:
        r.end_date, r.rent_pesewas = rn.new_end_date, rn.new_rent_pesewas
    db.flush()
    record(db, tenant, "renewal.decided", rn, accepted=accept)
    notify_on(db, r.landlord, "renewal_decided", {"in_app", "sms"}, link=f"/landlord/rentals/{r.id}",
              tenant=r.tenant_name, result="accepted" if accept else "declined")
    return rn


def renewals_for(db: Session, r: Rental) -> list[Renewal]:
    return list(db.scalars(select(Renewal).where(Renewal.rental_id == r.id).order_by(Renewal.id.desc())))


# --- Agent workspace ----------------------------------------------------------------------------------------------


def homes_by_owner(db: Session, agent: User) -> list[dict]:
    """For agents: the homes they manage, grouped by the owner who authorised them."""
    from app.modules.units.models import AuthorityRecord, AuthorityStatus, Unit

    rows = db.execute(
        select(AuthorityRecord.owner_name, AuthorityRecord.owner_phone, Unit)
        .join(Unit, AuthorityRecord.unit_id == Unit.id)
        .where(AuthorityRecord.party_id == agent.id, AuthorityRecord.status == AuthorityStatus.ACCEPTED)
    ).all()
    owners: dict[str, dict] = {}
    for name, phone, unit in rows:
        key = name or phone or "Owner not named"
        owners.setdefault(key, {"owner": key, "homes": []})["homes"].append(unit)
    return list(owners.values())
