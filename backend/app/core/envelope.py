"""API response envelope from the Statement's API conventions: { data, meta, error }."""

from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    reasons: list[str] = []


class Envelope[T](BaseModel):
    data: T | None = None
    meta: dict[str, Any] = {}
    error: ErrorBody | None = None


def ok[T](data: T, **meta) -> Envelope[T]:
    return Envelope(data=data, meta=meta)
