"""Before a deploy: can this image run against this environment? `python -m app.preflight`

Run it as a one-off ECS task with the new image and the environment's settings and secrets, before the migrations
and before the services change (docs/deploy.md). It reads; it never changes anything. It exits 1 if a check fails.

It is its own entry point, not a `python -m app.cli` command: importing the CLI connects to the database, which needs
settings that load, and a broken setting has to show up here as a failed check, not as a traceback.
"""

import sys
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.config import BASE_DIR, Settings

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
# What each real provider needs. Only the names are ever printed, never the values.
PROVIDER_SECRETS = {
    "AFE_PAYSTACK_SECRET_KEY": "paystack_secret_key",
    "AFE_WHATSAPP_ACCESS_TOKEN": "whatsapp_access_token",
    "AFE_WHATSAPP_APP_SECRET": "whatsapp_app_secret",
    "AFE_WHATSAPP_VERIFY_TOKEN": "whatsapp_verify_token",
    "AFE_WHATSAPP_PHONE_NUMBER_ID": "whatsapp_phone_number_id",
    "AFE_HUBTEL_CLIENT_ID": "hubtel_client_id",
    "AFE_HUBTEL_CLIENT_SECRET": "hubtel_client_secret",
    "AFE_EMAIL_FROM": "email_from",
}
FAKE_CHECKED = ("kyc_provider", "sms_provider", "whatsapp_provider", "email_provider", "payment_provider",
                "malware_scanner")


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok, warn, fail or skip
    detail: str


def _settings(factory: Callable[[], Settings]) -> tuple[Check, Settings | None]:
    try:
        s = factory()
    except ValidationError as exc:
        reasons = "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
        return Check("settings", FAIL, f"Settings don't load: {reasons}"), None
    if s.debug:
        return Check("settings", FAIL, "AFE_DEBUG is on: development settings in a deployed environment"), s
    fakes = [f"AFE_{name.upper()}" for name in FAKE_CHECKED if ".Fake" in getattr(s, name)]
    if s.allow_fake_providers:
        using = f" (in use: {', '.join(fakes)})" if fakes else ""
        return Check("settings", WARN, f"AFE_ALLOW_FAKE_PROVIDERS is on{using}: only until the KYC partner is chosen "
                                       "(B5), never in production."), s
    return Check("settings", OK, "Production settings load."), s


def _provider_secrets(s: Settings) -> Check:
    missing = sorted(name for name, field in PROVIDER_SECRETS.items() if not getattr(s, field))
    if missing:
        return Check("provider secrets", WARN, f"Not set: {', '.join(missing)}")
    return Check("provider secrets", OK, "Every provider has its settings.")


def _database(url: str) -> Check:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any failure to connect is the finding
        first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        return Check("database", FAIL, f"Can't connect: {type(exc).__name__}: {first_line}"[:300])
    finally:
        engine.dispose()
    return Check("database", OK, "Connected.")


def _ancestors(script, revisions) -> set[str]:
    seen, stack = set(), list(revisions)
    while stack:
        revision = stack.pop()
        if revision is None or revision in seen:
            continue
        seen.add(revision)
        down = script.get_revision(revision).down_revision
        stack.extend(down if isinstance(down, tuple) else [down])
    return seen


def _migrations(url: str) -> Check:
    # Imported here: loading the migration scripts imports the app, which needs settings that load.
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from alembic.script.revision import RevisionError
    from alembic.util import CommandError

    script = ScriptDirectory.from_config(Config(str(BASE_DIR / "alembic.ini")))
    heads = set(script.get_heads())
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
    finally:
        engine.dispose()
    if current == heads:
        return Check("migrations", OK, f"At {', '.join(sorted(heads))}, the code's latest.")
    if not current:
        return Check("migrations", WARN, "An empty database: every migration to apply. Run alembic upgrade head "
                                         "before the services start.")
    unknown = []
    for revision in sorted(current):
        try:
            script.get_revision(revision)
        except (RevisionError, CommandError):
            unknown.append(revision)
    if unknown:
        return Check("migrations", FAIL, f"The database is at {', '.join(unknown)}, which is newer than this image "
                                         "(or from another branch). Rolling back to this image is safe only if the "
                                         "newer migrations only add tables or columns (docs/deploy.md, Rolling "
                                         "back); otherwise deploy an image that has them.")
    pending = _ancestors(script, heads) - _ancestors(script, current)
    return Check("migrations", WARN, f"{len(pending)} to apply ({', '.join(sorted(pending)[:5])}): run alembic "
                                     "upgrade head before the services change.")


def run(settings_factory: Callable[[], Settings] = Settings, database_url: str | None = None) -> list[Check]:
    """Every check, in order. Settings come first: if they don't load, the rest can't run and is skipped."""
    settings_check, s = _settings(settings_factory)
    if s is None:
        return [settings_check, *(Check(name, SKIP, "Settings must load first.")
                                  for name in ("provider secrets", "database", "migrations"))]
    checks = [settings_check, _provider_secrets(s)]
    url = database_url or s.database_url
    database = _database(url)
    checks.append(database)
    checks.append(_migrations(url) if database.status == OK
                  else Check("migrations", SKIP, "The database must be reachable first."))
    return checks


def report(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    return "\n".join(f"{c.status:<5} {c.name:<{width}}  {c.detail}" for c in checks)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status in (FAIL, SKIP) for c in checks) else 0


def main() -> int:
    checks = run()
    print(report(checks))
    return exit_code(checks)


if __name__ == "__main__":
    sys.exit(main())
