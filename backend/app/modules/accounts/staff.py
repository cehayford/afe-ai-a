"""Staff accounts: field verifiers, reviewers and admins, managed by an admin in the app.

New staff have no password: they sign in with a code sent to their phone, then must set up
an authenticator app before they can do anything (staff always need the second step)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import InvalidInput, NotAllowed, RuleViolation
from app.core.ghana import normalise_phone
from app.modules.audit.log import record
from app.modules.notifications.service import send_direct

from .models import STAFF_ROLES, Role, User
from .service import create_user, sign_out_everywhere


def _require_admin(actor: User) -> None:
    if actor.role != Role.ADMIN:
        raise NotAllowed("Only an Afe admin can manage staff.")


def list_staff(db: Session, actor: User) -> list[User]:
    _require_admin(actor)
    return list(db.scalars(select(User).where(User.role.in_([str(r) for r in STAFF_ROLES])).order_by(User.id)))


def _active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active.is_(True)))


def add_staff(db: Session, actor: User, name: str, phone: str, role: str) -> User:
    _require_admin(actor)
    if role not in {str(r) for r in STAFF_ROLES}:
        raise InvalidInput("Choose field verifier, reviewer or admin.")
    name = " ".join((name or "").split())
    if len(name) < 3:
        raise InvalidInput("Enter the person's full name.")
    phone = normalise_phone(phone)
    if db.scalar(select(User.id).where(User.phone == phone)):
        raise RuleViolation("That phone number already has an Afe account.")
    username = f"staff-{phone[-9:]}"
    user = create_user(db, username, None, Role(role), name, phone)
    record(db, actor, "staff.added", user, role=role)
    send_direct(db, "sms", phone, "staff_invite", user_id=user.id, name=name.split()[0],
                url=f"{get_settings().frontend_url}/signin")
    return user


def change_role(db: Session, actor: User, user: User, role: str) -> User:
    _require_admin(actor)
    if user.id == actor.id:
        raise RuleViolation("Ask another admin to change your own role.")
    if user.role not in {str(r) for r in STAFF_ROLES} or role not in {str(r) for r in STAFF_ROLES}:
        raise InvalidInput("Only staff roles can be changed here.")
    if user.role == Role.ADMIN and role != Role.ADMIN and user.is_active and _active_admins(db) <= 1:
        raise RuleViolation("Afe must keep at least one active admin.")
    old, user.role = user.role, role
    db.flush()
    sign_out_everywhere(db, user)  # new permissions take effect at the next sign-in
    record(db, actor, "staff.role_changed", user, old=old, new=role)
    return user


def set_active(db: Session, actor: User, user: User, active: bool) -> User:
    _require_admin(actor)
    if user.id == actor.id:
        raise RuleViolation("You can't deactivate your own account.")
    if user.role not in {str(r) for r in STAFF_ROLES}:
        raise InvalidInput("Only staff accounts are managed here.")
    if not active and user.role == Role.ADMIN and user.is_active and _active_admins(db) <= 1:
        raise RuleViolation("Afe must keep at least one active admin.")
    user.is_active = active
    db.flush()
    if not active:
        sign_out_everywhere(db, user)
    record(db, actor, "staff.activated" if active else "staff.deactivated", user)
    return user


def suspend_account(db: Session, actor: User, user: User, active: bool, reason: str = "") -> User:
    """Suspend or restore a renter, landlord or agent: for a suspected account takeover or a scam
    that's still being checked. A suspended person can't sign in, is signed out everywhere, and no
    money is released to them until an admin restores the account."""
    from app.modules.notifications.service import notify

    _require_admin(actor)
    if user.role in {str(r) for r in STAFF_ROLES}:
        raise InvalidInput("Staff accounts are managed on the Staff page.")
    reason = reason.strip()
    if not active and len(reason) < 10:
        raise InvalidInput("Say why you're suspending this account. It goes in the audit log.")
    if user.is_active == active:
        return user
    user.is_active = active
    db.flush()
    if active:
        notify(db, user, "account_restored")
    else:
        sign_out_everywhere(db, user)
        notify(db, user, "account_suspended")
    record(db, actor, "account.restored" if active else "account.suspended", user, reason=reason)
    return user
