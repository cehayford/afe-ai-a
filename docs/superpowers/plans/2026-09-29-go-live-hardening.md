# Go-Live Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gaps between the WhatsApp build and a real launch, and harden the money path before the pilot. WhatsApp templates stay in step with Meta, and messages that never arrive go by SMS in time. Admins hear about template problems. Tenants learn they can confirm move-in on WhatsApp. Payment webhooks are kept as evidence, and every money exception reaches a person the same day.

**Architecture:** WhatsApp work stays in `notifications/` (the template registry, service and alarms) and the webhook. Money work stays in `tenancies/service.py`, with one new model for webhook evidence in `audit/` (append-only, like the audit log). A new `notify_admins` helper in `notifications/service.py` carries every staff alarm.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pytest, Meta's WhatsApp Cloud API (Graph `v21.0`), one line of SvelteKit copy.

**Spec:**
- The WhatsApp go-live review's deferred minors (template drift and the missing edit path, stale SMS fallback, the health check at pilot volume, telling tenants about MOVED IN). They were ledgered at the end of `docs/superpowers/plans/2026-09-29-whatsapp-go-live.md`'s execution.
- "Afe's WhatsApp and payments plan", Payments → "Changes before the pilot": change 3 (refuse webhooks older than a few minutes, log every raw payload) and change 5 (alarms on a failed release or refund, any reconciliation difference, and the held total near the pilot cap). It's in git at `feature/working-functionalities:docs/Afe_WhatsApp_Payments.html`.
- Meta's docs, checked 29 Sep 2026:
  - **Template management:** edit with `POST /{template_id}`. Only category, components or time-to-live can change. Only `APPROVED`, `REJECTED` or `PAUSED` templates can be edited, and an approved one at most once a day and ten times in 30 days. List with `GET /{waba}/message_templates?fields=…`, paged.
  - **Time-to-live:** set with `message_send_ttl_seconds`, 30–900 s for authentication, 30–43,200 s for utility, 43,200–2,592,000 s for marketing. When it runs out, "assume the message was dropped" (no report is promised).
  - **`message_template_status_update` webhook:** `event` is one of `APPROVED`, `REJECTED`, `PAUSED`, `DISABLED`, `FLAGGED`, …, with `reason`, `message_template_name` and `message_template_category`.
  - **`template_category_update` webhook:** `new_category`, plus `correct_category` for a change still to come or `previous_category` for one that's done.

## Global Constraints

- **How to run things:** run every command from `backend/` with `.venv/Scripts/python` (Windows) or `.venv/bin/python`.
- **Tests:** `.venv/Scripts/python -m pytest` (the repo's `addopts` adds `-q`).
- **Lint:** `.venv/Scripts/python -m ruff check app tests` passes. Run `ruff format` only on new migration files.
- **Migrations:** they must match the models (`tests/test_flows.py::test_migrations_match_the_models`). Generate them with `AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/autogen.db`, then delete `var/autogen.db`. Keep Alembic's generated comments, as the existing migrations do.
- **Terraform:** `terraform fmt -check` and `terraform validate` pass in `infra/terraform/staging/`.
- **Staff messages** never go on WhatsApp: every new staff template goes in `NOT_ON_WHATSAPP`.
- **Money:** a model or an alarm never moves money. Alarms only tell people. Every money state change stays in the existing service functions.
- **Copy:** plain English, sentence case.
- **Never commit** `.env`, databases or `var/`.

## Review Focus

1. **A partner webhook with no signed send time, a naive timestamp, a garbled one, or one in the future.** It's refused and kept as evidence, and it never crashes the endpoint or moves money. Tested in Task 5.
2. **A refund or release the partner refuses inside `run_due`.** The job still finishes, the rest of that run's work is kept, the tenancy stays as it was, and admins are told once however many times the job retries. Tested in Task 6.
3. **Meta's template list spans several pages, or has the same name in another language.** Only Afe's language is compared, and nothing is created twice. Tested in Task 1.
4. **No delivery reports arrive at all** (the webhook isn't subscribed to message statuses). The time-to-live sweep sends no SMS, and the daily health check says reports are missing. Tested in Tasks 2 and 3.
5. **A failure report that arrives hours or weeks late.** No SMS for a stale notice, and no new sign-in code once the old one has expired. Tested in Task 2.

---

### Task 1: WhatsApp templates stay in step with Meta

**Files:**
- Modify: `backend/app/modules/notifications/whatsapp_templates.py`: docstring, time-to-live, `matches`, and `sync_all` in place of `submit_all`
- Modify: `backend/app/cli.py`: `whatsapp-templates` gets `--bodies`, and `--submit` calls `sync_all`
- Create: `backend/tests/whatsapp_templates.json`, the wording snapshot
- Modify: `backend/tests/test_whatsapp.py`: replace the two `submit_all` tests; add sync, time-to-live and snapshot tests
- Modify: `backend/README.md` and `infra/terraform/staging/README.md` (the `--submit` sentences)

**Interfaces:**
- Produces:
  - `WaTemplate.ttl_seconds -> int`, used by Task 2's sweep
  - `WaTemplate.matches(at_meta: dict) -> bool`
  - `sync_all() -> list[dict]`. Each result has `name`, plus `action` (`created`, `edited` or `unchanged`) or `error`, plus `status` and `category` when Meta gave them.
  - Constants `UTILITY_TTL_SECONDS = 3600`, `MARKETING_TTL_SECONDS = 43200` and `EDITABLE = {"APPROVED", "REJECTED", "PAUSED"}`
  - CLI `whatsapp-templates --bodies`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_whatsapp.py`, import `sync_all` instead of `submit_all`. Delete `test_submit_sends_every_template_and_reports_each_one` and `test_submit_needs_the_business_account`, and add:

```python
SNAPSHOT = Path(__file__).parent / "whatsapp_templates.json"


def _meta(name, body, status="APPROVED", category="UTILITY", language="en", id_="tpl-1") -> dict:
    return {"id": id_, "name": name, "language": language, "status": status, "category": category,
            "components": [{"type": "BODY", "text": body}]}


def test_sync_creates_edits_and_leaves_alone(graph):
    calls, answers = graph
    otp = {"id": "tpl-0", "name": "afe_sign_in_code", "language": "en", "status": "APPROVED",
           "category": "AUTHENTICATION", "components": [{"type": "BODY"}, {"type": "FOOTER", "code_expiration_minutes": 10}]}
    same = _meta("afe_viewing_confirmed", whatsapp_template("viewing_confirmed").body, id_="tpl-1")
    old = _meta("afe_new_message", "Afe: {{sender}} wrote about {{listing}}.", id_="tpl-2")
    other_language = _meta("afe_review_received", "Un locataire…", language="fr", id_="tpl-3")
    answers.append({"data": [otp, same], "paging": {"next": "https://graph.facebook.com/v21.0/next-page"}})
    answers.append({"data": [old, other_language]})
    results = {r["name"]: r for r in sync_all()}
    assert calls[0].get_method() == "GET" and "fields=id,name,language,status,category,components" in calls[0].full_url
    assert calls[1].full_url == "https://graph.facebook.com/v21.0/next-page"
    assert results["afe_sign_in_code"]["action"] == "unchanged"
    assert results["afe_viewing_confirmed"]["action"] == "unchanged"
    assert results["afe_new_message"]["action"] == "edited"
    edit = next(c for c in calls if c.full_url.endswith("/tpl-2"))
    assert json.loads(edit.data) == {"components": whatsapp_template("new_message").submission()["components"]}
    assert results["afe_review_received"]["action"] == "created"  # only the French one existed
    created = [json.loads(c.data)["name"] for c in calls if c.full_url.endswith("/waba-1/message_templates")]
    assert len(created) == len(registry()) - 3 and "afe_review_received" in created
    assert not any("error" in r for r in results.values())


def test_sync_reports_what_it_cannot_do(graph):
    _, answers = graph
    reviewing = _meta("afe_new_message", "Afe: {{sender}} wrote.", status="PENDING", id_="tpl-2")
    moved = _meta("afe_account_restored", whatsapp_template("account_restored").body, category="MARKETING", id_="tpl-4")
    answers.append({"data": [reviewing, moved]})
    results = {r["name"]: r for r in sync_all()}
    assert "while it's PENDING" in results["afe_new_message"]["error"]
    assert "filed it as MARKETING" in results["afe_account_restored"]["error"]


def test_sync_needs_the_business_account(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_business_account_id", "")
    with pytest.raises(providers.DeliveryError, match="AFE_WHATSAPP_BUSINESS_ACCOUNT_ID"):
        sync_all()


def test_each_template_says_how_long_meta_keeps_trying():
    assert whatsapp_template("otp").submission()["message_send_ttl_seconds"] == get_settings().otp_minutes * 60
    assert whatsapp_template("viewing_confirmed").submission()["message_send_ttl_seconds"] == 3600
    assert whatsapp_template("search_alert").submission()["message_send_ttl_seconds"] == 43200  # Meta's minimum


def test_whatsapp_wording_matches_the_snapshot():
    bodies = {wa.name: wa.body for wa in registry().values()}
    assert bodies == json.loads(SNAPSHOT.read_text(encoding="utf-8")), (
        "A WhatsApp template's wording changed. If you meant it, update the snapshot "
        "(python -m app.cli whatsapp-templates --bodies > tests/whatsapp_templates.json), then run "
        "python -m app.cli whatsapp-templates --submit so Meta reviews the new wording."
    )


def test_the_command_prints_the_bodies(capsys):
    assert main(["whatsapp-templates", "--bodies"]) == 0
    assert json.loads(capsys.readouterr().out) == {wa.name: wa.body for wa in registry().values()}
```

Add `from pathlib import Path` to the imports.

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py`
Expected: collection error: `cannot import name 'sync_all'`.

- [ ] **Step 3: Time-to-live, matching and sync**

In `backend/app/modules/notifications/whatsapp_templates.py`:

Replace the docstring's last paragraph with:

```
`python -m app.cli whatsapp-templates --submit` creates the templates Meta doesn't have and edits the ones whose
wording changed (Meta reviews every edit, and allows one a day on an approved template). The wording is pinned
by tests/whatsapp_templates.json, so a change to a text in TEMPLATES that goes to WhatsApp can't slip through.
```

After `MAX_PARAMETER = 500` add:

```python
# How long Meta keeps trying to deliver (its time-to-live). A code is useless once it expires; a notice that
# can't arrive within the hour goes by SMS instead; 12 hours is Meta's shortest for marketing.
UTILITY_TTL_SECONDS = 3600
MARKETING_TTL_SECONDS = 43200
# Meta can edit a template only in these states.
EDITABLE = {"APPROVED", "REJECTED", "PAUSED"}
```

In `WaTemplate`, after `body`:

```python
    @property
    def ttl_seconds(self) -> int:
        """How long Meta keeps trying to deliver one of these messages."""
        if self.category == AUTHENTICATION:
            return min(max(get_settings().otp_minutes * 60, 30), 900)
        return MARKETING_TTL_SECONDS if self.category == MARKETING else UTILITY_TTL_SECONDS

    def matches(self, at_meta: dict) -> bool:
        """Whether the template Meta has says what this one says."""
        components = {c.get("type"): c for c in at_meta.get("components", [])}
        if self.category == AUTHENTICATION:
            return components.get("FOOTER", {}).get("code_expiration_minutes") == get_settings().otp_minutes
        return components.get("BODY", {}).get("text") == self.body
```

In `submission`, start `out` with the time-to-live:

```python
        out = {"name": self.name, "language": s.whatsapp_template_language, "category": self.category,
               "message_send_ttl_seconds": self.ttl_seconds}
```

Replace `submit_all` with:

```python
def _at_meta(base: str, headers: dict) -> dict[str, dict]:
    """Afe's templates at Meta in Afe's language, by name, from every page of the list."""
    s = get_settings()
    url = f"{base}/{s.whatsapp_business_account_id}/message_templates?fields=id,name,language,status,category,components&limit=100"
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
        _request(f"{base}/{at_meta['id']}", {"components": wa.submission()["components"]}, headers, "WhatsApp")
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
```

- [ ] **Step 4: The command**

In `backend/app/cli.py`, change the docstring line to `whatsapp-templates  print the WhatsApp templates (--submit creates or updates them at Meta, --bodies prints the wording)`, add the argument `templates.add_argument("--bodies", action="store_true", help="print each template's wording (the test snapshot)")`, and in the handler import `sync_all` instead of `submit_all`, then:

```python
        if args.bodies:
            print(json.dumps({wa.name: wa.body for wa in registry().values()}, indent=2, sort_keys=True))
            return 0
        if not args.submit:
            print(json.dumps([wa.submission() for wa in registry().values()], indent=2))
            return 0
        try:
            results = sync_all()
```

(the rest unchanged).

- [ ] **Step 5: The snapshot**

Run: `AFE_DEBUG=1 .venv/Scripts/python -m app.cli whatsapp-templates --bodies > tests/whatsapp_templates.json`
Expected: a JSON object with one entry per template (`afe_sign_in_code` … `afe_featured_paid`).

- [ ] **Step 6: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py`
Expected: all pass.

- [ ] **Step 7: Docs**

- **`backend/README.md`:** replace "`python -m app.cli whatsapp-templates --submit` sends them to Meta for review" with "`python -m app.cli whatsapp-templates --submit` creates them at Meta, and edits any whose wording changed; `tests/whatsapp_templates.json` pins the wording".
- **`infra/terraform/staging/README.md`:** replace "Fix and resubmit any Meta rejects or files under a different category." with "Run it again after changing a message's wording: it edits only the templates that changed (Meta allows one edit a day to an approved template). Fix and rerun any it reports as rejected or filed under a different category."

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/notifications/whatsapp_templates.py backend/app/cli.py backend/tests/test_whatsapp.py backend/tests/whatsapp_templates.json backend/README.md infra/terraform/staging/README.md
git commit -m "feat(whatsapp): keep templates in step with Meta (create or edit), with a time-to-live and a wording snapshot"
```

---

### Task 2: WhatsApp messages that never arrive go by SMS in time

**Files:**
- Modify: `backend/app/modules/notifications/service.py`: `FALLBACK_WITHIN`, `REPORT_GRACE`, `_undelivered`, a stale-report guard in `fallback_to_sms`, `apply_whatsapp_status`, and `expire_undelivered`
- Modify: `backend/app/worker.py` (`JOBS`), `backend/app/cli.py` (`expire-whatsapp`), and `backend/tests/test_worker.py` (the job names)
- Modify: `infra/terraform/staging/README.md` (the jobs table)
- Test: `backend/tests/test_whatsapp.py`

**Interfaces:**
- Consumes: `WaTemplate.ttl_seconds` (Task 1), `fallback_to_sms`, `resend_code_by_sms`
- Produces:
  - `expire_undelivered(db, now=None) -> dict` (keys `expired`, `reporting`)
  - `_undelivered(db, note, error)`
  - worker job and command `expire-whatsapp`, every 5 minutes

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_whatsapp.py` (import `expire_undelivered` from the service):

```python
# --- Messages that never arrive -------------------------------------------------------------------------------


def _delivered_recently(db, landlord):
    ok = _whatsapp_notice(db, landlord)
    apply_whatsapp_status(db, {"id": ok.provider_ref, "status": "delivered"})


def test_a_failure_reported_hours_late_sends_no_sms(db, landlord):
    wa = _whatsapp_notice(db, landlord)
    wa.created_at -= timedelta(hours=7)
    apply_whatsapp_status(db, {"id": wa.provider_ref, "status": "failed", "errors": [{"code": 131026}]})
    assert wa.status == "failed"
    assert db.scalar(select(func.count()).select_from(Notification).where(Notification.fallback_of_id == wa.id)) == 0


def test_a_message_with_no_report_after_its_time_to_live_goes_by_sms(db, landlord):
    _delivered_recently(db, landlord)
    late = _whatsapp_notice(db, landlord)
    fresh = _whatsapp_notice(db, landlord)
    late.created_at -= timedelta(hours=1, minutes=11)
    assert expire_undelivered(db) == {"expired": 1, "reporting": True}
    assert late.status == "failed" and "time-to-live" in late.error and fresh.status == "sent"
    sms = db.scalar(select(Notification).where(Notification.fallback_of_id == late.id))
    assert sms.channel == "sms" and sms.status == "sent"


def test_no_sweep_while_no_delivery_reports_arrive(db, landlord):
    wa = _whatsapp_notice(db, landlord)
    wa.created_at -= timedelta(hours=2)
    assert expire_undelivered(db) == {"expired": 0, "reporting": False}
    assert wa.status == "sent"
```

In `backend/tests/test_worker.py`, add `"expire-whatsapp"` to the expected set of `JOBS` names (line 44).

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py tests/test_worker.py`
Expected: `ImportError: cannot import name 'expire_undelivered'`, and the worker set check fails.

- [ ] **Step 3: The service**

In `backend/app/modules/notifications/service.py`, after `BOTH_CHANNELS`:

```python
# A failure reported later than this is about a stale notice: it isn't sent again by SMS.
FALLBACK_WITHIN = timedelta(hours=6)
# How long after a message's time-to-live Afe waits for Meta's delivery report before deciding it was dropped.
REPORT_GRACE = timedelta(minutes=10)
```

In `fallback_to_sms`, move `db.flush()` to the top (the row needs its id and time), and add the age check:

```python
    db.flush()  # the WhatsApp row needs its id and time
    wa = whatsapp_template(note.template)
    if (note.user_id is None or wa is None or wa.category == MARKETING or note.template in SENSITIVE
            or note.template in BOTH_CHANNELS or note.created_at < utcnow() - FALLBACK_WITHIN):
        return None
    note.attempts = MAX_ATTEMPTS
```

Add after `fallback_to_sms`:

```python
def _undelivered(db: Session, note: Notification, error: str) -> None:
    """WhatsApp won't deliver this message: stop trying it there, and get it to the person another way."""
    note.status, note.attempts, note.error = DeliveryStatus.FAILED, MAX_ATTEMPTS, error[:300]
    if note.template in SENSITIVE:
        from app.modules.accounts.service import resend_code_by_sms  # accounts imports this module

        resend_code_by_sms(db, note.recipient)
    else:
        fallback_to_sms(db, note)
```

In `apply_whatsapp_status`, replace the failed branch's body with:

```python
        error = (status.get("errors") or [{}])[0]
        _undelivered(db, note, f"{error.get('code', '')}: {error.get('title', '')}")
```

At the end of the file:

```python
def expire_undelivered(db: Session, now=None) -> dict:
    """Every few minutes: a WhatsApp message with no delivery report once its time-to-live has passed was
    dropped by Meta, which doesn't always say so; it goes by SMS instead. Skipped while no delivery reports
    arrive at all (the webhook isn't subscribed), when every message would look undelivered."""
    now = now or utcnow()
    reporting = db.scalar(select(Notification.id).where(
        Notification.channel == NotificationChannel.WHATSAPP, Notification.delivered_at > now - timedelta(days=1)
    ).limit(1)) is not None
    expired = 0
    if reporting:
        rows = db.scalars(select(Notification).where(
            Notification.channel == NotificationChannel.WHATSAPP, Notification.status == DeliveryStatus.SENT,
            Notification.created_at > now - FALLBACK_WITHIN, Notification.template.not_in(list(FREE_FORM)),
        ).order_by(Notification.id))
        for note in list(rows):
            wa = whatsapp_template(note.template)
            if wa is None or note.created_at + timedelta(seconds=wa.ttl_seconds) + REPORT_GRACE > now:
                continue
            _undelivered(db, note, "Not delivered within its time-to-live")
            expired += 1
        db.flush()
    return {"expired": expired, "reporting": reporting}
```

- [ ] **Step 4: The job**

- **`backend/app/worker.py`:** add `Job("expire-whatsapp", 300, "app.modules.notifications.service:expire_undelivered"),` after `retry-messages`.
- **`backend/app/cli.py`:** add the docstring line `expire-whatsapp WhatsApp messages with no delivery report after their time-to-live go by SMS (every 5 minutes)`, the parser `sub.add_parser("expire-whatsapp", help="send by SMS the WhatsApp messages that never arrived")`, and in the database block:

```python
        elif args.command == "expire-whatsapp":
            from app.modules.notifications.service import expire_undelivered

            print(expire_undelivered(db))
```

- [ ] **Step 5: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py tests/test_worker.py tests/test_auth.py`
Expected: all pass.

- [ ] **Step 6: Docs**

In `infra/terraform/staging/README.md`, add a jobs-table row after `retry-messages`:

```
| `expire-whatsapp` | every 5 min | worker | WhatsApp messages with no delivery report after their time-to-live go by SMS |
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/notifications/service.py backend/app/worker.py backend/app/cli.py backend/tests/test_whatsapp.py backend/tests/test_worker.py infra/terraform/staging/README.md
git commit -m "feat(whatsapp): messages with no delivery report after their time-to-live go by SMS; no SMS for stale failures"
```

---

### Task 3: Admins hear about template problems and missing reports

**Files:**
- Modify: `backend/app/modules/notifications/service.py`: `notify_admins`, and the `whatsapp_template` staff template
- Modify: `backend/app/modules/notifications/alarms.py`: use `notify_admins`, add `template_update`, and change the health rule and the missing-reports check
- Modify: `backend/app/modules/notifications/whatsapp_templates.py` (`NOT_ON_WHATSAPP`)
- Modify: `backend/app/api/v1/webhooks.py` (the two template fields)
- Modify: `infra/terraform/staging/README.md` (the webhook fields)
- Test: `backend/tests/test_whatsapp.py`

**Interfaces:**
- Produces:
  - `notify_admins(db, template, link="", **ctx) -> None`, which Task 6 uses
  - `template_update(db, field: str, value: dict) -> bool`
  - `whatsapp_health` now returns `{"templates", "failing", "no_reports"}`, and a template counts as failing at 3 or more failures and a fifth or more of its messages

- [ ] **Step 1: Write the failing tests**

In `test_the_daily_check_finds_templates_that_keep_failing`, make 3 of the 10 `viewing_confirmed` rows failed (`"failed" if i < 3`), change its `new_message` loop to 2 rows (`for _ in range(2):  # too few failures to judge`), expect `{"templates": 2, "failing": ["viewing_confirmed"], "no_reports": False}`, and expect `"viewing_confirmed: 3 of 10 failed"` in the admin's SMS. Then append:

```python
def _template_event(field, value) -> dict:
    return {"entry": [{"changes": [{"field": field, "value": value}]}]}


def test_meta_template_problems_reach_the_admins(client, db):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    db.commit()
    approved = {"event": "APPROVED", "message_template_name": "afe_new_message", "reason": "NONE"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("message_template_status_update", approved))
    assert fake_outbox.last("sms", boss.phone) is None
    rejected = {"event": "REJECTED", "message_template_name": "afe_new_message", "reason": "INVALID_FORMAT"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("message_template_status_update", rejected))
    assert "afe_new_message" in fake_outbox.last("sms", boss.phone).body
    assert "rejected (INVALID_FORMAT)" in fake_outbox.last("sms", boss.phone).body
    fake_outbox.clear()
    same = {"message_template_name": "afe_search_alert", "new_category": "MARKETING"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("template_category_update", same))
    assert fake_outbox.last("sms", boss.phone) is None  # already marketing
    moving = {"message_template_name": "afe_viewing_confirmed", "new_category": "UTILITY", "correct_category": "MARKETING"}
    client.post("/api/v1/webhooks/whatsapp", json=_template_event("template_category_update", moving))
    assert "moved to marketing" in fake_outbox.last("sms", boss.phone).body


def test_the_daily_check_notices_when_no_delivery_reports_arrive(db, landlord):
    boss = make_user(db, "boss", Role.ADMIN, phone="0200000001")
    for i in range(10):
        db.add(Notification(user_id=landlord.id, channel="whatsapp", recipient=landlord.phone, body="x",
                            template="viewing_confirmed", status="sent", provider_ref=f"wamid.{i}"))
    db.flush()
    assert whatsapp_health(db) == {"templates": 1, "failing": [], "no_reports": True}
    assert "no delivery reports" in fake_outbox.last("sms", boss.phone).body
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py -k "daily_check or template_problems"`
Expected: FAIL. There's no `no_reports` key and no template alarm.

- [ ] **Step 3: One helper for every staff alarm**

In `backend/app/modules/notifications/service.py`, change the accounts import to `from app.modules.accounts.models import Role, User`. After `notify_on`, add:

```python
def notify_admins(db: Session, template: str, link: str = "", **ctx) -> None:
    """Tell every active admin, in the app, by email and by SMS (staff messages never go on WhatsApp)."""
    for admin in db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True))):
        notify_on(db, admin, template, {"in_app", "email", "sms"}, link, **ctx)
```

Add to `TEMPLATES` after `whatsapp_health`:

```python
    "whatsapp_template": (
        "WhatsApp template needs attention",
        "Meta reports that the {name} WhatsApp template is {event}. Reword it and run "
        "python -m app.cli whatsapp-templates --submit; until then its messages may go by SMS.",
    ),
```

Add `"whatsapp_template"` to `NOT_ON_WHATSAPP` in `whatsapp_templates.py`.

- [ ] **Step 4: Alarms**

In `backend/app/modules/notifications/alarms.py`:
- Delete `_tell_admins`, and call `notify_admins` everywhere it was used.
- Import `notify_admins` from `.service` in place of `notify_on`, and `registry` from `.whatsapp_templates`.
- Replace `HEALTH_MIN_MESSAGES = 10` with:

```python
# A template is failing at 3 or more failures and a fifth or more of its messages: few enough to notice at pilot
# volume, when the SMS fallback would otherwise hide a template Meta paused.
HEALTH_MIN_FAILED = 3
# This many messages accepted in a day with no delivery report means the webhook isn't getting message statuses.
HEALTH_MIN_REPORTABLE = 10
# Meta's template events that need a person.
TEMPLATE_WARNINGS = {"REJECTED", "PAUSED", "DISABLED", "FLAGGED"}
```

Add:

```python
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
```

In `whatsapp_health`, count reports too, and use the new rule:

```python
    failed = func.sum(case((Notification.status == DeliveryStatus.FAILED, 1), else_=0))
    since = now - HEALTH_WINDOW
    rows = db.execute(
        select(Notification.template, func.count(), failed)
        .where(Notification.channel == NotificationChannel.WHATSAPP, Notification.created_at > since)
        .group_by(Notification.template)
        .order_by(Notification.template)
    ).all()
    failing = [(t, n, int(f or 0)) for t, n, f in rows if (f or 0) >= HEALTH_MIN_FAILED and (f or 0) / n >= HEALTH_MAX_FAILED]
    accepted, reported = db.execute(
        select(func.count(), func.count(Notification.delivered_at))
        .where(Notification.channel == NotificationChannel.WHATSAPP, Notification.created_at > since,
               Notification.provider_ref != "")
    ).one()
    no_reports = accepted >= HEALTH_MIN_REPORTABLE and reported == 0
    problems = [f"{t}: {f} of {n} failed" for t, n, f in failing]
    if no_reports:
        problems.append(f"no delivery reports for {accepted} messages (check the webhook gets message statuses)")
    if problems:
        notify_admins(db, "whatsapp_health", summary="; ".join(problems))
    return {"templates": len(rows), "failing": [t for t, _, _ in failing], "no_reports": no_reports}
```

Update `whatsapp_health`'s docstring to match: "3 or more failures and a fifth or more of the day's messages; or no delivery reports at all".

- [ ] **Step 5: The webhook**

In `backend/app/api/v1/webhooks.py`, after the `phone_number_quality_update` branch:

```python
            if change.get("field") in ("message_template_status_update", "template_category_update"):
                alarms.template_update(db, change["field"], change.get("value", {}))
                continue
```

- [ ] **Step 6: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_whatsapp.py tests/test_worker.py`
Expected: all pass.

- [ ] **Step 7: Docs**

In `infra/terraform/staging/README.md`, change "Subscribe the webhook to the `messages` and `phone_number_quality_update` fields" to "Subscribe the webhook to the `messages`, `phone_number_quality_update`, `message_template_status_update` and `template_category_update` fields", and add "; a rejected, paused or recategorised template does too" after "goes to admins at once".

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/notifications/service.py backend/app/modules/notifications/alarms.py backend/app/modules/notifications/whatsapp_templates.py backend/app/api/v1/webhooks.py backend/tests/test_whatsapp.py infra/terraform/staging/README.md
git commit -m "feat(whatsapp): admins hear about template problems and missing delivery reports"
```

---

### Task 4: Tell tenants they can confirm move-in on WhatsApp

**Files:**
- Modify: `backend/app/api/v1/webhooks.py` (HELP)
- Modify: `frontend/src/routes/tenancies/[reference]/+page.svelte` (the confirm section)
- Test: `backend/tests/test_tenancies.py`, `backend/tests/test_whatsapp.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tenancies.py` (protected payments are on there):

```python
def test_help_mentions_moved_in_while_protected_payments_are_on(client, db):
    assert "MOVED IN" in whatsapp(client, "hello")
```

Append to `backend/tests/test_whatsapp.py` (they're off by default):

```python
def test_help_leaves_out_moved_in_while_protected_payments_are_off(client):
    client.post("/api/v1/webhooks/whatsapp", json=_inbound("hello", sender="233551112222"))
    assert "MOVED IN" not in fake_outbox.last("whatsapp", "+233551112222").body
```

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_tenancies.py tests/test_whatsapp.py -k "help_mentions or help_leaves"`
Expected: the tenancies test fails (HELP has no MOVED IN line); the WhatsApp one passes (it pins the "off" case).

- [ ] **Step 3: HELP**

In `backend/app/api/v1/webhooks.py`, after `HELP`:

```python
MOVE_IN_HELP = "\n• MOVED IN and your tenancy reference (like AFE-T-1A2B3C), to confirm you've moved in"


def _help() -> str:
    return HELP + (MOVE_IN_HELP if get_settings().protected_payments_enabled else "")
```

Replace both `return HELP` in `_reply_text` with `return _help()`.

- [ ] **Step 4: The tenancy page**

In `frontend/src/routes/tenancies/[reference]/+page.svelte`, inside `{#if can('confirm_move_in')}`, after the closing `</form>`:

```svelte
					<p class="small muted" style="margin: 0">Prefer WhatsApp? Send <span class="mono">MOVED IN {t.reference}</span> to Afe from the phone number on your account, then reply YES within 30 minutes.</p>
```

- [ ] **Step 5: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_tenancies.py tests/test_whatsapp.py tests/test_billing.py tests/test_renter_growth.py`, and in `frontend/`: `npx svelte-check --threshold error`.
Expected: all pass; 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/webhooks.py backend/tests/test_tenancies.py backend/tests/test_whatsapp.py frontend/src/routes/tenancies/[reference]/+page.svelte
git commit -m "feat(whatsapp): tell tenants they can confirm move-in on WhatsApp"
```

---

### Task 5: Payment webhooks are kept as evidence; old partner deliveries are refused

**Files:**
- Modify: `backend/app/modules/audit/models.py` (`WebhookReceipt`, append-only)
- Create: `backend/app/modules/audit/webhooks.py` (`keep`)
- Modify: `backend/app/models.py` (import `WebhookReceipt`)
- Create: `backend/migrations/versions/<date>_<rev>_webhook_receipts.py` (autogenerated)
- Modify: `backend/app/modules/tenancies/partners.py` (`PartnerEvent.sent_at`, `MAX_WEBHOOK_AGE`, `is_fresh`, the contract docstring, and `TestEscrow.parse_webhook`)
- Modify: `backend/app/api/v1/common.py` (`rejected`), `backend/app/api/v1/payments.py`, `backend/app/api/v1/tenancies.py`
- Modify: `backend/README.md` (protected payments; data rights)
- Test: `backend/tests/test_billing.py` (fees) and `backend/tests/test_tenancies.py` (partner)

**Interfaces:**
- Produces:
  - `WebhookReceipt` (table `webhook_receipts`): `received_at`, `source`, `endpoint` (`fees` or `tenancies`), `outcome` (`applied`, `unmatched`, `ignored`, `rejected` or `stale`), `reference`, `error`, `headers`, `body`
  - `keep(db, source, endpoint, body, headers, outcome, reference="", error="") -> WebhookReceipt`
  - `PartnerEvent.sent_at: datetime | None`
  - `is_fresh(event, now=None) -> bool`
  - `rejected(message="Webhook rejected.") -> JSONResponse`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_billing.py` (imports: `from sqlalchemy import select` if missing, `from app.modules.audit.models import WebhookReceipt`):

```python
def test_every_fee_webhook_is_kept_as_evidence(client, db, monkeypatch):
    assert client.post("/api/v1/payments/webhook", content=b'{"reference": "AFE-P-NONE", "amount": 100}').status_code == 200
    bad = client.post("/api/v1/payments/webhook", content=b"not json")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_input"
    monkeypatch.setattr(get_settings(), "payment_provider", "app.modules.billing.providers.Paystack")
    monkeypatch.setattr(get_settings(), "paystack_secret_key", "sk_test")
    forged = client.post("/api/v1/payments/webhook", content=b'{"event": "charge.success"}',
                         headers={"x-paystack-signature": "0" * 128})
    assert forged.status_code == 422
    receipts = list(db.scalars(select(WebhookReceipt).order_by(WebhookReceipt.id)))
    assert [(r.source, r.endpoint, r.outcome) for r in receipts] == [
        ("fake", "fees", "unmatched"), ("fake", "fees", "rejected"), ("paystack", "fees", "rejected")]
    assert receipts[1].body == "not json" and "signature" in receipts[2].error
    assert receipts[2].headers["x-paystack-signature"] == "0" * 128
    receipts[0].outcome = "applied"
    with pytest.raises(PermissionError):
        db.flush()  # evidence can't be changed
```

Append to `backend/tests/test_tenancies.py` (imports: `from app.modules.audit.models import AuditEvent, WebhookReceipt` replacing the `AuditEvent` import, `from app.db import utcnow` is already there):

```python
def _partner_webhook(client, t, sent_at):
    ref = TestEscrow.record_charge(t.reference, t.charge_pesewas)
    body = {"kind": "charge.succeeded", "reference": t.reference, "amount": t.charge_pesewas, "partner_ref": ref}
    if sent_at is not None:
        body["sent_at"] = sent_at
    return client.post("/api/v1/tenancies/webhook", json=body)


def test_partner_webhooks_are_kept_and_old_ones_refused(client, db, viewed, verified_landlord, renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    db.commit()
    for sent_at in [(utcnow() - timedelta(minutes=6)).isoformat(), (utcnow() + timedelta(minutes=6)).isoformat(),
                    "2026-01-01T10:00:00", "yesterday"]:
        assert _partner_webhook(client, t, sent_at).status_code == 422
    assert t.status == TenancyStatus.FUNDING
    assert _partner_webhook(client, t, utcnow().isoformat()).status_code == 200
    assert t.status == TenancyStatus.FUNDED
    receipts = [(r.outcome, r.reference) for r in db.scalars(select(WebhookReceipt).order_by(WebhookReceipt.id))]
    assert receipts == [("stale", t.reference), ("stale", t.reference), ("stale", t.reference),
                        ("rejected", ""), ("applied", t.reference)]


def test_a_partner_event_without_a_signed_send_time_is_refused(client, db, monkeypatch, viewed, verified_landlord,
                                                              renter, payee):
    t = offer(db, viewed, verified_landlord)
    tenancies.accept(db, renter, t)
    db.commit()
    unsigned = PartnerEvent("charge.succeeded", t.reference, t.charge_pesewas, "p-1")
    monkeypatch.setattr(TestEscrow, "parse_webhook", lambda self, body, headers: unsigned)
    assert _partner_webhook(client, t, None).status_code == 422 and t.status == TenancyStatus.FUNDING
```

(`"2026-01-01T10:00:00"` has no zone, so it's read as UTC and is months old: stale. `"yesterday"` doesn't parse: rejected.)

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py tests/test_tenancies.py -k "evidence or partner_webhooks or signed_send"`
Expected: `ImportError: cannot import name 'WebhookReceipt'`.

- [ ] **Step 3: The model and its migration**

In `backend/app/modules/audit/models.py`, add `Text` to the SQLAlchemy import, and after `AuditEvent`:

```python
class WebhookReceipt(Base):
    """Every payment webhook as it arrived, accepted or not: evidence for a replayed or disputed confirmation.
    Written once, never changed. Kept with the payments and tenancies when an account closes."""

    __tablename__ = "webhook_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    received_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(20))  # the provider's name, e.g. paystack
    endpoint: Mapped[str] = mapped_column(String(20))  # fees or tenancies
    outcome: Mapped[str] = mapped_column(String(20))  # applied, unmatched, ignored, rejected or stale
    reference: Mapped[str] = mapped_column(String(40), default="", index=True)
    error: Mapped[str] = mapped_column(String(300), default="")
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    body: Mapped[str] = mapped_column(Text)
```

Make both append-only: decorate `_no_update` and `_no_delete` with a second `@event.listens_for(WebhookReceipt, ...)` line each (the functions move below `WebhookReceipt`). In `_no_bulk_changes`, check `m.class_ in (AuditEvent, WebhookReceipt)`. Add `WebhookReceipt` to the audit import in `backend/app/models.py`.

Generate the migration with `-m "webhook receipts"`, delete `var/autogen.db`, and `ruff format` the new file only.

- [ ] **Step 4: Keeping a receipt**

Create `backend/app/modules/audit/webhooks.py`:

```python
"""Payment webhooks as they arrived, kept as evidence whether or not Afe accepted them."""

from sqlalchemy.orm import Session

from .models import WebhookReceipt

MAX_BODY = 64 * 1024
# Nothing a partner sends needs these, and they could hold credentials.
SKIP_HEADERS = {"authorization", "cookie"}


def keep(db: Session, source: str, endpoint: str, body: bytes, headers: dict[str, str], outcome: str,
         reference: str = "", error: str = "") -> WebhookReceipt:
    receipt = WebhookReceipt(
        source=source[:20], endpoint=endpoint, outcome=outcome, reference=reference[:40], error=error[:300],
        headers={k: v[:500] for k, v in headers.items() if k not in SKIP_HEADERS},
        body=body[:MAX_BODY].decode("utf-8", errors="replace"),
    )
    db.add(receipt)
    db.flush()
    return receipt
```

In `backend/app/api/v1/common.py`, add `from fastapi.responses import JSONResponse` and `from app.core.envelope import Envelope, ErrorBody`, and:

```python
def rejected(message: str = "Webhook rejected.") -> JSONResponse:
    """InvalidInput's 422, returned rather than raised so the request still commits (the evidence is kept)."""
    body = Envelope(error=ErrorBody(code=InvalidInput.code, message=message))
    return JSONResponse(body.model_dump(), status_code=InvalidInput.status_code)
```

- [ ] **Step 5: The partner contract**

In `backend/app/modules/tenancies/partners.py`:
- Add `from datetime import UTC, datetime, timedelta` and `from app.db import utcnow`.
- Replace "A real partner implements the same five calls." in the docstring with:

```
A real partner implements the same calls. Its parse_webhook verifies the signature and sets `sent_at` from the
signed time of the delivery (not of the event), so the partner's own retries pass and a request captured and
replayed later is refused (MAX_WEBHOOK_AGE).
```

- Add `sent_at: datetime | None = None  # the signed delivery time` to `PartnerEvent`, after `raw`.
- After `PartnerEvent`, add:

```python
MAX_WEBHOOK_AGE = timedelta(minutes=5)


def is_fresh(event: PartnerEvent, now: datetime | None = None) -> bool:
    """A delivery signed within MAX_WEBHOOK_AGE of now (either way, for clock drift)."""
    return event.sent_at is not None and abs((now or utcnow()) - event.sent_at) <= MAX_WEBHOOK_AGE
```

Replace `TestEscrow.parse_webhook` with:

```python
    def parse_webhook(self, body, headers) -> PartnerEvent | None:
        data = json.loads(body)
        sent_at = datetime.fromisoformat(data["sent_at"]) if "sent_at" in data else utcnow()
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=UTC)
        return PartnerEvent(data["kind"], data["reference"], int(data["amount"]), data.get("partner_ref", ""), data,
                            sent_at)
```

- [ ] **Step 6: The endpoints**

`backend/app/api/v1/payments.py`:
- Import `from app.modules.audit.webhooks import keep` and `rejected` from `.common` (beside `get_or_404`).
- Replace `webhook` with:

```python
@router.post("/webhook", include_in_schema=False)
async def webhook(db: DB, request: Request):
    """The payment partner calls this. The provider checks the signature, and every delivery is kept as
    evidence, accepted or not. There's no age check: Paystack signs only the body and resends for up to three
    days, and a resend changes nothing because payments are applied once by reference."""
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    provider = get_provider()
    try:
        event = provider.parse_webhook(body, headers)
    except (PaymentError, ValueError, KeyError) as exc:
        keep(db, provider.name, "fees", body, headers, "rejected", error=str(exc))
        return rejected()
    if event is None:
        keep(db, provider.name, "fees", body, headers, "ignored")
        return {"ok": True}
    payment = billing.apply_webhook(db, event)
    keep(db, provider.name, "fees", body, headers, "applied" if payment else "unmatched", reference=event.reference)
    return {"ok": True}
```

`backend/app/api/v1/tenancies.py`:
- Import `keep`, `rejected`, and `is_fresh` (from `app.modules.tenancies.partners`, beside `get_partner`).
- Replace `webhook` with:

```python
@router.post("/webhook", include_in_schema=False)
async def webhook(db: DB, request: Request):
    """The escrow partner calls this. The partner class checks the signature; a delivery signed more than a few
    minutes ago is refused; every delivery is kept as evidence."""
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    partner = get_partner()
    try:
        event = partner.parse_webhook(body, headers)
    except (PartnerError, ValueError, KeyError, json.JSONDecodeError) as exc:
        keep(db, partner.name, "tenancies", body, headers, "rejected", error=str(exc))
        return rejected()
    if event is None:
        keep(db, partner.name, "tenancies", body, headers, "ignored")
        return {"ok": True}
    if not is_fresh(event):
        keep(db, partner.name, "tenancies", body, headers, "stale", reference=event.reference,
             error=f"Signed at {event.sent_at}")
        return rejected("Webhook too old.")
    t = tenancies.apply_partner_event(db, event)
    keep(db, partner.name, "tenancies", body, headers, "applied" if t else "unmatched", reference=event.reference)
    return {"ok": True}
```

- [ ] **Step 7: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest tests/test_billing.py tests/test_tenancies.py tests/test_flows.py`
Expected: all pass.

- [ ] **Step 8: Docs**

`backend/README.md`, protected payments list, after the "Partner events are idempotent…" bullet's line:

```
- Every payment webhook (fees and held rent) is kept as it arrived, accepted or not, and can't be changed. The
  partner signs when it sent each delivery; one signed more than 5 minutes away from now is refused.
```

And in the data-rights sentence of what closing an account keeps, add "payment webhooks as received" after "payments".

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/audit/models.py backend/app/modules/audit/webhooks.py backend/app/models.py backend/migrations/versions/*_webhook_receipts.py backend/app/modules/tenancies/partners.py backend/app/api/v1/common.py backend/app/api/v1/payments.py backend/app/api/v1/tenancies.py backend/tests/test_billing.py backend/tests/test_tenancies.py backend/README.md
git commit -m "feat(payments): keep every payment webhook as evidence; refuse partner deliveries signed too long ago"
```

---

### Task 6: Every money exception reaches a person the same day

**Files:**
- Modify: `backend/app/modules/tenancies/service.py`: `CAP_WARNING`, `_money_alarm`, the four money flags, `run_due`, `nightly_reconcile`, and the cap warning in `accept`
- Modify: `backend/app/modules/notifications/service.py`: three staff templates
- Modify: `backend/app/modules/notifications/whatsapp_templates.py` (`NOT_ON_WHATSAPP`)
- Modify: `backend/app/worker.py` (the reconcile target), `backend/app/cli.py` (`reconcile` uses `nightly_reconcile`)
- Modify: `backend/README.md`, `infra/terraform/staging/README.md` (the reconcile row)
- Test: `backend/tests/test_tenancies.py`

**Interfaces:**
- Consumes: `notify_admins(db, template, link, **ctx)` (Task 3)
- Produces:
  - `nightly_reconcile(db) -> list[dict]`
  - `run_due(...)` counts gain `failed`
  - templates `money_alert`, `money_reconcile` and `money_cap`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tenancies.py` (imports: `from app.modules.risk.models import RiskFlag` is already there; add `make_user` if missing):

```python
@pytest.fixture
def boss(db):
    return make_user(db, "boss", Role.ADMIN, phone="0200000001")


def _admin_texts(boss) -> list[str]:
    return [m.body for m in fake_outbox.messages if m.channel == "sms" and m.recipient == boss.phone]


def test_a_refused_refund_tells_admins_once_and_the_job_carries_on(db, monkeypatch, funded, boss):
    def refuse(*args, **kwargs):
        raise PartnerError("wallet closed")

    monkeypatch.setattr(TestEscrow, "refund", refuse)
    late = funded.move_in_date + timedelta(days=4)
    assert tenancies.run_due(db, today=late)["failed"] == 1
    assert tenancies.run_due(db, today=late)["failed"] == 1  # retried every few minutes, told once
    assert funded.status == TenancyStatus.FUNDED
    flag = db.scalar(select(RiskFlag).where(RiskFlag.rule == "money.refund_failed"))
    assert flag.status == "open" and "wallet closed" in flag.explanation
    texts = _admin_texts(boss)
    assert len(texts) == 1 and "wallet closed" in texts[0] and funded.reference in texts[0]


def test_a_failed_payout_from_the_partner_tells_admins(db, monkeypatch, funded, renter, reviewer, boss):
    monkeypatch.setattr(TestEscrow, "release", lambda self, *a: Transfer("rel-1", completed=False))
    tenancies.confirm_move_in(db, renter, funded)
    tenancies.approve_release(db, reviewer, funded)
    tenancies.apply_partner_event(db, PartnerEvent("release.failed", funded.reference, funded.payout_pesewas, "rel-1"))
    assert any("could not pay the landlord" in t for t in _admin_texts(boss))


def test_reconciliation_differences_reach_admins(db, funded, boss):
    test_book.lines.clear()  # the partner's statement lost the charge
    problems = tenancies.nightly_reconcile(db)
    assert len(problems) == 1
    assert "1 difference" in _admin_texts(boss)[0]


def test_admins_hear_when_held_money_nears_the_pilot_limit(db, monkeypatch, viewed, verified_landlord, renter, payee,
                                                           boss):
    t = offer(db, viewed, verified_landlord)
    monkeypatch.setitem(compliance.RULES, "pilot_max_held_pesewas",
                        dataclasses.replace(compliance.RULES["pilot_max_held_pesewas"], default=int(t.held_pesewas / 0.9)))
    tenancies.accept(db, renter, t)
    assert any("pilot limit" in text for text in _admin_texts(boss))
```

Add `Transfer` to the `partners` import.

- [ ] **Step 2: Run the tests to watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_tenancies.py -k "admins or refused_refund or reconciliation"`
Expected: FAIL. `run_due` raises `RuleViolation`, `nightly_reconcile` doesn't exist, and no admin texts are sent.

- [ ] **Step 3: Staff templates**

In `backend/app/modules/notifications/service.py` `TEMPLATES`, after `whatsapp_template`:

```python
    "money_alert": ("Money needs a person", "{explanation} Tenancy {reference}. Open the money page on Afe today."),
    "money_reconcile": (
        "Reconciliation differences",
        "{count} difference(s) between Afe's ledger and the partner's statement, e.g. {example}. Open the money "
        "page on Afe today.",
    ),
    "money_cap": (
        "Pilot limit nearly reached",
        "Afe now holds or is collecting {held} of the {limit} pilot limit. Tenants can't accept offers once it's full.",
    ),
```

Add the three to `NOT_ON_WHATSAPP`.

- [ ] **Step 4: Money alarms in the service**

In `backend/app/modules/tenancies/service.py`:
- Add `DomainError` to the `app.core.errors` import.
- Change the notifications import to `from app.modules.notifications.service import notify, notify_admins`.
- Change the risk import to `from app.modules.risk.flags import open_flags, raise_flag`.

After the imports and constants add:

```python
# Admins are warned when the money held (or being collected) reaches this share of the pilot's limit.
CAP_WARNING = 0.8


def _money_alarm(db: Session, t: Tenancy, flag_rule: str, explanation: str) -> None:
    """A money exception: a high-severity flag for the money page, and admins told at once. Once while the flag
    is open, however often the job that found it runs again."""
    already = any(f.rule == flag_rule for f in open_flags(db, t))
    raise_flag(db, t, flag_rule, Severity.HIGH, explanation)
    if not already:
        notify_admins(db, "money_alert", link="/review/money", explanation=explanation, reference=t.reference)
```

Replace the four `raise_flag(db, t, "money.…", Severity.HIGH, …)` calls in `apply_partner_event` with `_money_alarm(db, t, "money.…", …)` (same rule and text).

In `accept`, replace the cap check:

```python
    held_before, limit = held_total(db), rule(db, "pilot_max_held_pesewas")
    if held_before + t.held_pesewas > limit:
        raise RuleViolation("Afe's protected payments are full for now during the pilot. Try again in a few days.")
```

and after `record(db, tenant, "tenancy.accepted", t)`:

```python
    if held_before < limit * CAP_WARNING <= held_before + t.held_pesewas:
        notify_admins(db, "money_cap", link="/review/money", held=format_ghs(held_before + t.held_pesewas),
                      limit=format_ghs(limit))
```

In `run_due`, make `counts = {"expired": 0, "refunded": 0, "released": 0, "failed": 0}` and replace the FUNDED loop:

```python
    for t in list(db.scalars(select(Tenancy).where(Tenancy.status == TenancyStatus.FUNDED))):
        refund = t.landlord_evidence_at is None and today > t.move_in_date + grace
        release = t.landlord_evidence_at is not None and today >= t.move_in_date + fallback
        if not (refund or release):
            continue
        try:
            with db.begin_nested():  # a refused payout mustn't undo the rest of this run, or stop it
                if refund:
                    _send_refund(db, t, None, "Home not delivered by the move-in date")
                else:
                    _request_release(db, t, None, "Landlord evidence and no dispute after the move-in period")
        except DomainError as exc:
            _money_alarm(db, t, "money.refund_failed" if refund else "money.release_failed", str(exc))
            counts["failed"] += 1
            continue
        counts["refunded" if refund else "released"] += 1
```

After `reconcile`:

```python
def nightly_reconcile(db: Session) -> list[dict]:
    """The nightly job: reconcile, and tell admins about any difference the same morning."""
    problems = reconcile(db)
    if problems:
        first = problems[0]
        notify_admins(db, "money_reconcile", link="/review/money", count=len(problems),
                      example=f"{first['tenancy']} {first['kind']}: {first['problem']}")
    return problems
```

- [ ] **Step 5: The nightly job uses it**

- **`backend/app/worker.py`:** set the `reconcile` target to `"app.modules.tenancies.service:nightly_reconcile"`.
- **`backend/app/cli.py`:** in the `reconcile` branch, import and call `nightly_reconcile` instead of `reconcile`.

- [ ] **Step 6: Run the tests to watch them pass**

Run: `.venv/Scripts/python -m pytest`
Expected: all pass.

- [ ] **Step 7: Docs**

`backend/README.md`, protected payments list, after the webhook-evidence bullet:

```
- Money exceptions reach admins at once, by SMS, email and in the app: a refund or payout the partner refuses
  or fails, a wrong amount, a payment after the offer expired, any reconciliation difference, and the money held
  reaching 80% of the pilot limit. A refused refund or release doesn't stop the scheduled job; it's retried and
  admins are told once.
```

In `infra/terraform/staging/README.md`, change the `reconcile` row's description to "Ledger against the partner's statement; admins are told about any difference, and the job exits with an error".

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/tenancies/service.py backend/app/modules/notifications/service.py backend/app/modules/notifications/whatsapp_templates.py backend/app/worker.py backend/app/cli.py backend/tests/test_tenancies.py backend/README.md infra/terraform/staging/README.md
git commit -m "feat(payments): every money exception reaches admins the same day; a refused payout no longer stops run-due"
```

---

## Final check (after Task 6)

- `.venv/Scripts/python -m pytest` (whole suite) and `.venv/Scripts/python -m ruff check app tests` pass.
- `terraform fmt -check` and `terraform validate` pass in `infra/terraform/staging/`.
- In `frontend/`: `npx svelte-check --threshold error` reports 0 errors.
- `git status` shows no `var/`, `.env` or database files.
