"""JSON API, /api/v1. Module paths follow the Statement's module map (§8.2). Every response
uses the { data, meta, error } envelope. Clients: the SvelteKit frontend (frontend/), and
later the cross-platform app."""

from fastapi import APIRouter

from . import (
    admin,
    auth,
    check,
    documents,
    events,
    kyc,
    me,
    messages,
    payments,
    pricing,
    properties,
    rentals,
    review,
    tenancies,
    verify,
    webhooks,
)

router = APIRouter(prefix="/api/v1")
for module in (auth, me, admin, kyc, properties, messages, verify, review, payments, tenancies, pricing, rentals, check, documents, events, webhooks):
    router.include_router(module.router)
