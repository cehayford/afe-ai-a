import logging
import re
from contextlib import contextmanager
from datetime import timedelta

from fastapi import Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.envelope import Envelope, ErrorBody
from app.core.errors import InvalidInput, NotFound, UploadRejected
from app.modules.accounts.service import SignInFailed, TooManyAttempts, rate_limit
from app.modules.audit.webhooks import REJECTED_BODY, keep

MAX_PHOTO_BYTES = 15 * 1024 * 1024


def get_or_404[T](db: Session, model: type[T], pk, what: str | None = None) -> T:
    obj = db.get(model, pk)
    if obj is None:
        raise NotFound(f"{what or model.__name__} not found.")
    return obj


async def read_upload(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise InvalidInput(f"File is larger than {limit // (1024 * 1024)} MB.")
    return data


def client_address(request: Request) -> str:
    """The visitor's address. The website passes the browser's address in X-Forwarded-For; the
    mobile apps come through the load balancer (or Caddy), which adds theirs. uvicorn's proxy-headers
    setting turns that into request.client, trusting only our own proxies (FORWARDED_ALLOW_IPS)."""
    return request.client.host if request.client else "unknown"


_DEVICE_ID = re.compile(r"^[0-9a-f-]{16,64}$")


def device_id(request: Request) -> str:
    """The web app's random per-browser ID (cookie afe_dev), if it sent a well-formed one."""
    value = (request.headers.get("x-afe-device-id") or "").lower()
    return value if _DEVICE_ID.match(value) else ""


def device(request: Request) -> str:
    """The frontend forwards the browser's user agent in X-Client-Device."""
    return (request.headers.get("x-client-device") or request.headers.get("user-agent") or "")[:200]


@contextmanager
def keep_attempts(db: Session):
    """Failed sign-ins must still count against the limits, so commit the attempt record
    before the error rolls the request back."""
    try:
        yield
    except (SignInFailed, TooManyAttempts, UploadRejected):
        db.commit()
        raise


def rejected(message: str = "Webhook rejected.") -> JSONResponse:
    """InvalidInput's 422, returned rather than raised so the request still commits (the evidence is kept)."""
    body = Envelope(error=ErrorBody(code=InvalidInput.code, message=message))
    return JSONResponse(body.model_dump(), status_code=InvalidInput.status_code)


# Unsigned webhook deliveries kept per address per hour; more are only logged, so nobody can fill the table.
REJECTED_PER_HOUR = 60


def refuse(db: Session, request: Request, source: str, endpoint: str, body: bytes, headers: dict[str, str],
           error: str) -> JSONResponse:
    """A webhook whose signature or content didn't check out: keep its start and fingerprint as evidence (at most
    REJECTED_PER_HOUR from one address), and answer 422."""
    try:
        rate_limit(db, f"webhook-rejected:{client_address(request)}", REJECTED_PER_HOUR, timedelta(hours=1), "")
    except TooManyAttempts:
        logging.getLogger("afe.webhooks").warning("rejected %s webhooks over the hourly limit", endpoint)
    else:
        keep(db, source, endpoint, body, headers, "rejected", error=error, max_body=REJECTED_BODY)
    return rejected()
