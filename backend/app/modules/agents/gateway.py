"""The checks every agent run passes (Trust Engine: the agent gateway): masking what leaves Afe, and the agent's
level and daily token budget. Levels and budgets are compliance rules two reviewers change."""

import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.compliance.service import rule
from app.modules.detection.text import redact

from .models import AgentRun

_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_GHANAPOST = re.compile(r"\b[A-Z]{2}-\d{3,4}-\d{3,4}\b", re.IGNORECASE)
_COORDINATES = re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}")
# A run of digits with the separators people write phone numbers with: (024) 412 3456, 024.412.3456, +233-24-...
_PHONE_LIKE = re.compile(r"\+?\(?\d[\d\s.()\-]{6,}\d\)?")
_NAME_PARTS = re.compile(r"[\W_]+")


def _phone(match: re.Match) -> str:
    """Nine digits or more is a phone number; fewer is a date, an amount or a count, and stays."""
    return "[phone]" if sum(c.isdigit() for c in match.group()) >= 9 else match.group()


def _whole(term: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def mask(text: str, names: list[tuple[str, str]], places: list[str] = ()) -> str:
    """Mask free text before it leaves Afe:
    - the home's own address, label and landmark (`places`, as whole phrases), links, GhanaPost codes, coordinates;
    - phone numbers in any common format, emails and long numbers (redact);
    - each known person's name, and each part of it (split at spaces, hyphens and other punctuation), as their role
      ("[landlord]"). Whole words only, any case; parts under 3 letters stay."""
    text = text or ""
    for place in sorted({(p or "").strip() for p in places}, key=len, reverse=True):
        if len(place) >= 3:
            text = _whole(place).sub("[address]", text)
    text = _URL.sub("[link]", text)
    text = _GHANAPOST.sub("[address]", text)
    text = _COORDINATES.sub("[location]", text)
    text = _PHONE_LIKE.sub(_phone, text)
    text = redact(text)
    parts = []
    for name, tag in names:
        name = (name or "").strip()
        if len(name) >= 3:
            parts.append((name, tag))
            parts += [(part, tag) for part in _NAME_PARTS.split(name) if len(part) >= 3]
    for part, tag in sorted(parts, key=lambda p: -len(p[0])):
        text = _whole(part).sub(tag, text)
    return text


def level(db: Session, agent: str) -> str:
    return rule(db, f"agent_{agent}_level")


def tokens_today(db: Session, agent: str, now: datetime) -> int:
    """Tokens (in and out) spent by the agent's runs attempted since midnight UTC, failed attempts included."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(
        select(func.coalesce(func.sum(AgentRun.input_tokens + AgentRun.output_tokens), 0))
        .where(AgentRun.agent == agent, AgentRun.last_attempt_at >= start)
    )


def over_budget(db: Session, agent: str, now: datetime) -> bool:
    return tokens_today(db, agent, now) >= rule(db, f"agent_{agent}_daily_tokens")
