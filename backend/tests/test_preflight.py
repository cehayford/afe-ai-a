"""Preflight: before a deploy, can this image run against this environment's settings, secrets and database?"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app import preflight
from app.config import Settings

ALEMBIC_INI = str(Path(__file__).parent.parent / "alembic.ini")
PRODUCTION = dict(
    debug=False, secret_key="k" * 40, database_url="postgresql+psycopg://afe@db.internal/afe", storage_backend="s3",
    allow_fake_providers=False, kyc_provider="x.Real", sms_provider="x.Real", whatsapp_provider="x.Real",
    email_provider="x.Real", payment_provider="x.Real", malware_scanner="x.Real",
)
SECRETS = dict(
    paystack_secret_key="sk_live_SECRET", whatsapp_access_token="EAAG-SECRET", whatsapp_app_secret="app-secret",
    whatsapp_verify_token="verify", whatsapp_phone_number_id="1234567890", hubtel_client_id="hubtel-id",
    hubtel_client_secret="hubtel-SECRET", email_from="Afe <no-reply@afe.example>",
)


def settings(**changes):
    return lambda: Settings(_env_file=None, **{**PRODUCTION, **SECRETS, **changes})


def database(tmp_path, to="head") -> str:
    url = f"sqlite:///{tmp_path / 'deployed.db'}"
    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", url)
    if to:
        command.upgrade(cfg, to)
    else:
        create_engine(url).connect().close()  # an empty database
    return url


def results(checks) -> dict[str, tuple[str, str]]:
    return {c.name: (c.status, c.detail) for c in checks}


def test_a_ready_environment_passes(tmp_path):
    checks = preflight.run(settings(), database_url=database(tmp_path))
    assert {name: status for name, (status, _) in results(checks).items()} == {
        "settings": "ok", "provider secrets": "ok", "database": "ok", "migrations": "ok"}
    assert preflight.exit_code(checks) == 0


def test_settings_that_wont_load_fail_and_the_rest_is_skipped(tmp_path):
    checks = results(preflight.run(settings(secret_key="short"), database_url=database(tmp_path)))
    assert checks["settings"][0] == "fail" and "AFE_SECRET_KEY must be at least 32 characters" in checks["settings"][1]
    assert checks["database"][0] == checks["migrations"][0] == "skip"
    assert preflight.exit_code(preflight.run(settings(secret_key="short"))) == 1


def test_development_settings_fail(tmp_path):
    checks = results(preflight.run(settings(debug=True), database_url=database(tmp_path)))
    assert checks["settings"] == ("fail", "AFE_DEBUG is on: development settings in a deployed environment")


def test_fake_providers_allowed_is_a_warning(tmp_path):
    checks = results(preflight.run(settings(allow_fake_providers=True, kyc_provider="x.FakeKyc"),
                                   database_url=database(tmp_path)))
    assert checks["settings"][0] == "warn" and "AFE_ALLOW_FAKE_PROVIDERS" in checks["settings"][1]


def test_missing_provider_secrets_are_named_and_no_value_is_shown(tmp_path):
    checks = preflight.run(settings(whatsapp_access_token="", hubtel_client_secret=""), database_url=database(tmp_path))
    status, detail = results(checks)["provider secrets"]
    assert status == "warn" and detail == "Not set: AFE_HUBTEL_CLIENT_SECRET, AFE_WHATSAPP_ACCESS_TOKEN"
    printed = preflight.report(checks)
    for value in SECRETS.values():
        assert value not in printed


def test_an_unreachable_database_fails(tmp_path):
    checks = results(preflight.run(settings(), database_url=f"sqlite:///{tmp_path / 'missing' / 'dir' / 'x.db'}"))
    assert checks["database"][0] == "fail" and checks["migrations"][0] == "skip"


def test_migrations_waiting_to_run_are_a_warning(tmp_path):
    empty = results(preflight.run(settings(), database_url=database(tmp_path, to=None)))["migrations"]
    assert empty[0] == "warn" and "empty database" in empty[1]


def test_an_older_database_lists_what_to_apply(tmp_path):
    url = database(tmp_path, to="82447f99cb7e")  # before the merge migration
    status, detail = results(preflight.run(settings(), database_url=url))["migrations"]
    assert status == "warn" and "to apply" in detail and "alembic upgrade head" in detail


def test_a_database_newer_than_the_code_fails(tmp_path):
    url = database(tmp_path)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'ffffffffffff'"))
    engine.dispose()
    status, detail = results(preflight.run(settings(), database_url=url))["migrations"]
    assert status == "fail" and "ffffffffffff" in detail and "newer than this image" in detail
    assert "only add tables or columns" in detail and "docs/deploy.md" in detail  # how to judge a rollback


@pytest.mark.parametrize(("statuses", "code"), [(["ok", "warn"], 0), (["ok", "fail"], 1), (["skip"], 1)])
def test_exit_code(statuses, code):
    assert preflight.exit_code([preflight.Check(str(i), s, "") for i, s in enumerate(statuses)]) == code
