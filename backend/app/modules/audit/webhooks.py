"""Payment webhooks as they arrived, kept as evidence whether or not Afe accepted them."""

import hashlib

from sqlalchemy.orm import Session

from .models import WebhookReceipt

MAX_BODY = 64 * 1024
# Anyone can post an unsigned delivery, so only its start is kept (with its size and fingerprint).
REJECTED_BODY = 2 * 1024
# Nothing a partner sends needs these, and they could hold credentials.
SKIP_HEADERS = {"authorization", "cookie"}


def keep(db: Session, source: str, endpoint: str, body: bytes, headers: dict[str, str], outcome: str,
         reference: str = "", error: str = "", max_body: int = MAX_BODY) -> WebhookReceipt:
    receipt = WebhookReceipt(
        source=source[:20], endpoint=endpoint, outcome=outcome, reference=reference[:40], error=error[:300],
        headers={k: v[:500] for k, v in headers.items() if k not in SKIP_HEADERS},
        body=body[:max_body].decode("utf-8", errors="replace"), size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
    )
    db.add(receipt)
    db.flush()
    return receipt
