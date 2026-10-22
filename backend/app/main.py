"""Afe API. The web frontend is a separate app (frontend/) that talks to this API only."""

import json
import logging
import mimetypes
import secrets
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import router as api_router
from app.config import get_settings
from app.core.envelope import Envelope, ErrorBody
from app.core.errors import DomainError

# Some platforms (e.g. Windows) don't map .webp, which would serve photos as octet-stream.
mimetypes.add_type("image/webp", ".webp")

log = logging.getLogger("afe.errors")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}


def _error(status: int, code: str, message: str, reasons: list[str] | None = None) -> JSONResponse:
    body = Envelope(error=ErrorBody(code=code, message=message, reasons=reasons or []))
    return JSONResponse(body.model_dump(), status_code=status)


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.debug or settings.allow_fake_providers:
        # Show what the fake SMS/WhatsApp/email providers "send", including sign-in codes
        # (also on the free development server, which runs with debug off).
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = FastAPI(
        title="Afe API",
        version="0.2.0",
        description="Verified homes and protected rent for renters in Accra. Responses use the "
        "{ data, meta, error } envelope; authenticate with a bearer access token from /api/v1/auth.",
        # The API reference is for developers: only served in development.
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.debug else None,
    )
    public_media = (urlparse(settings.media_url).path or "/media").rstrip("/") + "/"

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(public_media):
            # Public listing photos are shown by the website and the app, which are other origins
            # (in development, localhost:5173 vs 127.0.0.1:8000). Private files never live here.
            response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/v1"):
            response.headers.setdefault("Cache-Control", "no-store")  # nearly everything here is personal
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        """One JSON line per unexpected error (a CloudWatch alarm counts them), and a reference
        the person can quote to support. Never the error details: they may hold personal data."""
        ref = secrets.token_hex(4).upper()
        log.error(json.dumps({"event": "unhandled_error", "ref": ref, "path": request.url.path,
                              "method": request.method, "type": type(exc).__name__}), exc_info=exc)
        return _error(500, "server_error", f"Something went wrong on our side. Quote reference {ref} if you contact Afe.")

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return _error(exc.status_code, exc.code, exc.message, exc.reasons)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        reasons = [f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return _error(422, "invalid_input", "Some fields are missing or wrong.", reasons)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        message = "Not found." if exc.status_code == 404 else str(exc.detail)
        return _error(exc.status_code, "http_error", message)

    @app.get("/healthz", include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "afe-api", "docs": "/api/docs"}

    app.include_router(api_router)
    if settings.debug:
        # In production CloudFront serves listing photos from the public bucket.
        settings.media_root.mkdir(parents=True, exist_ok=True)
        mount_at = urlparse(settings.media_url).path or "/media"
        app.mount(mount_at, StaticFiles(directory=settings.media_root), name="media")
    return app


app = create_app()
