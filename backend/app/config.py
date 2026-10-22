"""Afe settings, all from environment variables (prefix AFE_), with a .env file for local use.

Local development runs on SQLite with no extra services. Staging and production set
AFE_DATABASE_URL to PostgreSQL.
"""

from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AFE_", env_file=BASE_DIR / ".env", extra="ignore")

    debug: bool = False
    secret_key: str = ""
    database_url: str = f"sqlite:///{BASE_DIR / 'afe.db'}"
    # Where the separate frontend runs; used in links sent by SMS and for payment returns.
    frontend_url: str = "http://localhost:5173"

    media_root: Path = BASE_DIR / "var" / "media"
    private_media_root: Path = BASE_DIR / "var" / "private"
    # "local" (folders on disk) or "s3" (the buckets Terraform creates).
    storage_backend: str = "local"
    s3_region: str = "af-south-1"
    s3_bucket_public: str = "afe-media-public"
    s3_bucket_private: str = "afe-kyc-private"
    # Only for S3-compatible stores in development (e.g. MinIO); leave empty on AWS.
    s3_endpoint_url: str = ""
    # Public address of listing photos. The frontend is a separate site, so this is absolute:
    # the API itself in development, CloudFront in production.
    media_url: str = "http://127.0.0.1:8000/media"

    # --- Sign-in -------------------------------------------------------------------------
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    # scrypt cost. 2**14 is the OWASP minimum; tests lower it for speed.
    password_scrypt_n: int = 2**14
    # Landlords, agents and staff must use an authenticator app (Statement §5.1).
    mfa_enforced: bool = True
    otp_minutes: int = 10
    otp_max_attempts: int = 5
    otp_per_phone_per_hour: int = 5
    login_attempts_per_15_min: int = 10

    # --- Providers (dotted paths). Fakes are refused outside debug. ------------------------
    kyc_provider: str = "app.modules.identity.providers.FakeKycProvider"
    sms_provider: str = "app.modules.notifications.providers.FakeSms"
    whatsapp_provider: str = "app.modules.notifications.providers.FakeWhatsApp"
    email_provider: str = "app.modules.notifications.providers.FakeEmail"
    payment_provider: str = "app.modules.billing.providers.FakePayments"
    # Uploaded documents are scanned before storage. ClamAV (clamd) in staging and production.
    malware_scanner: str = "app.modules.media.scan.FakeScanner"
    clamd_host: str = "127.0.0.1"
    clamd_port: int = 3310
    # Protected payments (Phase 2). Off until counsel's written opinion and a licensed partner (gate B7).
    protected_payments_enabled: bool = False
    escrow_partner: str = "app.modules.tenancies.partners.TestEscrow"
    allow_fake_providers: bool = False

    # WhatsApp Cloud API webhook: the verify token set in the Meta app, and the app secret
    # used to sign webhook bodies.
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    # Sending on WhatsApp (WhatsAppCloud): the business phone number and a system-user token. Each event goes
    # through its own approved template (notifications/whatsapp_templates.py).
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_template_language: str = "en"
    whatsapp_graph_version: str = "v21.0"
    # The WhatsApp Business Account that owns the templates (`python -m app.cli whatsapp-templates --submit`).
    whatsapp_business_account_id: str = ""
    # SMS (HubtelSms) and email (SesEmail on AWS; ResendEmail or SmtpEmail on the free server).
    hubtel_client_id: str = ""
    hubtel_client_secret: str = ""
    sms_sender_id: str = "Afe"
    email_from: str = ""
    ses_region: str = ""
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"  # starttls, ssl or none
    # Paystack secret key: signs webhook bodies (HMAC-SHA512) and authorises API calls.
    paystack_secret_key: str = ""

    # --- Phase 3 detection. Models start in shadow; modes are rules (two reviewers). --------
    text_model: str = "app.modules.detection.text.HeuristicTextModel"
    # Used by the scam_text_llm detector (off until counsel clears B11). Text is redacted before it is sent.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    # The reviewer copilot (agents module): which model and how much effort. It runs only when two reviewers set the
    # rule agent_copilot_level, which waits on counsel's opinion on sending masked case facts abroad (B11).
    agent_copilot_model: str = "claude-opus-5-5"
    agent_copilot_effort: str = "medium"

    # Secret used to hash Ghana Card numbers so duplicates can be found without storing them.
    pii_hash_key: str = ""

    # --- Trust rules from the build plan. These become versioned compliance rules in Phase 2.
    verification_valid_days: int = 365
    field_visit_max_age_days: int = 30
    field_visit_radius_m: int = 150
    min_visit_photos: int = 4
    # A verifier may not verify the same landlord twice in a row (plan §5). Turn off only
    # while Afe has a single verifier (Phase 0).
    rotate_verifiers: bool = True
    photo_duplicate_distance: int = 6
    price_anomaly_ratio: float = 0.6
    advance_cap_months: int = 6
    # Verification fee per home, in pesewas (decision B6). 0 = free while the price is set.
    verification_fee_pesewas: int = 0

    @model_validator(mode="after")
    def _production_guards(self):
        if not self.secret_key:
            if not self.debug:
                raise ValueError("AFE_SECRET_KEY must be set when AFE_DEBUG is off")
            self.secret_key = "dev-only-insecure-key-not-for-production"  # noqa: S105 - only reachable in debug
        if not self.debug and len(self.secret_key) < 32:
            raise ValueError("AFE_SECRET_KEY must be at least 32 characters")
        if not self.pii_hash_key:
            self.pii_hash_key = self.secret_key
        if self.smtp_security not in ("starttls", "ssl", "none"):
            raise ValueError("AFE_SMTP_SECURITY must be starttls, ssl or none")
        if self.storage_backend not in ("local", "s3"):
            raise ValueError("AFE_STORAGE_BACKEND must be local or s3")
        if not self.debug and self.storage_backend != "s3":
            raise ValueError("Use AFE_STORAGE_BACKEND=s3 outside development; local disk is lost on redeploy")
        if not self.debug and not self.database_url.startswith("postgresql"):
            # SQLite is for development and tests only. Beta (staging) and production run on PostgreSQL.
            raise ValueError("Use PostgreSQL for AFE_DATABASE_URL outside development; SQLite is for local use only")
        if not self.debug and not self.allow_fake_providers:
            fakes = [
                name
                for name in (
                    "kyc_provider", "sms_provider", "whatsapp_provider", "email_provider", "payment_provider",
                    "malware_scanner",
                )
                if ".Fake" in getattr(self, name)
            ]
            if self.protected_payments_enabled and self.escrow_partner.endswith("TestEscrow"):
                fakes.append("escrow_partner")
            if fakes:
                raise ValueError(
                    f"Set real providers outside development: {', '.join(f'AFE_{n.upper()}' for n in fakes)}"
                )
        return self

    @property
    def verification_valid_for(self) -> timedelta:
        return timedelta(days=self.verification_valid_days)

    @property
    def field_visit_max_age(self) -> timedelta:
        return timedelta(days=self.field_visit_max_age_days)


@lru_cache
def get_settings() -> Settings:
    return Settings()
