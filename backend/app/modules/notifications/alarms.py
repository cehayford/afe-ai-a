"""Alarms on Afe's WhatsApp number: Meta's quality warnings, template problems, and templates that keep failing.

A number whose quality drops gets a lower messaging limit and can be restricted, which cuts off sign-in codes
and notices. Admins hear the same day: in the app, by email and by SMS, never on WhatsApp itself.
"""

import json
import logging
from datetime import timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.db import utcnow

from .models import DeliveryStatus, Notification, NotificationChannel
from .service import TTL_ERROR, notify_admins
from .whatsapp_templates import registry

log = logging.getLogger("afe.whatsapp")
# Meta's quality events that need a person: the number was flagged, or its messaging limit went down.
WARNINGS = {"FLAGGED", "DOWNGRADE"}
HEALTH_WINDOW = timedelta(hours=24)
# A template is failing at 3 or more failures and a fifth or more of its messages: few enough to notice at pilot
# volume, when the SMS fallback would otherwise hide a template Meta paused.
HEALTH_MIN_FAILED = 3
HEALTH_MAX_FAILED = 0.2
# This many messages sent since the last delivery report, and old enough to have one, means the webhook isn't
# getting message statuses.
HEALTH_MIN_REPORTABLE = 10
REPORT_WAIT = timedelta(hours=2)
# Meta's template events that need a person.
TEMPLATE_WARNINGS = {"REJECTED", "PAUSED", "DISABLED", "FLAGGED"}


def quality_update(db: Session, value: dict) -> bool:
    """Meta's phone_number_quality_update webhook. Every event is logged; a warning goes to the admins."""
    event = str(value.get("event", ""))
    limit = str(value.get("current_limit", "") or "unknown")
    log.info(json.dumps({"event": "whatsapp_quality", "quality_event": event, "limit": limit}))
    if event not in WARNINGS:
        return False
    notify_admins(db, "whatsapp_quality", event=event.lower(), number=value.get("display_phone_number", ""),
                  limit=limit)
    return True


def template_update(db: Session, field: str, value: dict) -> bool:
    """Meta's message_template_status_update and template_category_update webhooks: a rejected, paused, disabled
    or flagged template, or one Meta files under another category, goes to the admins."""
    name = str(value.get("message_template_name", ""))
    if field == "message_template_status_update":
        event = str(value.get("event", ""))
        log.info(json.dumps({"event": "whatsapp_template", "template": name, "status": event}))
        if event not in TEMPLATE_WARNINGS:
            return False
        reason = str(value.get("reason") or "NONE")
        what = event.lower() + ("" if reason == "NONE" else f" ({reason})")
    else:
        target = value.get("correct_category") or value.get("new_category")
        ours = next((wa.category for wa in registry().values() if wa.name == name), None)
        if not target or target == ours:
            return False
        what = f"moved to {str(target).lower()}"
    notify_admins(db, "whatsapp_template", name=name, event=what)
    return True


def whatsapp_health(db: Session, now=None) -> dict:
    """Daily: any template with 3 or more failures and a fifth or more of the day's messages failed, or delivery
    reports that stopped arriving, goes to the admins (Meta may have paused a template or filed it under another
    category; the webhook may have lost its subscription to message statuses). Messages that simply weren't
    delivered in time (the person's phone was off) aren't template failures."""
    now = now or utcnow()
    since = now - HEALTH_WINDOW
    failed = func.sum(case((and_(Notification.status == DeliveryStatus.FAILED, Notification.error != TTL_ERROR), 1),
                           else_=0))
    rows = db.execute(
        select(Notification.template, func.count(), failed)
        .where(Notification.channel == NotificationChannel.WHATSAPP, Notification.created_at > since)
        .group_by(Notification.template)
        .order_by(Notification.template)
    ).all()
    failing = [(t, n, int(f or 0)) for t, n, f in rows if (f or 0) >= HEALTH_MIN_FAILED and (f or 0) / n >= HEALTH_MAX_FAILED]
    latest_report = db.scalar(select(func.max(Notification.delivered_at)).where(
        Notification.channel == NotificationChannel.WHATSAPP, Notification.created_at > since - HEALTH_WINDOW
    ))
    unreported = db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.channel == NotificationChannel.WHATSAPP, Notification.provider_ref != "",
               Notification.created_at > max(latest_report or since, since), Notification.created_at < now - REPORT_WAIT)
    )
    no_reports = unreported >= HEALTH_MIN_REPORTABLE
    problems = [f"{t}: {f} of {n} failed" for t, n, f in failing]
    if no_reports:
        problems.append(f"no delivery reports for {unreported} messages sent since the last one (check the webhook "
                        "gets message statuses)")
    if problems:
        notify_admins(db, "whatsapp_health", summary="; ".join(problems))
    return {"templates": len(rows), "failing": [t for t, _, _ in failing], "no_reports": no_reports}
