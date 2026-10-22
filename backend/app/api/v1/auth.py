"""Sign-up and sign-in. Flow for the frontend:

1. POST /auth/code {phone, purpose, channel?} -> a 6-digit code by SMS (default) or WhatsApp
2. POST /auth/signup or /auth/signin/code       -> SignInOut
   (staff can use POST /auth/signin/password instead)
3. If status is mfa_setup or mfa_required: POST /auth/mfa {mfa_token, code} -> signed_in
4. Keep access_token (15 min) and refresh_token (30 days); POST /auth/refresh rotates both.
"""

from fastapi import APIRouter, Request

from app.core.envelope import Envelope, ok
from app.deps import DB, ApiUser
from app.modules.accounts import service as accounts

from .. import schemas as s
from .common import device, device_id, keep_attempts

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/code", response_model=Envelope[dict], status_code=202)
def request_code(db: DB, body: s.CodeRequestIn):
    """Always answers the same way, so it can't be used to find out who has an account."""
    with keep_attempts(db):
        accounts.request_code(db, body.phone, body.purpose, body.channel)
    return ok({"sent": True})


@router.post("/signup", response_model=Envelope[s.SignInOut], status_code=201)
def sign_up(db: DB, request: Request, body: s.SignUpIn):
    with keep_attempts(db):
        user = accounts.sign_up_with_code(db, body.phone, body.code, body.display_name, body.role, body.accept_privacy)
    return ok(s.SignInOut.of(accounts.begin_session(db, user, device(request), device_id(request))))


@router.post("/signin/code", response_model=Envelope[s.SignInOut])
def sign_in_with_code(db: DB, request: Request, body: s.CodeSignInIn):
    with keep_attempts(db):
        user = accounts.sign_in_with_code(db, body.phone, body.code)
    return ok(s.SignInOut.of(accounts.begin_session(db, user, device(request), device_id(request))))


@router.post("/signin/password", response_model=Envelope[s.SignInOut])
def sign_in_with_password(db: DB, request: Request, body: s.PasswordSignInIn):
    with keep_attempts(db):
        user = accounts.sign_in_with_password(db, body.login, body.password)
    return ok(s.SignInOut.of(accounts.begin_session(db, user, device(request), device_id(request))))


@router.post("/mfa", response_model=Envelope[s.SignInOut])
def mfa(db: DB, request: Request, body: s.MfaIn):
    with keep_attempts(db):
        result = accounts.complete_mfa(db, body.mfa_token, body.code, device(request), device_id(request))
    return ok(s.SignInOut.of(result))


@router.post("/refresh", response_model=Envelope[s.SignInOut])
def refresh(db: DB, request: Request, body: s.RefreshIn):
    with keep_attempts(db):
        result = accounts.refresh(db, body.refresh_token, device(request))
    return ok(s.SignInOut.of(result))


@router.post("/signout", response_model=Envelope[dict])
def sign_out(db: DB, body: s.RefreshIn):
    accounts.sign_out(db, body.refresh_token)
    return ok({"signed_out": True})


@router.post("/signout/everywhere", response_model=Envelope[dict])
def sign_out_everywhere(db: DB, user: ApiUser):
    return ok({"devices": accounts.sign_out_everywhere(db, user)})
