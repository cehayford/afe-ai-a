"""Request dependencies. The API is bearer-token only: the separate frontend keeps tokens
in its own httpOnly cookies and calls the API server-to-server, and native apps send the
token directly. No cookie ever authenticates an API call, so there is no CSRF surface."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotAllowed
from app.core.security import read_access_token
from app.db import get_db
from app.modules.accounts.models import LISTER_ROLES, REVIEWER_ROLES, Role, User

DB = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="Access token from /api/v1/auth")


class NotAuthenticated(DomainError):
    status_code = 401
    code = "not_authenticated"


def _user_from(db: Session, creds: HTTPAuthorizationCredentials | None) -> User | None:
    user_id = read_access_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    return user if user is not None and user.is_active else None


def api_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> User:
    user = _user_from(db, creds)
    if user is None:
        raise NotAuthenticated("Sign in to continue.")
    return user


def optional_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> User | None:
    return _user_from(db, creds)


ApiUser = Annotated[User, Depends(api_user)]
MaybeUser = Annotated[User | None, Depends(optional_user)]


def api_roles(*roles: Role):
    def dependency(user: ApiUser) -> User:
        if user.role not in roles:
            raise NotAllowed("Your account cannot do this.")
        return user

    return Depends(dependency)


Lister = Annotated[User, api_roles(*LISTER_ROLES)]
Verifier = Annotated[User, api_roles(Role.FIELD_VERIFIER)]
Reviewer = Annotated[User, api_roles(*REVIEWER_ROLES)]
Renter = Annotated[User, api_roles(Role.RENTER)]
