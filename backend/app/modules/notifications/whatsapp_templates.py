"""WhatsApp templates: one per event Afe sends on WhatsApp.

Messages Afe starts must use a template Meta has approved, and Meta files a template whose whole body is one
parameter ("{{1}}") as marketing. So each event has its own template, worded like its SMS (TEMPLATES in
service.py) with named parameters. Sign-in codes use Meta's authentication template: fixed wording, a copy-code
button and an expiry line. Replies to people who write to Afe aren't templates: inside the 24-hour customer
service window they go as plain text, which is free.

`python -m app.cli whatsapp-templates --submit` creates the templates Meta doesn't have and edits the ones whose
wording changed (Meta reviews every edit, and allows one a day on an approved template). The wording is pinned
by tests/whatsapp_templates.json, so a change to a text in TEMPLATES that goes to WhatsApp can't slip through.
"""

import re
from dataclasses import dataclass
from functools import cache

from app.config import get_settings

from .providers import DeliveryError, _request

UTILITY, MARKETING, AUTHENTICATION = "UTILITY", "MARKETING", "AUTHENTICATION"

# Not sent on WhatsApp: messages for staff, the request for a review (Meta counts asking for reviews as
# marketing), and check_reply, which is a free-form reply.
NOT_ON_WHATSAPP = {
    "check_reply", "staff_invite", "pilot_report", "model_report", "tenancy_review_invite", "whatsapp_quality",
    "whatsapp_health", "whatsapp_template", "money_alert", "money_reconcile", "money_cap",
}
# New homes for a saved search: Meta counts news about new offers as marketing.
MARKETING_TEMPLATES = {"search_alert"}
# Meta refuses a template that starts or ends with a parameter. Texts that start with one get "Afe: " in
# front; these are worded differently on WhatsApp.
WORDING = {"appeal_decided": "Your appeal was {result}. {outcome} Open Afe for details."}
OTP_TEXT = "{code} is your verification code. For your security, do not share this code."
MAX_PARAMETER = 500
# How long Meta keeps trying to deliver (its time-to-live). A code is useless once it expires; a notice that
# can't arrive within the hour goes by SMS instead; 12 hours is Meta's shortest for marketing.
UTILITY_TTL_SECONDS = 3600
MARKETING_TTL_SECONDS = 43200
# Meta can edit a template only in these states.
EDITABLE = {"APPROVED", "REJECTED", "PAUSED"}

# The example Meta's reviewers see for each parameter ("<template>.<parameter>" where one needs its own).
SAMPLES = {
    "account": "MTN MoMo ending 3456",
    "amount": "GH₵ 4,800.00",
    "area": "East Legon",
    "landlord": "Kofi Boateng",
    "lister": "Kofi Boateng",
    "listing": "2 bedroom flat, East Legon",
    "opener": "The tenant",
    "outcome": "Your listing is live again.",
    "rating": "5",
    "receipt": "AFE-R-7K3M9Q",
    "reference": "AFE-7K3M9Q",
    "rent": "GH₵ 4,800.00",
    "renter": "Yaa Asantewaa",
    "result": "accepted",
    "sender": "Yaa Asantewaa",
    "status": "in progress",
    "tenant": "Yaa Asantewaa",
    "title": "Kitchen tap is leaking",
    "unit": "12 Oak Street, East Legon",
    "until": "30 Sep 2027",
    "url": "https://afe.com.gh/homes/AFE-7K3M9Q",
    "what": "your home at 12 Oak Street",
    "when": "Mon 12 Oct, 10:00",
    "appeal_decided.result": "upheld",
    "search_alert.title": "2 bedroom flat with a garden",
}
_PARAM = re.compile(r"\{(\w+)\}")


def clean(value) -> str:
    """Meta refuses a parameter that is empty or has newlines, tabs or more than four spaces in a row."""
    text = re.sub(r"\s{4,}", "   ", re.sub(r"[\r\n\t]+", " · ", str(value))).strip()
    return text[:MAX_PARAMETER] or "-"


@dataclass(frozen=True)
class WaTemplate:
    key: str  # the event, as in TEMPLATES
    name: str  # the template's name at Meta
    category: str
    text: str  # Afe's wording, with {named} parameters
    params: tuple[str, ...]

    @property
    def body(self) -> str:
        """The wording as Meta writes it, with {{named}} parameters."""
        return _PARAM.sub(r"{{\1}}", self.text)

    @property
    def ttl_seconds(self) -> int:
        """How long Meta keeps trying to deliver one of these messages."""
        if self.category == AUTHENTICATION:
            return min(max(get_settings().otp_minutes * 60, 30), 900)
        return MARKETING_TTL_SECONDS if self.category == MARKETING else UTILITY_TTL_SECONDS

    def matches(self, at_meta: dict) -> bool:
        """Whether the template Meta has says what this one says, and keeps trying for as long."""
        if at_meta.get("message_send_ttl_seconds") not in (None, self.ttl_seconds):
            return False
        components = {c.get("type"): c for c in at_meta.get("components", [])}
        if self.category == AUTHENTICATION:
            return components.get("FOOTER", {}).get("code_expiration_minutes") == get_settings().otp_minutes
        return components.get("BODY", {}).get("text") == self.body

    def values(self, ctx: dict) -> dict[str, str]:
        missing = [p for p in self.params if p not in ctx]
        if missing:
            raise DeliveryError(f"The {self.name} template needs {', '.join(missing)}")
        return {p: clean(ctx[p]) for p in self.params}

    def render(self, ctx: dict) -> str:
        """What the person sees."""
        text = self.text.format(**self.values(ctx))
        if self.category == AUTHENTICATION:
            text += f" This code expires in {get_settings().otp_minutes} minutes."
        return text

    def message(self, ctx: dict) -> dict:
        """The "template" object of a send request."""
        values = self.values(ctx)
        if self.category == AUTHENTICATION:
            code = [{"type": "text", "text": values["code"]}]
            components = [
                {"type": "body", "parameters": code},
                {"type": "button", "sub_type": "url", "index": "0", "parameters": code},
            ]
        elif values:
            components = [{"type": "body", "parameters": [
                {"type": "text", "parameter_name": p, "text": v} for p, v in values.items()
            ]}]
        else:
            components = []
        message = {"name": self.name, "language": {"code": get_settings().whatsapp_template_language}}
        if components:
            message["components"] = components
        return message

    def submission(self) -> dict:
        """The request that registers this template with Meta (POST /{business account}/message_templates)."""
        s = get_settings()
        out = {"name": self.name, "language": s.whatsapp_template_language, "category": self.category,
               "message_send_ttl_seconds": self.ttl_seconds}
        if self.category == AUTHENTICATION:
            out["components"] = [
                {"type": "BODY", "add_security_recommendation": True},
                {"type": "FOOTER", "code_expiration_minutes": s.otp_minutes},
                {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE"}]},
            ]
            return out
        body = {"type": "BODY", "text": self.body}
        if self.params:
            out["parameter_format"] = "named"
            body["example"] = {"body_text_named_params": [
                {"param_name": p, "example": SAMPLES.get(f"{self.key}.{p}", SAMPLES.get(p, ""))} for p in self.params
            ]}
        out["components"] = [body]
        return out


@cache
def registry() -> dict[str, WaTemplate]:
    from .service import TEMPLATES  # service.py imports this module

    out = {"otp": WaTemplate("otp", "afe_sign_in_code", AUTHENTICATION, OTP_TEXT, ("code",))}
    for key, (_, text) in TEMPLATES.items():
        if key in out or key in NOT_ON_WHATSAPP:
            continue
        text = WORDING.get(key, text)
        if text.startswith("{"):
            text = f"Afe: {text}"
        category = MARKETING if key in MARKETING_TEMPLATES else UTILITY
        out[key] = WaTemplate(key, f"afe_{key}", category, text, tuple(dict.fromkeys(_PARAM.findall(text))))
    return out


def whatsapp_template(key: str) -> WaTemplate | None:
    return registry().get(key)


def _at_meta(base: str, headers: dict) -> dict[str, dict]:
    """Afe's templates at Meta in Afe's language, by name, from every page of the list."""
    s = get_settings()
    url = f"{base}/{s.whatsapp_business_account_id}/message_templates?fields=id,name,language,status,category,components,message_send_ttl_seconds&limit=100"
    found = {}
    while url:
        data = _request(url, None, headers, "WhatsApp")
        for template in data.get("data", []):
            if template.get("language") == s.whatsapp_template_language:
                found[template["name"]] = template
        url = data.get("paging", {}).get("next", "")
    return found


def _sync_one(wa: WaTemplate, at_meta: dict | None, base: str, headers: dict) -> dict:
    if at_meta is None:
        url = f"{base}/{get_settings().whatsapp_business_account_id}/message_templates"
        data = _request(url, wa.submission(), headers, "WhatsApp")
        return {"name": wa.name, "action": "created", "status": data.get("status", ""),
                "category": data.get("category", "")}
    result = {"name": wa.name, "status": at_meta.get("status", ""), "category": at_meta.get("category", "")}
    if wa.matches(at_meta):
        result["action"] = "unchanged"
    elif at_meta.get("status") in EDITABLE:
        submission = wa.submission()
        edit = {"components": submission["components"], "message_send_ttl_seconds": submission["message_send_ttl_seconds"]}
        _request(f"{base}/{at_meta['id']}", edit, headers, "WhatsApp")
        result["action"] = "edited"
    else:
        result["error"] = f"Meta can't edit it while it's {at_meta.get('status')}: run this again once it's reviewed"
    return result


def sync_all() -> list[dict]:
    """Bring Meta's templates in line with the registry: create the ones Meta doesn't have, and edit the ones
    whose wording changed. One result per template. A template Meta filed under another category comes back
    as an error: reword it so it's clearly about the person's own viewing, payment or listing."""
    s = get_settings()
    if not (s.whatsapp_business_account_id and s.whatsapp_access_token):
        raise DeliveryError("Set AFE_WHATSAPP_BUSINESS_ACCOUNT_ID and AFE_WHATSAPP_ACCESS_TOKEN to sync templates")
    base = f"https://graph.facebook.com/{s.whatsapp_graph_version}"
    headers = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    existing = _at_meta(base, headers)
    results = []
    for wa in registry().values():
        try:
            result = _sync_one(wa, existing.get(wa.name), base, headers)
        except DeliveryError as exc:
            result = {"name": wa.name, "error": str(exc)}
        if "error" not in result and result.get("category") and result["category"] != wa.category:
            result["error"] = f"Meta filed it as {result['category']}, not {wa.category}: reword it"
        results.append(result)
    return results
