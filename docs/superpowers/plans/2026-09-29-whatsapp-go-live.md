# WhatsApp Go-Live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Afe's WhatsApp channel ready for Meta and for real people: one approved template per event, free replies, delivery reports, WhatsApp first with SMS as the fallback, a record of every opt-in, move-in confirmation by WhatsApp, and alarms when the number's health drops.

**Architecture:** Everything stays in the existing modules. A new `notifications/whatsapp_templates.py` holds the template registry (built from the SMS texts, so wording has one source) and the submission call. WhatsApp providers get two calls, `send_template` and `send_text`, and `notifications/service.py` picks between them and routes a "text message" to WhatsApp or SMS. The webhook reads Meta's delivery reports and quality warnings as well as messages. Move-in confirmation is a new `tenancies/whatsapp.py` that ends in the existing `confirm_move_in`. Alarms live in `notifications/alarms.py` and run as one more daily job.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pytest, Meta's WhatsApp Cloud API (Graph `v21.0`), Terraform for the schedule and settings, one line of SvelteKit copy.

**Spec:** "Afe's WhatsApp and payments plan", section WhatsApp → "Changes before go-live", changes 1–7. It is in git at `feature/working-functionalities:docs/Afe_WhatsApp_Payments.html` (commit 85ebe96). Meta's own docs, checked 29 Sep 2026: status webhooks (`value.statuses[]`), authentication templates (copy-code button), named template parameters, and the `phone_number_quality_update` webhook.

## Global Constraints

- **How to run things:** run every command from `backend/` with the project venv: `.venv/Scripts/python` on Windows, `.venv/bin/python` elsewhere.
- **Tests:** `.venv/Scripts/python -m pytest` (the repo's `addopts` already adds `-q`).
- **Lint:** `.venv/Scripts/python -m ruff check app tests` passes (line length 120). Run `ruff format` only on new migration files; the rest of the code base isn't ruff-formatted.
- **Migrations:** they must match the models, so `pytest tests/test_flows.py::test_migrations_match_the_models` passes. Generate them with `AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/autogen.db` and delete `var/autogen.db` afterwards.
- **Terraform:** `terraform fmt -check` and `terraform validate` pass in `infra/terraform/staging/` (validate needs `terraform init -backend=false` once).
- **Meta:** the Graph version and template language come from settings (`whatsapp_graph_version`, `whatsapp_template_language`). Template names are `afe_` plus the event key; the sign-in code template is `afe_sign_in_code`.
- **Opt-in:** Afe starts a WhatsApp conversation only with people who opted in, or who asked for WhatsApp alerts. Free-form text goes only as a reply to someone who just wrote.
- **Sign-in codes:** never stored in clear, never retried (unchanged).
- **Copy:** user-facing text is plain English in sentence case.
- **Never commit** `.env`, databases or `var/`.

## Review Focus

1. **A caller's context lacks a parameter the template needs** (or the value is empty). The WhatsApp row fails with a reason that names the parameter, and a person who gets it WhatsApp-first still gets the SMS. It never raises into the event that sent it. Tested in Tasks 1 and 3.
2. **Meta's delivery reports arrive twice, late or out of order** ("delivered" after "read", "failed" twice). A message's status only moves forward, and a failure sends at most one fallback SMS. Tested in Task 4.
3. **A parameter with newlines, tabs, long runs of spaces, or nothing in it.** It is cleaned the way Meta requires, never sent raw. Tested in Task 1.
4. **An opted-in person gets an event with no WhatsApp template** (staff messages, the review request). It still goes by SMS. Tested in Task 3.
5. **MOVED IN or YES from a number that isn't the tenant's, for a tenancy that isn't waiting, or YES after 30 minutes.** It gets the same answer as a made-up reference (or a request to start again), and nothing about the money changes. Tested in Task 6.

---

### Task 1: One WhatsApp template per event, and a command to submit them

**Files:**
- Create: `backend/app/modules/notifications/whatsapp_templates.py`
- Modify: `backend/app/config.py:66-76` (WhatsApp settings: add `whatsapp_business_account_id`)
- Modify: `backend/app/cli.py` (docstring, parser, a handler before the database block)
- Modify: `infra/terraform/staging/variables.tf:80-84`, `infra/terraform/staging/services.tf:239`
- Test: `backend/tests/test_whatsapp.py` (new)

**Interfaces:**
- Consumes: `TEMPLATES` from `app.modules.notifications.service` (imported inside `registry()` to avoid an import cycle); `DeliveryError`, `_request` from `app.modules.notifications.providers`.
- Produces:
  - constants `UTILITY`, `MARKETING`, `AUTHENTICATION`; `NOT_ON_WHATSAPP: set[str]`; `SAMPLES: dict[str, str]`
  - `clean(value) -> str`
  - `WaTemplate(key, name, category, text, params)` with `.body -> str`, `.values(ctx) -> dict[str, str]` (raises `DeliveryError`), `.render(ctx) -> str`, `.message(ctx) -> dict` (the `template` object of a send), `.submission() -> dict`
  - `registry() -> dict[str, WaTemplate]`, `whatsapp_template(key: str) -> WaTemplate | None`, `submit_all() -> list[dict]`
  - setting `whatsapp_business_account_id: str`; CLI `whatsapp-templates [--submit]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_whatsapp.py`:

```python
"""WhatsApp go-live: a template per event, free-form replies, delivery reports, WhatsApp first with SMS as the
fallback, the opt-in record, and alarms on the number's health."""

import io
import json
import re
import urllib.error

import pytest

from app.cli import main
from app.config import get_settings
from app.modules.notifications import providers
from app.modules.notifications.service import TEMPLATES
from app.modules.notifications.whatsapp_templates import (
    AUTHENTICATION,
    MARKETING,
    NOT_ON_WHATSAPP,
    SAMPLES,
    UTILITY,
    registry,
    submit_all,
    whatsapp_template,
)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def graph(monkeypatch):
    """Meta's Graph API: records each request and answers with the next canned body (or raises it)."""
    calls, answers = [], []

    def urlopen(req, timeout=0):
        calls.append(req)
        answer = answers.pop(0) if answers else {}
        if isinstance(answer, Exception):
            raise answer
        return _Response(json.dumps(answer).encode())

    monkeypatch.setattr(providers.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(get_settings(), "whatsapp_business_account_id", "waba-1")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "token")
    return calls, answers


# --- Templates ---------------------------------------------------------------------------------------------


def test_every_message_has_a_whatsapp_template_or_a_reason_not_to():
    for key in TEMPLATES:
        assert (whatsapp_template(key) is None) == (key in NOT_ON_WHATSAPP), key


def test_templates_follow_metas_rules():
    for wa in registry().values():
        assert re.fullmatch(r"afe_[a-z0-9_]+", wa.name), wa.name
        if wa.category == AUTHENTICATION:
            continue
        assert not wa.body.startswith("{{") and not wa.body.endswith("}}"), wa.name  # Meta refuses both
        assert re.findall(r"\{\{(\w+)\}\}", wa.body) == list(wa.params), wa.name
        assert all(p in SAMPLES for p in wa.params), wa.name


def test_categories_and_names():
    assert whatsapp_template("otp").category == AUTHENTICATION
    assert whatsapp_template("otp").name == "afe_sign_in_code"
    assert whatsapp_template("search_alert").category == MARKETING
    assert whatsapp_template("viewing_confirmed").category == UTILITY
    assert whatsapp_template("viewing_confirmed").name == "afe_viewing_confirmed"


def test_a_text_that_starts_with_a_name_gets_a_prefix():
    wa = whatsapp_template("new_message")
    assert wa.body == "Afe: {{sender}} sent you a message about {{listing}} on Afe."
    assert wa.render({"sender": "Yaa", "listing": "2 bed, East Legon"}) == (
        "Afe: Yaa sent you a message about 2 bed, East Legon on Afe."
    )


def test_parameters_are_cleaned_for_meta():
    wa = whatsapp_template("maintenance_raised")
    message = wa.message({"tenant": "Yaa", "title": "Leak\nin the\tkitchen" + " " * 8 + "sink"})
    assert message["name"] == "afe_maintenance_raised" and message["language"] == {"code": "en"}
    assert message["components"] == [{"type": "body", "parameters": [
        {"type": "text", "parameter_name": "tenant", "text": "Yaa"},
        {"type": "text", "parameter_name": "title", "text": "Leak · in the · kitchen   sink"},
    ]}]
    assert wa.values({"tenant": "  ", "title": "x"})["tenant"] == "-"  # Meta refuses an empty parameter
    with pytest.raises(providers.DeliveryError, match="needs title"):
        wa.message({"tenant": "Yaa"})


def test_sign_in_codes_use_metas_authentication_template():
    wa = whatsapp_template("otp")
    code = [{"type": "text", "text": "123456"}]
    assert wa.message({"code": "123456"})["components"] == [
        {"type": "body", "parameters": code},
        {"type": "button", "sub_type": "url", "index": "0", "parameters": code},
    ]
    assert wa.submission()["components"] == [
        {"type": "BODY", "add_security_recommendation": True},
        {"type": "FOOTER", "code_expiration_minutes": get_settings().otp_minutes},
        {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE"}]},
    ]
    assert wa.render({"code": "123456"}).startswith("123456 is your verification code.")


def test_a_utility_submission_has_named_examples():
    sub = whatsapp_template("viewing_confirmed").submission()
    assert sub["category"] == UTILITY and sub["parameter_format"] == "named" and sub["language"] == "en"
    assert sub["components"] == [{
        "type": "BODY",
        "text": "Your viewing of {{listing}} is confirmed for {{when}}. Never pay before you view.",
        "example": {"body_text_named_params": [
            {"param_name": "listing", "example": SAMPLES["listing"]},
            {"param_name": "when", "example": SAMPLES["when"]},
        ]},
    }]
    plain = whatsapp_template("account_restored").submission()
    assert "parameter_format" not in plain and "example" not in plain["components"][0]
    alert = whatsapp_template("search_alert").submission()
    title = alert["components"][0]["example"]["body_text_named_params"][0]
    assert title == {"param_name": "title", "example": SAMPLES["search_alert.title"]}  # an example that fits


# --- Submitting to Meta ----------------------------------------------------------------------------------------


def test_submit_sends_every_template_and_reports_each_one(graph):
    calls, answers = graph
    answers.append(urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"error":{"message":"name exists"}}')))
    answers.extend({"id": str(i), "status": "PENDING", "category": "UTILITY"} for i in range(len(registry()) - 1))
    results = submit_all()
    assert calls[0].full_url == "https://graph.facebook.com/v21.0/waba-1/message_templates"
    assert calls[0].headers["Authorization"] == "Bearer token"
    assert json.loads(calls[0].data)["name"] == "afe_sign_in_code"
    assert len(calls) == len(results) == len(registry())
    assert results[0]["name"] == "afe_sign_in_code" and "name exists" in results[0]["error"]
    assert results[1] == {"name": list(registry().values())[1].name, "id": "0", "status": "PENDING",
                          "category": "UTILITY"}


def test_submit_needs_the_business_account(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_business_account_id", "")
    with pytest.raises(providers.DeliveryError, match="AFE_WHATSAPP_BUSINESS_ACCOUNT_ID"):
        submit_all()


def test_the_command_prints_what_to_submit(capsys):
    assert main(["whatsapp-templates"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [t["name"] for t in printed] == [wa.name for wa in registry().values()]
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py`
Expected: collection error, `ModuleNotFoundError: No module named 'app.modules.notifications.whatsapp_templates'`.

- [ ] **Step 3: Add the setting**

In `backend/app/config.py`, after `whatsapp_graph_version: str = "v21.0"` (line 76):

```python
    # The WhatsApp Business Account that owns the templates (`python -m app.cli whatsapp-templates --submit`).
    whatsapp_business_account_id: str = ""
```

- [ ] **Step 4: Write the registry**

Create `backend/app/modules/notifications/whatsapp_templates.py`:

```python
"""WhatsApp templates: one per event Afe sends on WhatsApp.

Messages Afe starts must use a template Meta has approved, and Meta files a template whose whole body is one
parameter ("{{1}}") as marketing. So each event has its own template, worded like its SMS (TEMPLATES in
service.py) with named parameters. Sign-in codes use Meta's authentication template: fixed wording, a copy-code
button and an expiry line. Replies to people who write to Afe aren't templates: inside the 24-hour customer
service window they go as plain text, which is free.

`python -m app.cli whatsapp-templates` prints what to register; `--submit` sends it all to Meta for review.
Changing a text in TEMPLATES that goes to WhatsApp means submitting its template again.
"""

import re
from dataclasses import dataclass
from functools import cache

from app.config import get_settings

from .providers import DeliveryError, _request

UTILITY, MARKETING, AUTHENTICATION = "UTILITY", "MARKETING", "AUTHENTICATION"

# Not sent on WhatsApp: messages for staff, the request for a review (Meta counts asking for reviews as
# marketing), and check_reply, which is a free-form reply.
NOT_ON_WHATSAPP = {"check_reply", "staff_invite", "pilot_report", "model_report", "tenancy_review_invite"}
# New homes for a saved search: Meta counts news about new offers as marketing.
MARKETING_TEMPLATES = {"search_alert"}
# Meta refuses a template that starts or ends with a parameter. Texts that start with one get "Afe: " in
# front; these are worded differently on WhatsApp.
WORDING = {"appeal_decided": "Your appeal was {result}. {outcome} Open Afe for details."}
OTP_TEXT = "{code} is your verification code. For your security, do not share this code."
MAX_PARAMETER = 500

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
        out = {"name": self.name, "language": s.whatsapp_template_language, "category": self.category}
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


def submit_all() -> list[dict]:
    """Send every template to Meta for review, one result each. A template Meta already has comes back as
    an error naming it; the others still go."""
    s = get_settings()
    if not (s.whatsapp_business_account_id and s.whatsapp_access_token):
        raise DeliveryError("Set AFE_WHATSAPP_BUSINESS_ACCOUNT_ID and AFE_WHATSAPP_ACCESS_TOKEN to submit templates")
    url = f"https://graph.facebook.com/{s.whatsapp_graph_version}/{s.whatsapp_business_account_id}/message_templates"
    results = []
    for wa in registry().values():
        try:
            data = _request(url, wa.submission(), {"Authorization": f"Bearer {s.whatsapp_access_token}"}, "WhatsApp")
        except DeliveryError as exc:
            results.append({"name": wa.name, "error": str(exc)})
            continue
        results.append({"name": wa.name, "id": data.get("id", ""), "status": data.get("status", ""),
                        "category": data.get("category", "")})
    return results
```

- [ ] **Step 5: Add the command**

In `backend/app/cli.py`, add to the docstring after the `pilot-report` line:

```
whatsapp-templates  print the WhatsApp templates to register with Meta (--submit sends them for review)
```

Add the parser after `sub.add_parser("pilot-report", ...)`:

```python
    templates = sub.add_parser("whatsapp-templates", help="print the WhatsApp message templates for Meta")
    templates.add_argument("--submit", action="store_true", help="submit every template to Meta for review")
```

Add the handler after the `worker` block, before `with SessionLocal.begin() as db:`:

```python
    if args.command == "whatsapp-templates":
        import json

        from app.modules.notifications.providers import DeliveryError
        from app.modules.notifications.whatsapp_templates import registry, submit_all

        if not args.submit:
            print(json.dumps([wa.submission() for wa in registry().values()], indent=2))
            return 0
        try:
            results = submit_all()
        except DeliveryError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(json.dumps(results, indent=2))
        return 1 if any("error" in r for r in results) else 0
```

- [ ] **Step 6: Terraform: the business account ID**

In `infra/terraform/staging/variables.tf`, after the `whatsapp_phone_number_id` variable:

```hcl
variable "whatsapp_business_account_id" {
  description = "WhatsApp Business Account ID from Meta (not secret); used to submit message templates."
  type        = string
  default     = ""
}
```

In `infra/terraform/staging/services.tf`, after the `AFE_WHATSAPP_PHONE_NUMBER_ID` line:

```hcl
    { name = "AFE_WHATSAPP_BUSINESS_ACCOUNT_ID", value = var.whatsapp_business_account_id },
```

- [ ] **Step 7: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py`
Expected: `10 passed`.

Run: `.venv/Scripts/python -m ruff check app tests` → `All checks passed!`; in `infra/terraform/staging/`: `terraform fmt -check` (no output) and `terraform validate` → `Success!`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/notifications/whatsapp_templates.py backend/app/config.py backend/app/cli.py backend/tests/test_whatsapp.py infra/terraform/staging/variables.tf infra/terraform/staging/services.tf
git commit -m "feat(whatsapp): one template per event, and a command to submit them to Meta"
```

---

### Task 2: Send each event through its template; replies as free text

**Files:**
- Modify: `backend/app/modules/notifications/providers.py` (docstring, a `WhatsAppProvider` protocol, `FakeWhatsApp`, `WhatsAppCloud`, `provider_for`'s annotation; drop `import re`)
- Modify: `backend/app/modules/notifications/service.py` (`FREE_FORM`, `_whatsapp_data`, `_send_whatsapp`, `_deliver`, `send_direct`, `notify`, `notify_on`)
- Modify: `backend/app/config.py:70-74` (drop `whatsapp_template`, reword the comment)
- Modify: `backend/tests/test_launch_readiness.py:20,53-77` (the two WhatsApp provider tests)
- Modify: `backend/README.md` (Launch readiness → Messages), `infra/terraform/staging/README.md` (the Meta template step)
- Test: `backend/tests/test_whatsapp.py`, `backend/tests/test_launch_readiness.py`

**Interfaces:**
- Consumes: `WaTemplate.message(ctx)`, `WaTemplate.render(ctx)`, `whatsapp_template(key)` from Task 1.
- Produces:
  - providers: `send_template(recipient: str, template: WaTemplate, ctx: dict) -> str` and `send_text(recipient: str, body: str) -> str` on `WhatsAppCloud` and `FakeWhatsApp`
  - service: `FREE_FORM = {"check_reply"}`; `_whatsapp_data(channel, template, ctx) -> dict`; `_deliver(db, note, body, ctx: dict | None = None)`. WhatsApp rows store their parameters in `Notification.data` (never for `SENSITIVE`), and a retry sends from them.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_launch_readiness.py`, add to the imports:

```python
from app.modules.notifications.whatsapp_templates import whatsapp_template
```

Replace `test_whatsapp_sends_through_the_approved_template` and `test_whatsapp_errors_become_delivery_errors` (lines 53–77) with:

```python
def test_whatsapp_sends_each_event_through_its_template(monkeypatch, http):
    calls, answer = http
    monkeypatch.setattr(get_settings(), "whatsapp_phone_number_id", "1234567890")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "token")
    answer["body"] = {"messages": [{"id": "wamid.ABC"}]}
    wa = whatsapp_template("viewing_confirmed")
    ctx = {"listing": "2 bed\nEast Legon", "when": "Mon 10:00"}
    assert WhatsAppCloud().send_template("+233244123456", wa, ctx) == "wamid.ABC"
    req = calls[0]
    assert req.full_url == "https://graph.facebook.com/v21.0/1234567890/messages"
    assert req.headers["Authorization"] == "Bearer token"
    payload = json.loads(req.data)
    assert payload["to"] == "233244123456" and payload["type"] == "template"
    assert payload["template"] == wa.message(ctx)
    assert payload["template"]["components"][0]["parameters"][0]["text"] == "2 bed · East Legon"


def test_whatsapp_replies_go_as_free_text(monkeypatch, http):
    calls, answer = http
    monkeypatch.setattr(get_settings(), "whatsapp_phone_number_id", "1234567890")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "token")
    answer["body"] = {"messages": [{"id": "wamid.R"}]}
    assert WhatsAppCloud().send_text("+233244123456", "Line one\nLine two") == "wamid.R"
    payload = json.loads(calls[0].data)
    assert payload["type"] == "text" and payload["text"] == {"preview_url": False, "body": "Line one\nLine two"}


def test_whatsapp_errors_become_delivery_errors(monkeypatch, http):
    _, answer = http
    monkeypatch.setattr(get_settings(), "whatsapp_phone_number_id", "1")
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "t")
    answer["error"] = urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"error":{"code":131047}}'))
    with pytest.raises(DeliveryError, match="400"):
        WhatsAppCloud().send_text("+233244123456", "hi")
    with pytest.raises(DeliveryError, match="not configured"):
        monkeypatch.setattr(get_settings(), "whatsapp_access_token", "")
        WhatsAppCloud().send_template("+233244123456", whatsapp_template("party_verified"), {})
```

Append to `backend/tests/test_whatsapp.py` (add these imports at the top of the file, keeping them sorted):

```python
from datetime import timedelta

from app.db import utcnow
from app.modules.notifications import service
from app.modules.notifications.models import Notification
from app.modules.notifications.providers import fake_outbox
from app.modules.notifications.service import notify, notify_on, retry_failed, send_direct
```

```python
# --- Sending ------------------------------------------------------------------------------------------------


class FlakyWhatsApp(providers.FakeWhatsApp):
    fails = 1

    def send_template(self, recipient, template, ctx):
        if FlakyWhatsApp.fails:
            FlakyWhatsApp.fails -= 1
            raise providers.DeliveryError("WhatsApp is unreachable: timed out")
        return super().send_template(recipient, template, ctx)


def test_notices_go_through_their_template_and_keep_its_parameters(db, landlord):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "review_received", rating=5)
    wa = next(n for n in notes if n.channel == "whatsapp")
    assert wa.status == "sent" and wa.data == {"rating": 5}
    assert fake_outbox.last("whatsapp", landlord.phone).body == "A tenant left you a 5-star review on Afe."


def test_replies_go_as_free_text_and_keep_no_parameters(db):
    note = send_direct(db, "whatsapp", "+233551112222", "check_reply", text="Line one\nLine two")
    assert note.status == "sent" and note.data == {}
    assert fake_outbox.last("whatsapp", "+233551112222").body == "Line one\nLine two"


def test_sign_in_codes_on_whatsapp_keep_no_parameters(db):
    note = send_direct(db, "whatsapp", "+233551112222", "otp", code="123456")
    assert note.status == "sent" and note.data == {} and "123456" not in note.body
    assert "123456 is your verification code" in fake_outbox.last("whatsapp", "+233551112222").body


def test_an_event_without_a_whatsapp_template_is_not_sent_on_whatsapp(db):
    note = send_direct(db, "whatsapp", "+233551112222", "staff_invite", name="Esi", url="https://afe.example")
    assert note.status == "failed" and "No WhatsApp template for staff_invite" in note.error


def test_a_row_without_its_parameters_fails_its_retry_and_says_why(db, landlord):
    # A WhatsApp row written before rows kept their parameters.
    note = Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, template="review_received",
                        body="A tenant left you a 5-star review on Afe.", status="failed", attempts=1,
                        created_at=utcnow() - timedelta(minutes=6))
    db.add(note)
    db.flush()
    retry_failed(db)
    assert note.status == "failed" and "needs rating" in note.error


def test_a_failed_whatsapp_notice_is_retried_from_its_parameters(db, monkeypatch, landlord):
    monkeypatch.setattr(service, "provider_for", lambda channel: FlakyWhatsApp())
    FlakyWhatsApp.fails = 1
    [note] = notify_on(db, landlord, "tenancy_refunded", {"whatsapp"}, amount="GH₵ 10.00")
    assert note.status == "failed" and note.attempts == 1
    note.created_at -= timedelta(minutes=6)
    assert retry_failed(db)["sent"] == 1 and note.status == "sent"
    assert fake_outbox.last("whatsapp", landlord.phone).body == "Afe refunded GH₵ 10.00 to you."
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py tests/test_launch_readiness.py`
Expected: FAIL. `send_template`/`send_text` don't exist (`AttributeError`), `wa.data == {}` where `{"rating": 5}` is expected, and `staff_invite` is `sent` where `failed` is expected.

- [ ] **Step 3: Providers**

In `backend/app/modules/notifications/providers.py`:

Add a paragraph to the module docstring, after "…not code.":

```
WhatsApp providers have two calls instead of `send`: `send_template` for messages Afe starts (each event has its
own approved template, see whatsapp_templates.py) and `send_text` for a reply to someone who just wrote.
```

Remove `import re`. After the `Provider` protocol add:

```python
class WhatsAppProvider(Protocol):
    name: str

    def send_template(self, recipient: str, template, ctx: dict) -> str:
        """Send an approved template with its parameters filled from ctx; return Meta's message id."""

    def send_text(self, recipient: str, body: str) -> str:
        """Send a free-form reply (only inside the 24-hour customer service window)."""
```

Replace `FakeWhatsApp`:

```python
class FakeWhatsApp(_Fake):
    """Records what the person would see: the template's wording with its parameters filled in."""

    channel = "whatsapp"

    def send_template(self, recipient: str, template, ctx: dict) -> str:
        return self.send(recipient, template.render(ctx))

    def send_text(self, recipient: str, body: str) -> str:
        return self.send(recipient, body)
```

Replace `WhatsAppCloud`:

```python
class WhatsAppCloud:
    """Meta's WhatsApp Business Cloud API. Messages Afe starts go through the approved template for their
    event; replies inside the 24-hour customer service window go as plain text, which is free."""

    name = "whatsapp-cloud"
    channel = "whatsapp"

    def send_template(self, recipient: str, template, ctx: dict) -> str:
        return self._post(recipient, {"type": "template", "template": template.message(ctx)})

    def send_text(self, recipient: str, body: str) -> str:
        return self._post(recipient, {"type": "text", "text": {"preview_url": False, "body": body[:4096]}})

    def _post(self, recipient: str, message: dict) -> str:
        s = get_settings()
        if not (s.whatsapp_phone_number_id and s.whatsapp_access_token):
            raise DeliveryError("WhatsApp is not configured")
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": _digits(recipient), **message}
        data = _request(
            f"https://graph.facebook.com/{s.whatsapp_graph_version}/{s.whatsapp_phone_number_id}/messages",
            payload,
            {"Authorization": f"Bearer {s.whatsapp_access_token}"},
            "WhatsApp",
        )
        try:
            return data["messages"][0]["id"]
        except (KeyError, IndexError) as exc:
            raise DeliveryError(f"WhatsApp gave no message id: {str(data)[:200]}") from exc
```

Change `provider_for`'s return annotation to `Provider | WhatsAppProvider | None`.

- [ ] **Step 4: Service**

In `backend/app/modules/notifications/service.py`, add the import:

```python
from .whatsapp_templates import whatsapp_template
```

After `SENSITIVE = {"otp"}`:

```python
# Replies to someone who just wrote to Afe on WhatsApp: plain text, free inside the 24-hour window.
FREE_FORM = {"check_reply"}
```

After `_render`:

```python
def _whatsapp_data(channel: str, template: str, ctx: dict) -> dict:
    """A WhatsApp row keeps its template's parameters, so a retry can send the template again. Never a code."""
    if channel != NotificationChannel.WHATSAPP or template in SENSITIVE or template in FREE_FORM:
        return {}
    return ctx


def _send_whatsapp(provider, note: Notification, body: str, ctx: dict | None) -> str:
    if note.template in FREE_FORM:
        return provider.send_text(note.recipient, body)
    template = whatsapp_template(note.template)
    if template is None:
        raise DeliveryError(f"No WhatsApp template for {note.template}")
    return provider.send_template(note.recipient, template, note.data if ctx is None else ctx)
```

Replace `_deliver`:

```python
def _deliver(db: Session, note: Notification, body: str, ctx: dict | None = None) -> Notification:
    """Send one row. ctx fills a WhatsApp template; without it (a retry) the row's stored parameters do."""
    provider = provider_for(note.channel)
    if provider is None:
        note.status, note.error = DeliveryStatus.FAILED, "No provider configured"
        return note
    note.attempts = (note.attempts or 0) + 1
    try:
        if note.channel == NotificationChannel.WHATSAPP:
            note.provider_ref = _send_whatsapp(provider, note, body, ctx)
        else:
            note.provider_ref = provider.send(note.recipient, body, note.title)
        note.provider, note.status, note.sent_at = provider.name, DeliveryStatus.SENT, utcnow()
    except DeliveryError as exc:
        note.provider, note.status, note.error = provider.name, DeliveryStatus.FAILED, str(exc)[:300]
    return note
```

In `send_direct`, give the row its data and pass ctx:

```python
    note = Notification(
        user_id=user_id, channel=channel, recipient=recipient, template=template, title=title, body=stored,
        data=_whatsapp_data(channel, template, ctx),
    )
    db.add(note)
    _deliver(db, note, body, ctx)
```

In `notify`, add `data=ctx,` to the WhatsApp row, and change `_deliver(db, note, body)` to `_deliver(db, note, body, ctx)`. In `notify_on`, add `data=_whatsapp_data(channel, template, ctx)` to the rows built in the channel loop, and change its `_deliver(db, note, body)` to `_deliver(db, note, body, ctx)`.

- [ ] **Step 5: Settings**

In `backend/app/config.py`, replace lines 70–74:

```python
    # Sending on WhatsApp (WhatsAppCloud): the business phone number and a system-user token. Each event goes
    # through its own approved template (notifications/whatsapp_templates.py).
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
```

(`whatsapp_template_language` and `whatsapp_graph_version` stay.)

- [ ] **Step 6: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py tests/test_launch_readiness.py tests/test_auth.py tests/test_billing.py tests/test_renter_growth.py tests/test_hardening.py`
Expected: all pass.

- [ ] **Step 7: Docs**

In `backend/README.md`, Launch readiness → Messages, replace "real senders for WhatsApp (`WhatsAppCloud`, Meta's Cloud API, through one approved template "Afe update: {{1}}"), SMS (`HubtelSms`) and email (`SesEmail`)." with:

```
real senders for WhatsApp (`WhatsAppCloud`, Meta's Cloud API), SMS (`HubtelSms`) and email (`SesEmail`). Each
  event Afe sends on WhatsApp has its own template (`notifications/whatsapp_templates.py`; `python -m app.cli
  whatsapp-templates --submit` sends them to Meta for review), sign-in codes use Meta's authentication template,
  and replies to people who write to Afe go as free text.
```

In `infra/terraform/staging/README.md`, replace the bullet "In Meta's WhatsApp Manager, get the utility template `afe_update` approved, with the body "Afe update: {{1}}". Every WhatsApp message goes through it." with:

```
- Set `whatsapp_business_account_id`, then submit the WhatsApp templates once: `python -m app.cli
  whatsapp-templates --submit` (a jobs task, or any machine with the access token). Each event Afe sends on
  WhatsApp has its own template; the command prints each one's status, and Meta reviews them within a day or two.
  Fix and resubmit any Meta rejects or files under a different category.
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/notifications/providers.py backend/app/modules/notifications/service.py backend/app/config.py backend/tests/test_whatsapp.py backend/tests/test_launch_readiness.py backend/README.md infra/terraform/staging/README.md
git commit -m "feat(whatsapp): send each event through its template, replies as free text"
```

---

### Task 3: WhatsApp first for people who opted in, SMS as the fallback

**Files:**
- Modify: `backend/app/modules/notifications/models.py` (`Notification.fallback_of_id`)
- Create: `backend/migrations/versions/20260929_<rev>_whatsapp_sms_fallback.py` (autogenerated)
- Modify: `backend/app/modules/notifications/service.py` (docstring, `BOTH_CHANNELS`, `_text_channels`, `_send`, `fallback_to_sms`, `notify`, `notify_on`)
- Modify: `frontend/src/routes/account/+page.svelte:33` (the opt-in label)
- Test: `backend/tests/test_whatsapp.py`

**Interfaces:**
- Consumes: `whatsapp_template(key)`, `MARKETING` (Task 1); `_deliver(db, note, body, ctx)`, `_whatsapp_data` (Task 2).
- Produces:
  - `BOTH_CHANNELS: set[str]`; `fallback_to_sms(db, note) -> Notification | None` (Task 4 calls it)
  - `Notification.fallback_of_id: int | None`
  - `notify_on(..., channels)`: `"sms"` in `channels` means "a text message", routed to WhatsApp or SMS; `notify` is `notify_on` with `{"in_app", "sms", "email"}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_whatsapp.py` (add `from app.modules.notifications.service import MAX_ATTEMPTS` to the service import):

```python
# --- WhatsApp first -----------------------------------------------------------------------------------------


class DeadWhatsApp(providers.FakeWhatsApp):
    def send_template(self, recipient, template, ctx):
        raise providers.DeliveryError("WhatsApp refused the message (400): 131026")


@pytest.fixture
def dead_whatsapp(monkeypatch):
    real = service.provider_for
    monkeypatch.setattr(service, "provider_for", lambda channel: DeadWhatsApp() if channel == "whatsapp" else real(channel))


def test_people_who_opted_in_get_whatsapp_instead_of_sms(db, landlord):
    assert [n.channel for n in notify(db, landlord, "review_received", rating=5)] == ["in_app", "sms"]
    landlord.whatsapp_opt_in = True
    assert [n.channel for n in notify(db, landlord, "review_received", rating=5)] == ["in_app", "whatsapp"]


def test_money_events_go_by_both(db, landlord):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "tenancy_refunded", amount="GH₵ 10.00")
    assert [n.channel for n in notes] == ["in_app", "sms", "whatsapp"]


def test_events_with_no_whatsapp_template_still_go_by_sms(db, landlord):
    landlord.whatsapp_opt_in = True
    assert [n.channel for n in notify(db, landlord, "tenancy_review_invite", landlord="Ama")] == ["in_app", "sms"]


def test_a_text_message_asked_for_by_sms_goes_on_whatsapp_to_people_who_opted_in(db, landlord):
    landlord.whatsapp_opt_in = True
    notes = notify_on(db, landlord, "rent_due", {"in_app", "sms"}, tenant="Yaa", amount="GH₵ 10.00", when="1 Oct")
    assert [n.channel for n in notes] == ["in_app", "whatsapp"]
    # An alert follows the channel the person chose for it.
    alert = dict(title="2 bed", rent="GH₵ 10.00", area="East Legon", url="https://afe.example/homes/AFE-1")
    assert [n.channel for n in notify_on(db, landlord, "search_alert", {"sms"}, **alert)] == ["sms"]


def test_when_whatsapp_fails_the_notice_goes_by_sms_once(db, landlord, dead_whatsapp):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "review_received", rating=5)
    assert [n.channel for n in notes] == ["in_app", "whatsapp", "sms"]
    wa, sms = notes[1], notes[2]
    assert wa.status == "failed" and wa.attempts == MAX_ATTEMPTS  # WhatsApp isn't tried again
    assert sms.fallback_of_id == wa.id and sms.status == "sent"
    assert fake_outbox.last("sms", landlord.phone).body == "A tenant left you a 5-star review on Afe."
    wa.created_at -= timedelta(hours=1)
    assert retry_failed(db) == {"sent": 0, "failed": 0, "waiting": 0}


def test_no_fallback_for_money_events_or_alerts(db, landlord, dead_whatsapp):
    landlord.whatsapp_opt_in = True
    notes = notify(db, landlord, "tenancy_refunded", amount="GH₵ 10.00")
    assert [n.channel for n in notes] == ["in_app", "sms", "whatsapp"]  # the SMS it gets anyway, no second one
    alert = dict(title="2 bed", rent="GH₵ 10.00", area="East Legon", url="https://afe.example/homes/AFE-1")
    assert [n.channel for n in notify_on(db, landlord, "search_alert", {"whatsapp"}, **alert)] == ["whatsapp"]
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py`
Expected: FAIL. Opted-in people get `["in_app", "sms", "whatsapp"]`, `fallback_of_id` doesn't exist, and `notify_on(..., {"in_app", "sms"})` sends SMS.

- [ ] **Step 3: The column and its migration**

In `backend/app/modules/notifications/models.py`, after `attempts`:

```python
    # For an SMS sent because WhatsApp couldn't deliver: the WhatsApp message it stands in for.
    fallback_of_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"))
```

Generate the migration:

```bash
AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/autogen.db .venv/Scripts/python -m alembic upgrade head
AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/autogen.db .venv/Scripts/python -m alembic revision --autogenerate -m "whatsapp sms fallback"
rm var/autogen.db
.venv/Scripts/python -m ruff format migrations/versions/*_whatsapp_sms_fallback.py
```

Expected: one new file whose `upgrade()` adds `fallback_of_id` and its foreign key inside `batch_alter_table("notifications")`, and whose `downgrade()` drops them. Delete the "commands auto generated" comments.

- [ ] **Step 4: Routing and fallback in the service**

In `backend/app/modules/notifications/service.py`, replace the module docstring's first paragraph:

```python
"""Send notifications. Every event creates an in-app notification and, where the person can receive them, an
email and a text message. The text goes on WhatsApp to people who opted in (by SMS if WhatsApp can't deliver
it), and by SMS to everyone else. Events about money go by both.
```

(keep the second paragraph about Celery). Change the import to:

```python
from .whatsapp_templates import MARKETING, whatsapp_template
```

After `FREE_FORM`:

```python
# Events about money go by SMS as well as WhatsApp: a missed message about someone's money costs more than a
# second one.
BOTH_CHANNELS = {
    "tenancy_offered", "tenancy_funded_tenant", "tenancy_funded_landlord", "tenancy_released", "tenancy_refunded",
    "dispute_opened", "payee_changed", "fee_paid", "featured_paid",
}
```

After `send_direct`, replace `notify` and `notify_on` with:

```python
def _text_channels(user, template: str) -> set[str]:
    """Where a text message goes: on WhatsApp to people who opted in, when the event has a template (not
    alerts, which follow the channel the person chose for them); by SMS otherwise. Money events go by both."""
    wa = whatsapp_template(template)
    if not (user.whatsapp_opt_in and wa is not None and wa.category != MARKETING):
        return {"sms"}
    return {"sms", "whatsapp"} if template in BOTH_CHANNELS else {"whatsapp"}


def fallback_to_sms(db: Session, note: Notification) -> Notification | None:
    """WhatsApp couldn't deliver a notice: send it by SMS, once, and stop trying WhatsApp. Not for sign-in
    codes (request_code sends those by SMS itself), replies, alerts (not worth a paid SMS), messages with no
    account, or money events (they went by SMS already)."""
    wa = whatsapp_template(note.template)
    if (note.user_id is None or wa is None or wa.category == MARKETING or note.template in SENSITIVE
            or note.template in BOTH_CHANNELS):
        return None
    db.flush()  # the WhatsApp row needs its id
    note.attempts = MAX_ATTEMPTS
    sms = Notification(user_id=note.user_id, channel=NotificationChannel.SMS, recipient=note.recipient,
                       template=note.template, title=note.title, body=note.body, link=note.link,
                       fallback_of_id=note.id)
    db.add(sms)
    _deliver(db, sms, sms.body)
    db.flush()
    return sms


def _send(db: Session, notes: list[Notification], body: str, ctx: dict) -> list[Notification]:
    sent = []
    for note in notes:
        db.add(note)
        sent.append(note)
        if note.channel == NotificationChannel.IN_APP:
            continue
        _deliver(db, note, body, ctx)
        if note.channel == NotificationChannel.WHATSAPP and note.status == DeliveryStatus.FAILED:
            fallback = fallback_to_sms(db, note)
            if fallback is not None:
                sent.append(fallback)
    db.flush()
    return sent


def notify(db: Session, user, template: str, link: str = "", **ctx) -> list[Notification]:
    """Tell a person about an event on every channel they can receive: in the app, by email, and a text
    message (on WhatsApp or by SMS, see _text_channels)."""
    return notify_on(db, user, template, {"in_app", "sms", "email"}, link, **ctx)


def notify_on(db: Session, user, template: str, channels: set[str], link: str = "", **ctx) -> list[Notification]:
    """Like notify, but only on the channels given. "sms" asks for a text message, which goes on WhatsApp to
    people who opted in; "whatsapp" on its own is for someone who asked for it (an alert)."""
    title, body = _render(template, ctx)
    if "sms" in channels:
        channels = (set(channels) - {"sms"}) | _text_channels(user, template)
    notes = []
    if "in_app" in channels:
        notes.append(Notification(user_id=user.id, channel=NotificationChannel.IN_APP, template=template, title=title,
                                  body=body, link=link, data=ctx, status=DeliveryStatus.SENT, sent_at=utcnow()))
    for channel, address in (("sms", user.phone), ("whatsapp", user.phone), ("email", user.email)):
        if channel in channels and address:
            notes.append(Notification(user_id=user.id, channel=channel, recipient=address, template=template,
                                      title=title, body=body, link=link, data=_whatsapp_data(channel, template, ctx)))
    return _send(db, notes, body, ctx)
```

- [ ] **Step 5: The opt-in label says what now happens**

In `frontend/src/routes/account/+page.svelte:33`, replace `Send my Afe alerts on WhatsApp as well as SMS` with:

```svelte
			<span>Send my Afe updates on WhatsApp instead of SMS (payment updates come by SMS too)</span>
```

- [ ] **Step 6: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass, including `tests/test_flows.py::test_migrations_match_the_models`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/notifications/models.py backend/migrations/versions/*_whatsapp_sms_fallback.py backend/app/modules/notifications/service.py backend/tests/test_whatsapp.py frontend/src/routes/account/+page.svelte
git commit -m "feat(whatsapp): WhatsApp first for people who opted in, SMS when it fails, both for money"
```

---

### Task 4: Delivery reports from Meta

**Files:**
- Modify: `backend/app/modules/notifications/models.py` (`DeliveryStatus.DELIVERED`, `DeliveryStatus.READ`, `Notification.delivered_at`)
- Create: `backend/migrations/versions/20260929_<rev>_notification_delivered_at.py` (autogenerated)
- Modify: `backend/app/modules/notifications/service.py` (`apply_whatsapp_status`)
- Modify: `backend/app/api/v1/webhooks.py:132-146` (read `value.statuses`)
- Test: `backend/tests/test_whatsapp.py`

**Interfaces:**
- Consumes: `fallback_to_sms(db, note)`, `MAX_ATTEMPTS` (Task 3).
- Produces: `apply_whatsapp_status(db, status: dict) -> Notification | None`; statuses `delivered` and `read`; `Notification.delivered_at`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_whatsapp.py` (imports to add: `UTC, datetime` from `datetime`, `from sqlalchemy import func, select`, and `apply_whatsapp_status` from the service):

```python
# --- Delivery reports ----------------------------------------------------------------------------------------


def _report(ref, status, **extra) -> dict:
    report = {"id": ref, "status": status, "timestamp": "1790000000", "recipient_id": "233244123456", **extra}
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": {"statuses": [report]}}]}]}


def _whatsapp_notice(db, landlord) -> Notification:
    landlord.whatsapp_opt_in = True
    return next(n for n in notify(db, landlord, "review_received", rating=5) if n.channel == "whatsapp")


def test_delivery_reports_only_move_a_message_forward(client, db, landlord):
    wa = _whatsapp_notice(db, landlord)
    db.commit()
    assert client.post("/api/v1/webhooks/whatsapp", json=_report(wa.provider_ref, "read")).status_code == 200
    assert wa.status == "read" and wa.delivered_at == datetime.fromtimestamp(1790000000, UTC)
    client.post("/api/v1/webhooks/whatsapp", json=_report(wa.provider_ref, "delivered"))  # late
    assert wa.status == "read"
    client.post("/api/v1/webhooks/whatsapp", json=_report(wa.provider_ref, "failed"))  # after it was read
    assert wa.status == "read"
    assert client.post("/api/v1/webhooks/whatsapp", json=_report("wamid.not-ours", "delivered")).status_code == 200


def test_a_failure_report_sends_the_notice_by_sms_once(client, db, landlord):
    wa = _whatsapp_notice(db, landlord)
    db.commit()
    failed = _report(wa.provider_ref, "failed", errors=[{"code": 131026, "title": "Message undeliverable"}])
    client.post("/api/v1/webhooks/whatsapp", json=failed)
    client.post("/api/v1/webhooks/whatsapp", json=failed)  # Meta sends it again
    assert wa.status == "failed" and wa.error == "131026: Message undeliverable" and wa.attempts == MAX_ATTEMPTS
    fallbacks = select(func.count()).select_from(Notification).where(Notification.fallback_of_id == wa.id)
    assert db.scalar(fallbacks) == 1
    assert fake_outbox.last("sms", landlord.phone).body == "A tenant left you a 5-star review on Afe."


def test_a_report_with_no_timestamp_still_counts(db, landlord):
    wa = _whatsapp_notice(db, landlord)
    assert apply_whatsapp_status(db, {"id": wa.provider_ref, "status": "delivered"}) is wa
    assert wa.status == "delivered" and wa.delivered_at is not None
    assert apply_whatsapp_status(db, {"status": "delivered"}) is None
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py -k "report"`
Expected: FAIL: `ImportError: cannot import name 'apply_whatsapp_status'`.

- [ ] **Step 3: Model and migration**

In `backend/app/modules/notifications/models.py`:

```python
class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"  # WhatsApp only: Meta's delivery report
    READ = "read"  # WhatsApp only
    FAILED = "failed"
```

After `sent_at`:

```python
    delivered_at: Mapped[datetime | None]
```

Generate the migration the same way as Task 3, with `-m "notification delivered at"`, then `rm var/autogen.db` and `ruff format` the new file only. Expected: `upgrade()` adds `delivered_at` to `notifications`.

- [ ] **Step 4: Apply a report**

In `backend/app/modules/notifications/service.py`, change `from datetime import timedelta` to `from datetime import UTC, datetime, timedelta`, and add at the end of the file:

```python
_PROGRESS = {DeliveryStatus.QUEUED: 0, DeliveryStatus.SENT: 1, DeliveryStatus.DELIVERED: 2, DeliveryStatus.READ: 3}


def _reported_at(timestamp) -> datetime:
    try:
        return datetime.fromtimestamp(int(timestamp), UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return utcnow()


def apply_whatsapp_status(db: Session, status: dict) -> Notification | None:
    """Meta's delivery report (sent, delivered, read or failed) for a message Afe sent. Reports can come late,
    twice or out of order, so a message only moves forward. A message that fails after Meta accepted it isn't
    sent on WhatsApp again: the notice goes by SMS instead."""
    ref = str(status.get("id") or "")
    note = ref and db.scalar(select(Notification).where(
        Notification.channel == NotificationChannel.WHATSAPP, Notification.provider_ref == ref
    ))
    if not note:
        return None
    state = status.get("status")
    if state == "failed" and note.status in (DeliveryStatus.QUEUED, DeliveryStatus.SENT):
        error = (status.get("errors") or [{}])[0]
        note.status, note.attempts = DeliveryStatus.FAILED, MAX_ATTEMPTS
        note.error = f"{error.get('code', '')}: {error.get('title', '')}"[:300]
        fallback_to_sms(db, note)
    elif state in (DeliveryStatus.DELIVERED, DeliveryStatus.READ) and (
        _PROGRESS.get(note.status, len(_PROGRESS)) < _PROGRESS[state]
    ):
        note.status = state
        note.delivered_at = note.delivered_at or _reported_at(status.get("timestamp"))
    db.flush()
    return note
```

- [ ] **Step 5: The webhook reads reports**

In `backend/app/api/v1/webhooks.py`, import `apply_whatsapp_status` beside `send_direct`, and in `inbound` replace the inner loop header:

```python
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []):
                apply_whatsapp_status(db, status)
            for message in value.get("messages", []):
```

(the body of the `messages` loop is unchanged).

- [ ] **Step 6: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py tests/test_flows.py tests/test_billing.py`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/notifications/models.py backend/migrations/versions/*_notification_delivered_at.py backend/app/modules/notifications/service.py backend/app/api/v1/webhooks.py backend/tests/test_whatsapp.py
git commit -m "feat(whatsapp): read Meta's delivery reports; a late failure goes by SMS"
```

---

### Task 5: Record when and where each person opted in

**Files:**
- Modify: `backend/app/modules/accounts/models.py:51` (three columns on `User`)
- Create: `backend/migrations/versions/20260929_<rev>_whatsapp_opt_in_record.py` (autogenerated)
- Modify: `backend/app/modules/accounts/service.py` (`set_whatsapp_opt_in`)
- Modify: `backend/app/api/v1/me.py:64-65`, `backend/app/modules/alerts/service.py:99-100`, `backend/app/api/v1/webhooks.py:82-88` (the three callers)
- Modify: `backend/app/modules/accounts/privacy.py:58` (the export)
- Test: `backend/tests/test_whatsapp.py`

**Interfaces:**
- Consumes: `record(db, actor, action, subject, **data)` from `app.modules.audit.log`.
- Produces: `set_whatsapp_opt_in(db, user, on: bool, source: str) -> None` with sources `settings`, `alert`, `whatsapp_stop`; `User.whatsapp_opt_in_at`, `User.whatsapp_opt_in_source`, `User.whatsapp_opt_out_at`; audit actions `account.whatsapp_opt_in` and `account.whatsapp_opt_out`; export keys `whatsapp_opted_in_at`, `whatsapp_opt_in_source`, `whatsapp_opted_out_at`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_whatsapp.py` (imports to add: `from app.modules.accounts.models import Role`, `from app.modules.alerts import service as alerts`, `from app.modules.audit.models import AuditEvent`, `from tests.conftest import api_login, make_user`):

```python
# --- The opt-in record -----------------------------------------------------------------------------------------


def _inbound(text, sender="233240000009") -> dict:
    return {"entry": [{"changes": [{"value": {"messages": [{"from": sender, "type": "text", "text": {"body": text}}]}}]}]}


def test_opting_in_and_out_is_recorded(client, db):
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    db.commit()
    h = api_login(client, "yaa")
    assert client.patch("/api/v1/me", headers=h, json={"whatsapp_opt_in": True}).status_code == 200
    assert renter.whatsapp_opt_in and renter.whatsapp_opt_in_source == "settings" and renter.whatsapp_opt_in_at
    client.patch("/api/v1/me", headers=h, json={"whatsapp_opt_in": True})  # no change, nothing new recorded
    client.post("/api/v1/webhooks/whatsapp", json=_inbound("STOP"))
    assert not renter.whatsapp_opt_in and renter.whatsapp_opt_out_at
    events = db.scalars(select(AuditEvent).where(AuditEvent.action.like("account.whatsapp%")).order_by(AuditEvent.id))
    assert [(e.action, e.data["source"]) for e in events] == [
        ("account.whatsapp_opt_in", "settings"), ("account.whatsapp_opt_out", "whatsapp_stop"),
    ]
    account = client.get("/api/v1/me/export", headers=h).json()["account"]
    assert account["whatsapp_updates"] is False and account["whatsapp_opt_in_source"] == "settings"
    assert account["whatsapp_opted_in_at"] and account["whatsapp_opted_out_at"]


def test_asking_for_whatsapp_alerts_records_the_opt_in(db, area):
    renter = make_user(db, "yaa", Role.RENTER, phone="0240000009")
    alerts.save_search(db, renter, alerts.parse_query(db, "2 bed east legon"), "whatsapp")
    assert renter.whatsapp_opt_in and renter.whatsapp_opt_in_source == "alert"
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py -k "opt"`
Expected: FAIL: `AttributeError: 'User' object has no attribute 'whatsapp_opt_in_source'`.

- [ ] **Step 3: Columns and migration**

In `backend/app/modules/accounts/models.py`, after `whatsapp_opt_in`:

```python
    # When and how the person turned WhatsApp messages on (settings or an alert) or off. Meta requires an
    # opt-in, and this is the evidence if the number's quality rating drops.
    whatsapp_opt_in_at: Mapped[datetime | None]
    whatsapp_opt_in_source: Mapped[str] = mapped_column(String(20), default="", server_default="")
    whatsapp_opt_out_at: Mapped[datetime | None]
```

Generate the migration as in Task 3 with `-m "whatsapp opt in record"`, `rm var/autogen.db`, `ruff format` the new file only. Expected: three `add_column` calls on `users`.

- [ ] **Step 4: One function records every change**

In `backend/app/modules/accounts/service.py`, after `request_code`:

```python
def set_whatsapp_opt_in(db: Session, user: User, on: bool, source: str) -> None:
    """Turn WhatsApp messages on or off and record when and how: settings, alert or whatsapp_stop."""
    if user.whatsapp_opt_in == on:
        return
    user.whatsapp_opt_in = on
    if on:
        user.whatsapp_opt_in_at, user.whatsapp_opt_in_source = utcnow(), source
    else:
        user.whatsapp_opt_out_at = utcnow()
    db.flush()
    record(db, user, "account.whatsapp_opt_in" if on else "account.whatsapp_opt_out", user, source=source)
```

- [ ] **Step 5: The three callers**

`backend/app/api/v1/me.py`: import `set_whatsapp_opt_in` beside `active_devices`, and replace lines 64–65:

```python
    if body.whatsapp_opt_in is not None:
        set_whatsapp_opt_in(db, user, body.whatsapp_opt_in, "settings")
```

`backend/app/modules/alerts/service.py`: add `from app.modules.accounts.service import set_whatsapp_opt_in`, and replace lines 99–100:

```python
    if channel == "whatsapp":
        set_whatsapp_opt_in(db, user, True, "alert")  # they asked for WhatsApp messages
```

`backend/app/api/v1/webhooks.py`: import `set_whatsapp_opt_in` beside `rate_limit`, and in `_stop` replace `user.whatsapp_opt_in = False` with:

```python
        set_whatsapp_opt_in(db, user, False, "whatsapp_stop")
```

- [ ] **Step 6: The export shows the record**

In `backend/app/modules/accounts/privacy.py`, after `"whatsapp_updates": user.whatsapp_opt_in,` add:

```python
            "whatsapp_opted_in_at": _iso(user.whatsapp_opt_in_at), "whatsapp_opt_in_source": user.whatsapp_opt_in_source,
            "whatsapp_opted_out_at": _iso(user.whatsapp_opt_out_at),
```

- [ ] **Step 7: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/accounts/models.py backend/migrations/versions/*_whatsapp_opt_in_record.py backend/app/modules/accounts/service.py backend/app/api/v1/me.py backend/app/modules/alerts/service.py backend/app/api/v1/webhooks.py backend/app/modules/accounts/privacy.py backend/tests/test_whatsapp.py
git commit -m "feat(whatsapp): record when and where each person opted in or out"
```

---

### Task 6: Confirm move-in on WhatsApp

**Files:**
- Create: `backend/app/modules/tenancies/whatsapp.py`
- Modify: `backend/app/api/v1/webhooks.py` (`_reply_text`: MOVED IN and YES)
- Modify: `backend/README.md` (protected payments: move-in on WhatsApp)
- Test: `backend/tests/test_tenancies.py` (append; it has the `funded` fixture)

**Interfaces:**
- Consumes: `tenancies.service.confirm_move_in(db, tenant, t, photo=None)`; `RateEvent(key, created_at)`; `format_ghs(pesewas)`.
- Produces: `REFERENCE` (compiled regex), `NOT_FOUND: str`, `start(db, sender, words) -> str`, `confirm(db, sender, words) -> str` in `app.modules.tenancies.whatsapp`; audit action `tenancy.move_in_whatsapp`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tenancies.py` (imports to add: `from app.modules.accounts.models import RateEvent, Role` in place of the `Role` import, and `from app.modules.notifications.providers import fake_outbox`):

```python
# --- Move-in on WhatsApp ------------------------------------------------------------------------------------------


def whatsapp(client, text, sender="233240000009"):
    body = {"entry": [{"changes": [{"value": {"messages": [{"from": sender, "type": "text", "text": {"body": text}}]}}]}]}
    assert client.post("/api/v1/webhooks/whatsapp", json=body).status_code == 200
    return fake_outbox.last("whatsapp", "+" + sender).body


def test_tenant_confirms_move_in_on_whatsapp(client, db, funded):
    ref = funded.reference
    db.commit()
    reply = whatsapp(client, f"MOVED IN {ref}")
    assert "I have the keys" in reply and f"YES {ref}" in reply
    assert funded.status == TenancyStatus.FUNDED  # nothing happens until YES
    assert "confirmed" in whatsapp(client, f"yes {ref.lower()}")
    assert funded.status == TenancyStatus.RELEASE_PENDING and funded.tenant_confirmed_at
    assert whatsapp(client, f"YES {ref}") == whatsapp(client, "MOVED IN AFE-T-000000")  # nothing more to confirm


def test_move_in_on_whatsapp_needs_the_tenants_number_and_a_fresh_yes(client, db, funded):
    ref = funded.reference
    db.commit()
    made_up = whatsapp(client, "MOVED IN AFE-T-000000")
    assert whatsapp(client, f"MOVED IN {ref}", sender="233244123456") == made_up  # the landlord's number
    assert whatsapp(client, f"YES {ref}", sender="233244123456") == made_up
    assert f"MOVED IN {ref}" in whatsapp(client, f"YES {ref}")  # YES before MOVED IN
    whatsapp(client, f"MOVED IN {ref}")
    db.scalar(select(RateEvent).where(RateEvent.key == f"wa-movein:{ref}")).created_at -= timedelta(minutes=31)
    db.commit()
    assert f"MOVED IN {ref}" in whatsapp(client, f"YES {ref}")  # too late: start again
    assert funded.status == TenancyStatus.FUNDED


def test_a_plain_yes_is_not_a_move_in(client, db, funded):
    db.commit()
    assert "a phone number or listing reference" in whatsapp(client, "Yes")
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_tenancies.py -k whatsapp`
Expected: FAIL: the reply to MOVED IN is the scam-check answer, not the three statements.

- [ ] **Step 3: The conversation**

Create `backend/app/modules/tenancies/whatsapp.py`:

```python
"""Confirming move-in on WhatsApp.

The tenant sends "MOVED IN AFE-T-1A2B3C" from the phone number on their Afe account. Afe answers with the three
things the tenancy page asks them to check, and "YES AFE-T-1A2B3C" within 30 minutes confirms, exactly as the
page's button does. A message that doesn't match a tenancy of that number waiting for move-in gets the same
answer as a made-up reference, so the command can't be used to find out which references exist.
"""

import re
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.ghana import format_ghs
from app.db import utcnow
from app.modules.accounts.models import RateEvent
from app.modules.audit.log import record

from . import service
from .models import Tenancy, TenancyStatus

ANSWER_WITHIN = timedelta(minutes=30)
REFERENCE = re.compile(r"\bAFE-T-[0-9A-F]{6}\b", re.IGNORECASE)
NOT_FOUND = (
    "There's no tenancy waiting for your move-in under that reference for this number. Send MOVED IN and the "
    "reference on your tenancy page (like AFE-T-1A2B3C), from the number on your Afe account."
)


def _waiting(db: Session, sender: str, words: str) -> Tenancy | None:
    match = REFERENCE.search(words)
    if match is None:
        return None
    tenancy = db.scalar(select(Tenancy).where(Tenancy.reference == match.group(0).upper()))
    if tenancy is None or tenancy.status != TenancyStatus.FUNDED:
        return None
    if tenancy.tenant.phone != sender or not tenancy.tenant.is_active:
        return None
    return tenancy


def _key(tenancy: Tenancy) -> str:
    return f"wa-movein:{tenancy.reference}"


def start(db: Session, sender: str, words: str) -> str:
    """MOVED IN <reference>: ask the tenant to check the three statements, then wait for YES."""
    tenancy = _waiting(db, sender, words)
    if tenancy is None:
        return NOT_FOUND
    db.execute(delete(RateEvent).where(RateEvent.key == _key(tenancy)))
    db.add(RateEvent(key=_key(tenancy)))
    db.flush()
    landlord = tenancy.landlord.name
    return (
        f"Before Afe releases {format_ghs(tenancy.payout_pesewas)} to {landlord}, check that all three are true:\n"
        "• I have the keys\n"
        "• The home matches the listing and photos\n"
        f"• I met the verified landlord, {landlord}\n"
        f"If they are, reply YES {tenancy.reference} within 30 minutes. If something is wrong, don't reply YES: "
        "tell us on the tenancy page on Afe."
    )


def confirm(db: Session, sender: str, words: str) -> str:
    """YES <reference>, within 30 minutes of MOVED IN: confirm the move-in, as the tenancy page does."""
    tenancy = _waiting(db, sender, words)
    if tenancy is None:
        return NOT_FOUND
    asked = db.scalar(
        select(RateEvent).where(RateEvent.key == _key(tenancy), RateEvent.created_at > utcnow() - ANSWER_WITHIN)
    )
    if asked is None:
        return f"Send MOVED IN {tenancy.reference} first, so we can check the details with you."
    db.execute(delete(RateEvent).where(RateEvent.key == _key(tenancy)))
    try:
        service.confirm_move_in(db, tenancy.tenant, tenancy)
    except DomainError as exc:
        return str(exc)
    record(db, tenancy.tenant, "tenancy.move_in_whatsapp", tenancy)
    return f"Thank you. Your move-in is confirmed, and Afe will release the payment to {tenancy.landlord.name}."
```

- [ ] **Step 4: The webhook knows the commands**

In `backend/app/api/v1/webhooks.py`, add `from app.modules.tenancies import whatsapp as move_in`, and in `_reply_text` after the `VIEW` branch:

```python
    if command == "MOVED" and rest.upper().startswith("IN"):
        return move_in.start(db, sender, rest)
    if command == "YES" and move_in.REFERENCE.search(rest):
        return move_in.confirm(db, sender, rest)
```

- [ ] **Step 5: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_tenancies.py tests/test_billing.py tests/test_renter_growth.py`
Expected: all pass.

- [ ] **Step 6: Docs**

In `backend/README.md`, in the protected payments section where the tenant's move-in confirmation is described, add:

```
A tenant can also confirm on WhatsApp: "MOVED IN AFE-T-…" from the number on their account, then "YES AFE-T-…"
within 30 minutes. Anything that doesn't match gets the same answer as a made-up reference.
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/tenancies/whatsapp.py backend/app/api/v1/webhooks.py backend/tests/test_tenancies.py backend/README.md
git commit -m "feat(whatsapp): tenants confirm move-in with MOVED IN and YES"
```

---

### Task 7: Alarms on the number's quality and on failing templates

**Files:**
- Create: `backend/app/modules/notifications/alarms.py`
- Modify: `backend/app/modules/notifications/service.py` (two staff templates)
- Modify: `backend/app/modules/notifications/whatsapp_templates.py` (`NOT_ON_WHATSAPP`)
- Modify: `backend/app/api/v1/webhooks.py` (`phone_number_quality_update`)
- Modify: `backend/app/worker.py` (`DAILY_JOBS`), `backend/app/cli.py` (`whatsapp-health`)
- Modify: `infra/terraform/staging/operations.tf` (schedule), `infra/terraform/staging/README.md` (jobs table, webhook fields), `backend/README.md`
- Test: `backend/tests/test_whatsapp.py`

**Interfaces:**
- Consumes: `notify_on(db, user, template, channels, link, **ctx)`.
- Produces: `quality_update(db, value: dict) -> bool`, `whatsapp_health(db, now=None) -> dict` in `app.modules.notifications.alarms`; templates `whatsapp_quality`, `whatsapp_health`; daily job and command `whatsapp-health` at 06:00 UTC.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_whatsapp.py` (import to add: `from app.modules.notifications.alarms import whatsapp_health`):

```python
# --- Alarms ---------------------------------------------------------------------------------------------------------


def _quality(event) -> dict:
    value = {"display_phone_number": "233300000000", "event": event, "current_limit": "TIER_1K"}
    return {"entry": [{"changes": [{"field": "phone_number_quality_update", "value": value}]}]}


def test_a_quality_warning_reaches_the_admins(client, db):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    db.commit()
    assert client.post("/api/v1/webhooks/whatsapp", json=_quality("UPGRADE")).status_code == 200
    assert fake_outbox.last("sms", boss.phone) is None
    client.post("/api/v1/webhooks/whatsapp", json=_quality("FLAGGED"))
    assert "flagged" in fake_outbox.last("sms", boss.phone).body
    assert not [m for m in fake_outbox.messages if m.channel == "whatsapp"]  # never about WhatsApp on WhatsApp


def test_the_daily_check_finds_templates_that_keep_failing(db, landlord):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    for i in range(10):
        db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                            template="viewing_confirmed", status="failed" if i < 2 else "delivered"))
    for _ in range(9):  # too few to judge
        db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                            template="new_message", status="failed"))
    db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                        template="viewing_confirmed", status="failed", created_at=utcnow() - timedelta(days=2)))
    db.flush()
    assert whatsapp_health(db) == {"templates": 2, "failing": ["viewing_confirmed"]}
    assert "viewing_confirmed: 2 of 10 failed" in fake_outbox.last("sms", boss.phone).body
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py`
Expected: collection error: `No module named 'app.modules.notifications.alarms'`.

- [ ] **Step 3: Staff templates**

In `backend/app/modules/notifications/service.py`, add to `TEMPLATES` after `model_report`:

```python
    "whatsapp_quality": (
        "WhatsApp number at risk",
        "Meta reports \"{event}\" for Afe's WhatsApp number {number}. Messaging limit: {limit}. Check its quality "
        "rating in WhatsApp Manager today.",
    ),
    "whatsapp_health": (
        "WhatsApp messages failing",
        "WhatsApp messages failed in the last day: {summary}. Check the templates and the number's quality rating "
        "in WhatsApp Manager.",
    ),
```

In `backend/app/modules/notifications/whatsapp_templates.py`, add both to `NOT_ON_WHATSAPP`:

```python
NOT_ON_WHATSAPP = {
    "check_reply", "staff_invite", "pilot_report", "model_report", "tenancy_review_invite", "whatsapp_quality",
    "whatsapp_health",
}
```

- [ ] **Step 4: The alarms**

Create `backend/app/modules/notifications/alarms.py`:

```python
"""Alarms on Afe's WhatsApp number: Meta's quality warnings, and templates that keep failing.

A number whose quality drops gets a lower messaging limit and can be restricted, which cuts off sign-in codes
and notices. Admins hear the same day: in the app, by email and by SMS, never on WhatsApp itself.
"""

import json
import logging
from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import utcnow

from .models import DeliveryStatus, Notification, NotificationChannel
from .service import notify_on

log = logging.getLogger("afe.whatsapp")
# Meta's quality events that need a person: the number was flagged, or its messaging limit went down.
WARNINGS = {"FLAGGED", "DOWNGRADE"}
HEALTH_WINDOW = timedelta(hours=24)
HEALTH_MIN_MESSAGES = 10
HEALTH_MAX_FAILED = 0.2


def _tell_admins(db: Session, template: str, **ctx) -> None:
    from app.modules.accounts.models import Role, User

    for admin in db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True))):
        notify_on(db, admin, template, {"in_app", "email", "sms"}, **ctx)


def quality_update(db: Session, value: dict) -> bool:
    """Meta's phone_number_quality_update webhook. Every event is logged; a warning goes to the admins."""
    event = str(value.get("event", ""))
    limit = str(value.get("current_limit", "") or "unknown")
    log.info(json.dumps({"event": "whatsapp_quality", "quality_event": event, "limit": limit}))
    if event not in WARNINGS:
        return False
    _tell_admins(db, "whatsapp_quality", event=event.lower(), number=value.get("display_phone_number", ""),
                 limit=limit)
    return True


def whatsapp_health(db: Session, now=None) -> dict:
    """Daily: any template with 10 or more WhatsApp messages in the last day, a fifth or more of them failed,
    goes to the admins (Meta may have paused it, or filed it under another category)."""
    now = now or utcnow()
    failed = func.sum(case((Notification.status == DeliveryStatus.FAILED, 1), else_=0))
    rows = db.execute(
        select(Notification.template, func.count(), failed)
        .where(Notification.channel == NotificationChannel.WHATSAPP, Notification.created_at > now - HEALTH_WINDOW)
        .group_by(Notification.template)
        .order_by(Notification.template)
    ).all()
    failing = [(t, n, int(f or 0)) for t, n, f in rows if n >= HEALTH_MIN_MESSAGES and (f or 0) / n >= HEALTH_MAX_FAILED]
    if failing:
        _tell_admins(db, "whatsapp_health", summary="; ".join(f"{t}: {f} of {n} failed" for t, n, f in failing))
    return {"templates": len(rows), "failing": [t for t, _, _ in failing]}
```

- [ ] **Step 5: The webhook passes quality events on**

In `backend/app/api/v1/webhooks.py`, add `from app.modules.notifications import alarms`, and at the top of the `for change in entry.get("changes", []):` loop:

```python
            if change.get("field") == "phone_number_quality_update":
                alarms.quality_update(db, change.get("value", {}))
                continue
```

- [ ] **Step 6: The daily job**

`backend/app/worker.py`, add to `DAILY_JOBS`:

```python
    DailyJob("whatsapp-health", 86400, "app.modules.notifications.alarms:whatsapp_health", at_hour=6),
```

`backend/app/cli.py`: docstring line after `pilot-report`:

```
whatsapp-health  tell admins about WhatsApp templates that keep failing (daily)
```

parser: `sub.add_parser("whatsapp-health", help="daily check for WhatsApp templates that keep failing")`, and in the database block:

```python
        elif args.command == "whatsapp-health":
            from app.modules.notifications.alarms import whatsapp_health

            print(whatsapp_health(db))
```

`infra/terraform/staging/operations.tf`, add to `local.jobs`, then run `terraform fmt`:

```hcl
    "whatsapp-health" = "cron(0 6 * * ? *)" # WhatsApp templates that keep failing, 06:00
```

- [ ] **Step 7: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass, including `tests/test_worker.py` (every daily job runs against the database).

- [ ] **Step 8: Docs**

`infra/terraform/staging/README.md`: add rows to the jobs table after `pilot-report`:

```
| `weekly-models` | Mondays 05:00 | scheduler | Weekly model report; retrains the wording model while it's in shadow |
| `whatsapp-health` | 06:00 | scheduler | Tells admins about WhatsApp templates where a fifth or more of the day's messages failed |
```

and add to the WhatsApp step: "Subscribe the webhook to the `messages` and `phone_number_quality_update` fields. A quality warning (flagged, or a lower messaging limit) goes to admins at once."

`backend/README.md`, Launch readiness → Messages, append: "Meta's delivery reports mark WhatsApp messages delivered or read. Admins hear about a quality warning on the number at once, and `whatsapp-health` tells them each morning about any template where a fifth or more of the day's messages failed."

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/notifications/alarms.py backend/app/modules/notifications/service.py backend/app/modules/notifications/whatsapp_templates.py backend/app/api/v1/webhooks.py backend/app/worker.py backend/app/cli.py backend/tests/test_whatsapp.py infra/terraform/staging/operations.tf infra/terraform/staging/README.md backend/README.md
git commit -m "feat(whatsapp): alarms on the number's quality and on failing templates"
```

---

## Final check (after Task 7)

- `.venv/Scripts/python -m pytest` (whole suite) and `.venv/Scripts/python -m ruff check app tests` pass.
- `terraform fmt -check` and `terraform validate` pass in `infra/terraform/staging/`.
- In `frontend/`: `npx svelte-check --threshold error` reports 0 errors.
- `git status` shows no `var/`, `.env` or database files.
