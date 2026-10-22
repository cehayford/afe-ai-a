"""The S3 storage backend, against a simulated S3 (moto)."""

import boto3
import pytest
from moto import mock_aws

from app.config import get_settings
from app.modules.media.storage import S3Storage, get_storage, reset_storage, storage


@pytest.fixture
def s3(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_region", "af-south-1")
    monkeypatch.setattr(settings, "media_url", "https://media.afe.example")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        client = boto3.client("s3", region_name="af-south-1")
        for bucket in (settings.s3_bucket_public, settings.s3_bucket_private):
            client.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "af-south-1"})
        reset_storage()
        yield client
    reset_storage()


def test_s3_backend_saves_reads_and_links(s3):
    assert isinstance(get_storage(), S3Storage)
    key = storage.save("public", "units", b"RIFF....WEBP", ".webp")
    assert key.startswith("units/") and key.endswith(".webp")
    head = s3.head_object(Bucket="afe-media-public", Key=key)
    assert head["ContentType"] == "image/webp" and "immutable" in head["CacheControl"]
    assert storage.public_url(key) == f"https://media.afe.example/{key}"

    doc = storage.save("private", "authority", b"%PDF-1.4", ".pdf")
    assert storage.read("private", doc) == b"%PDF-1.4"
    assert "CacheControl" not in s3.head_object(Bucket="afe-kyc-private", Key=doc)  # private objects are never cached
    with pytest.raises(FileNotFoundError):
        storage.read("private", "authority/missing.pdf")


def test_local_backend_is_the_development_default():
    reset_storage()
    assert type(get_storage()).__name__ == "LocalStorage"


def test_production_refuses_local_storage():
    from app.config import Settings

    with pytest.raises(ValueError, match="AFE_STORAGE_BACKEND=s3"):
        Settings(debug=False, secret_key="x" * 40, storage_backend="local", allow_fake_providers=True)


def test_beta_and_production_refuse_sqlite():
    from app.config import Settings

    base = dict(debug=False, secret_key="x" * 40, storage_backend="s3", allow_fake_providers=True)
    with pytest.raises(ValueError, match="Use PostgreSQL"):
        Settings(**base, database_url="sqlite:///afe.db")
    Settings(**base, database_url="postgresql+psycopg://afe:secret@db:5432/afe")
