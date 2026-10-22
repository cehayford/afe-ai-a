# Afe backend

The Afe API: FastAPI, SQLAlchemy 2, Alembic and Pydantic settings. It serves JSON only, under `/api/v1`; every page lives
in the separate [frontend](../frontend/). PostgreSQL and S3 in staging and production; SQLite and local folders for
development and tests.

## Run it locally

Needs Python 3.12. No database server is required locally.

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # macOS/Linux: .venv/bin/pip
export AFE_DEBUG=1                                     # PowerShell: $env:AFE_DEBUG = "1"
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.cli seed-demo             # demo areas, people, 4 verified homes, a renter enquiry
.venv/Scripts/uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/api/docs. In debug mode the fake SMS/WhatsApp/email providers print what they "send"
(including sign-in codes) to the console, and `python -m app.cli totp <username>` prints a demo account's current
authenticator code.

`seed-demo` runs the real verification flow (Ghana Card check, owner authority, visit assignment, field visit with
photos, reviewer decisions, publish, then an enquiry and a viewing request), so if it succeeds the whole Phase 1
journey works.

## Checks

```bash
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
.venv/Scripts/alembic check                 # models and migrations agree
.venv/Scripts/python -m pytest              # add AFE_TEST_DATABASE_URL=postgresql+psycopg://... to run on Postgres
```

After changing a model: `alembic revision --autogenerate -m "what changed"`, review it (new non-null columns on existing
tables need a `server_default`), and check it downgrades.

## Layout

```
app/
  main.py            app factory, error envelope, dev media files
  config.py          settings from AFE_* variables; refuses fakes, local storage and weak keys in production
  db.py              engine, session per request, UTC datetimes
  deps.py            bearer-token auth and role checks
  api/schemas.py     request and response shapes
  api/v1/            one router per module: auth, me, kyc, properties, messages, verify, review, payments,
                     tenancies, check, events, webhooks
  modules/
    accounts/        accounts, SMS codes, authenticator (TOTP), rotating refresh tokens, attempt limits
    notifications/   outbox + in-app inbox; SMS, WhatsApp, email behind provider interfaces
    identity/        Ghana Card checks via a pluggable KYC provider; card numbers kept only as a keyed hash
    areas/ units/    service areas and price bands; the register of homes and authority documents
    verification/    visit assignments, field visits, Afe-taken photos, reviewer decisions and expiry
    listings/        listings on verified homes, one active per home, the verification panel
    enquiries/       saved homes, message threads (scam-language warnings), viewings
    billing/         verification fee and featured listings via hosted checkout (Paystack or a test provider),
                     signed webhooks, waivers
    tenancies/       Phase 2 protected payments: offers, escrow partner interface, append-only ledger + outbox,
                     payout accounts, release/refund, disputes, scheduled work, reconciliation
    compliance/      money and legal limits as versioned settings; every change needs two reviewers
    reviews/         tenant reviews, only from tenancies that were paid out
    detection/       Phase 3 models: scam wording, price, photos, documents, linked accounts; score queue,
                     labels from reviewer decisions, evaluation against the rules, training
    risk/            rule-based flags; scamcheck/ "Check before you pay" and reports; analytics/ events
    audit/           append-only log of every trust decision
    media/           photo processing and storage (local folders or S3)
  seed.py, cli.py    demo data and command-line tasks
migrations/          Alembic
```

Business rules live in each module's `service.py`; routers only translate HTTP. Services flush and the request commits
once at the end, so a failed rule leaves nothing half-written. (Sign-in attempt records are the deliberate exception:
they're committed even when the request fails, so limits can't be dodged.)

## Rules the code enforces

- A listing goes live only if the lister and the home each have a current verification, the lister has accepted
  authority over the home, and there are no open high-severity flags. A home has at most one active listing.
- A home is verified only after an accepted ownership or authority document, a settled fee, and a passed field visit
  from the last 30 days: assigned by a reviewer, checked in within 150 m of the pin, at least 4 photos, and approved by
  someone other than the verifier. Verifiers rotate between landlords and can't visit homes they own or let.
- Photos are re-encoded as WebP with all metadata removed, and hashed; a photo matching another home raises a
  high-severity flag. Documents go to private storage, are read only by reviewers, and every read is logged.
- The same Ghana Card on two accounts fails the check and flags both accounts.
- Landlords, agents and staff must pass an authenticator step. Refresh tokens rotate; reusing one after 30 seconds
  signs every device in that session out.
- Messages asking for money before a viewing are marked for the renter and flag the lister.
- Payments are marked paid only by the partner's signed webhook, with the amount checked.
- "Check before you pay" (web and WhatsApp) only ever says "verified by Afe" or "not verified by Afe".
- **Launch offer:** every Afe charge (the verification fee, the protection fee and featured listings) is free before
  the `free_period_until` rule date. The default is 5 Jun 2027: the first 8 months of Year 1, counting W1 as
  5 Oct 2026. Tenancies paid during the offer are refunded in full, because Afe absorbs the gateway's fee. Featuring is
  free one period at a time. The date is a rule, so ending or extending the offer needs two reviewers, not a deploy.
  `GET /api/v1/pricing` says what applies today.
- **Uploaded documents are scanned for malware** (ClamAV) before they're stored. Infected files are refused and the
  uploader is flagged. If the scanner can't be reached, the upload is refused too (fail closed).
- **Public endpoints are rate-limited:** 60 checks and 5 scam reports per hour per visitor, and 30 WhatsApp lookups per
  hour per sender (each reply is a paid message).
- **Unannounced re-checks:** 15% of approved homes (rule `qa_recheck_percent`) get a second visit from a different
  verifier. A failed re-check flags the home (which blocks publishing) and the first verifier. Pass rates, re-checks
  and reversals per verifier are at `GET /api/v1/review/verifier-stats`.
- **Receipts:** tenants and landlords can download a PDF receipt for money paid or received.
- **Device links:** the web app gives each browser a random ID (cookie `afe_dev`). Public accounts signed in on the
  same device are linked for the fraud graph. Staff accounts are left out. The privacy notice must say this.

### Protected payments (Phase 2)

Off until `AFE_PROTECTED_PAYMENTS_ENABLED=1`, which is refused in production with the test partner. It waits on
counsel's opinion and a licensed partner (gate B7). Afe never holds money: the partner does, and Afe keeps a ledger.

- A landlord can offer a tenancy only after a completed viewing, with both the landlord and the home verified and a payout
  account set. Advance rent is capped by Act 220 (6 months for leases over 6 months, 2 otherwise), and the deposit
  by rule. Pilot limits cap each tenancy and the total held.
- The terms are written into a PDF summary when the tenant accepts. The tenant then pays through the partner's
  checkout. Partner events are idempotent by partner reference, and a wrong amount raises a flag instead of funding.
- Every payment webhook (fees and held rent) is kept as it arrived, accepted or not, and can't be changed. The
  partner signs when it sent each delivery; one signed more than 5 minutes away from now is refused.
- Money exceptions reach admins at once, by SMS, email and in the app: a refund or payout the partner refuses
  or fails, a wrong amount, a payment after the offer expired, any reconciliation difference, and the money held
  reaching 80% of the pilot limit. A refused refund or release doesn't stop the scheduled job; it's retried and
  admins are told once. One whose outcome is unknown (the partner call broke) isn't retried until a person
  resolves its flag, and unsigned webhook deliveries keep only their first 2 KB and a fingerprint.
- The money is released when the tenant confirms move-in. During the pilot a reviewer approves every release. If the
  landlord recorded the handover and nobody disputes it, the release happens after the move-in period. If the home isn't
  handed over within the grace days, the tenant is refunded, less the gateway's fee.
- A tenant can also confirm on WhatsApp: "MOVED IN AFE-T-…" from the number on their account, then "YES AFE-T-…"
  within 30 minutes. Anything that doesn't match gets the same answer as a made-up reference.
- Payout accounts must be in the verified Ghana Card name. A change needs an authenticator code, alerts the landlord,
  and receives money only after 72 hours.
- Either side can raise a dispute while money is held. That pauses everything until a reviewer (not a party to the
  tenancy) decides release or refund.
- Every tenancy stores the rule versions it was made under. Rule changes and rollbacks need a second reviewer.
- Only tenants of a paid-out tenancy can review the landlord.

Scheduled tasks: `python -m app.cli run-due` every few minutes, `reconcile` nightly (exit 1 on any difference), and
`publish-outbox` every minute. The test partner keeps its statement in the API process's memory, so `reconcile` from
a separate process reports differences in development. Use the reviewer's Money page instead. The test partner's
wallets are in `DEMO_WALLETS` (`app/modules/tenancies/partners.py`). `0209998888` belongs to someone else, to try the
name check.

### Fraud detection (Phase 3)

Six detectors: one for each capability in build plan §7, plus Claude doing the wording job in its own lane:

| Model | Scores | How |
|---|---|---|
| `scam_text` | listings, messages | Weighted signals on top of the Phase 1 wording rules. A naive Bayes model trained on labels is blended in once `train-text` has run. |
| `scam_text_llm` | listings, messages | Claude (`claude-haiku-4-5`, official SDK, structured output) on redacted text. **Off** until counsel clears sending text abroad (B11); turning it on is a rule change two reviewers make, with `AFE_ANTHROPIC_API_KEY` set. At most 20 of its jobs run per `score-pending` run. |
| `price` | listings | Rent against the median of Afe's own comparable listings (8 or more), otherwise against the price survey |
| `photos` | homes | Closest match to another home's visit photos on two hashes together, which catches crops and re-colours |
| `documents` | authority documents | Editing software in the metadata, late edits, saved revisions, typed text boxes |
| `accounts` | accounts | Links through a shared Ghana Card, payout account, photo, or a phone number handed out in messages, to accounts already found to be fraudulent |

- **Every model starts in shadow** (the Claude one starts off). It scores and logs, and changes nothing. Scoring runs
  from a queue (`score-pending`), so a slow model never slows a page.
- **Every human decision is a label:** verification decisions (rejections count as fraud only for deception reasons,
  not missing paperwork), publishing a listing, resolving a flag, accepting a document, and upheld scam reports.
- **Leaving shadow:** `canary` (acts on 10% of cases) and `active` are rule changes. They need an evaluation that beats
  the Phase 1 rules on at least 30 labelled cases (5 or more fraud), on both precision and recall, without more false
  alarms. A second reviewer must also approve.
- **What acting means:** raising a medium flag for a person, and warning on a message if no rule already did. A model
  never rejects, bans or holds money.
- **The account graph** is rebuilt nightly (`detect-graph`). Link evidence never stores the raw card number or
  account number.

Scheduled tasks: `score-pending` every minute, `detect-graph` nightly, and `weekly-models` on Mondays. The weekly job
keeps one report per model per ISO week (shown on the reviewers' Models page, and sent to reviewers). It also retrains
the in-house wording model while that model is in shadow, but only once the current version has enough decided cases
(30) to be judged. `train-text` trains by hand (5 fraud and 5 genuine examples at least).

**Seeded test set.** `app/modules/detection/seeded_cases.json` holds fake and genuine listings the team writes (12 to
start, 50 planned). `python -m app.cli eval-seeded` scores them in memory with the wording and price models and the
Phase 1 rules, and prints recall and the fakes each model missed. The cases are never written as listings, so they
can't reach the site or training.

**Reviewer copilot (shadow).** `app/modules/agents/` makes one structured Claude call per home verification: masked
facts only (no names, contact details, addresses, coordinates, photos or files), a suggested decision and reason codes,
stored in `agent_runs` and measured against the reviewer's decision (`copilot-report`, and the Models page). Nobody sees
a suggestion. It's off until counsel clears B11 and two reviewers set `agent_copilot_level` to `shadow`; the rule
`agent_copilot_daily_tokens` caps its daily spend. `python -m app.cli eval-copilot` runs it on 30 hand-written test cases
(`agents/copilot_cases.json`) and fails under 85% agreement or on any false approval of a fraud-type rejection.

### Launch readiness (roadmap workstream A)

- **Messages:** real senders for WhatsApp (`WhatsAppCloud`, Meta's Cloud API), SMS (`HubtelSms`) and email (`SesEmail`). Each
  event Afe sends on WhatsApp has its own template (`notifications/whatsapp_templates.py`; `python -m app.cli
  whatsapp-templates --submit` creates them at Meta, and edits any whose wording changed;
  `tests/whatsapp_templates.json` pins the wording), sign-in codes use Meta's authentication template,
  and replies to people who write to Afe go as free text. Check each against the live account in staging.
  Failed messages are retried by `retry-messages` (3 tries in a day, waiting 5 then 30 minutes). Sign-in codes are
  never retried. People who opted in get notices on WhatsApp instead of SMS (by SMS if WhatsApp fails), and money
  events go by both. When and where each person opted in or out is recorded and is in their data export. Meta's
  delivery reports mark WhatsApp messages delivered or read. Admins hear about a quality warning on the number at
  once, and `whatsapp-health` tells them each morning about any template with 3 or more failed messages (a fifth or more
  of its day), or no delivery reports at all. Meta's template warnings (rejected, paused, recategorised) reach them
  at once, and a WhatsApp message with no delivery report after its time-to-live goes by SMS (`expire-whatsapp`).
- **Data rights (Act 843):** `GET /api/v1/me/export` returns everything Afe holds about the person. `POST /api/v1/me/close`
  closes the account: it removes profile, contact details, saved homes, notifications and message text, and keeps
  the audit log, payments, payment webhooks as received, tenancies, verification decisions and the Ghana Card
  hash, with the name replaced by a
  reference. It's refused while a tenancy is in progress or the account is under a fraud review.
- **Staff:** admins add, re-role and turn off staff at `/api/v1/admin/staff`. New staff get an SMS, sign in with a phone
  code and must set up an authenticator. Turning someone off signs them out at once. There's always at least one
  active admin.

### Renter growth (roadmap workstream B)

- **Saved searches and alerts:** `GET/POST/DELETE /api/v1/me/searches`, up to 5 per person. `send-alerts` (every 5
  minutes) tells each search about matching homes published after it was saved, once per home. Every alert goes to
  the Afe inbox, and at most 3 a day also go by SMS or WhatsApp.
- **WhatsApp:** `FIND 2 bed East Legon under 5000` returns up to 3 verified homes; `ALERT …` saves the same search
  for an account with that phone number; `STOP` ends alerts; `VIEW AFE-XXXXXX` returns the booking link; `HELP` lists
  the commands. Phone numbers and references still run "Check before you pay".
- **Viewing reminders:** `remind-viewings` messages both people a day before and an hour before a confirmed viewing.
- **Neighbourhood pages:** `GET /api/v1/properties/areas/{slug}` gives rent ranges by size (from Afe's own verified
  listings once there are 3 or more of a size, otherwise from the price survey, and it says which) plus the homes live
  there.

### Trust and safety operations (roadmap workstream C)

- **Re-verification:** `reverify` (daily) warns 30 days before a verification ends and pauses live listings whose
  landlord or home verification has lapsed. Verified homes return to the visit queue only in that 30-day window.
- **Appeals (B12):** `GET /api/v1/me/appealable`, `POST /api/v1/me/appeals`. Each decision can be appealed once. A reviewer
  who didn't make the decision decides at `/api/v1/review/appeals`.
- **Workload:** `GET /api/v1/review/workload` shows queue sizes, oldest items against a 3-day target, median days from
  registering a home to its first live listing, and decisions per reviewer.
- **Visit routes:** `GET /api/v1/review/visit-plan?day=` suggests one-area routes per verifier (rule
  `visits_per_verifier_day`); `POST …/assign` assigns them through the usual visit rules.
- **Label checks:** 5% of reviewer decisions get a second reviewer's check. A disagreement marks the label disputed,
  and it's left out of model training and evaluation.
- **Photos seen elsewhere:** `python -m app.cli import-external-photos crawl.csv` loads photo hashes from a permitted
  crawl (`source,url,phash,dhash`) and flags homes whose photos appear there. Afe keeps only hashes and links.
- **Investigation graph:** `GET /api/v1/review/people/{id}/graph` returns everyone linked to a person and what Afe decided.

### Insights, move-in photos and new areas (roadmap workstreams E, D, H)

- **Targets:** `GET /api/v1/review/targets` shows the build plan's §13 targets now: verified listings live, confirmed
  fraud on verified listings, median days to live, verifier reversals, the share of lets paid outside Afe, cost per
  verification, enquiries that book a viewing, alert subscribers and money held.
- **Leakage:** after a completed viewing the renter can answer "did you rent it, and did you pay through Afe?"
  (`POST /api/v1/viewings/{id}/outcome`). The answer never affects them; it only counts.
- **Cost per verification:** verifiers log travel minutes and fares when they finish a visit. Cost = (visit + travel
  time) × the `verifier_hour_cost_pesewas` rule (a placeholder until Phase 0 measures it) + fares, against the fee.
- **Rent index:** `GET /api/v1/properties/rent-index` gives median rent by area and size from verified homes listed in
  the last 90 days. A figure appears only when at least 3 homes back it.
- **Move-in photo:** the tenant can attach a photo when confirming move-in. It's re-encoded without location data,
  kept private, and shown only to the two parties and reviewers.
- **New areas:** admins create an area (closed), load its price survey, and open it at `/api/v1/admin/areas`. It opens
  only with a boundary, a survey for at least 2 sizes, and an active field verifier.

### Landlord and agent tools (roadmap workstream G)

- **Tenant register:** `/api/v1/rentals`. Landlords record tenants (from Afe or not), rent and schedule. A released
  Afe tenancy joins the register by itself, with the advance recorded as paid through Afe.
- **Rent and receipts:** recording a payment moves the next due date and makes a receipt (PDF). `rent-reminders`
  (daily) tells the landlord 7 days before rent is due and once when it's 3 days overdue. The tenant is told too only if
  they have their own Afe account on that number: a landlord typing in a number isn't consent to message it.
- **Repairs, agreements, renewals:** tenants with an account raise repair requests (with a photo); the landlord updates
  them. Agreements are made from the record's terms and signed in the app by typing your account name; the signature is
  tied to the text by its SHA-256 hash. Renewal offers stay within the advance-rent cap rule.
- **Agents:** `GET /api/v1/rentals/agent-homes` groups an agent's homes by the owner who authorised them.
- **Plans (B19):** Free (1 tenant), Standard (10) and Pro (50). Prices are the `plan_standard_pesewas` and
  `plan_pro_pesewas` rules (placeholders). Plans are free during the launch offer, and landlords who joined during it get
  90 days free after it. Afe tenancies never count towards the limit.
- **Not built:** collecting monthly rent through the payment partner. It waits on decision B7.

### Before launch (roadmap workstream A, finished)

- **Privacy consent:** sign-up requires accepting the privacy notice and terms (`accept_privacy`). The version
  accepted and when are stored on the account (`NOTICE_VERSION` in `accounts/privacy.py`). When the notice changes,
  `privacy_current` turns false and the site asks the person to accept again (`POST /api/v1/me/privacy`).
- **Security headers and errors:** every response gets `nosniff`, `DENY` framing, `no-referrer` and a same-site resource
  policy; API responses are `no-store`. The API reference (`/api/docs`) is only served with `AFE_DEBUG` on. An
  unexpected error returns a reference to quote, never the details, and logs one `unhandled_error` JSON line that a
  CloudWatch alarm counts.
- **Approximate map positions:** listings expose `approx_lat`/`approx_lng`, snapped to a ~550 m grid. The exact address is
  shared only after a viewing is booked.
- **Pilot report:** `pilot-report` (daily) sends admins what's held against the pilot limit, the last day's payments,
  releases and refunds, and what needs a person. It only runs while protected payments are on.
- **Suspending accounts:** an admin can suspend or restore a renter, landlord or agent
  (`POST /api/v1/admin/people/{id}/active`, with a reason). They're signed out, can't sign in, and no money is released to
  them until they're restored. See [docs/runbooks.md](../docs/runbooks.md) for when to use it.

## Production settings

**Database:** SQLite is for local development only. Beta (staging) and production must use PostgreSQL. With
`AFE_DEBUG` off, the app refuses to start unless `AFE_DATABASE_URL` is a `postgresql+psycopg://` URL.

Required: `AFE_SECRET_KEY` (32+ chars), `AFE_PII_HASH_KEY`, `AFE_DATABASE_URL` (PostgreSQL), `AFE_STORAGE_BACKEND=s3` with the
bucket names, `AFE_MEDIA_URL` (CloudFront), `AFE_FRONTEND_URL`, and real providers for KYC, SMS, WhatsApp, email and
payments (decisions B4, B5), and `AFE_MALWARE_SCANNER=app.modules.media.scan.ClamAvScanner` with `AFE_CLAMD_HOST`.
Messages: `AFE_WHATSAPP_PHONE_NUMBER_ID` and `AFE_WHATSAPP_ACCESS_TOKEN`, `AFE_HUBTEL_CLIENT_ID` and
`AFE_HUBTEL_CLIENT_SECRET`, and `AFE_EMAIL_FROM` on a domain verified in SES. The staging setup is in
`infra/terraform/staging/README.md`, and how to deploy in `docs/deploy.md`.

`python -m app.preflight` checks an environment before a deploy: settings load (and `AFE_DEBUG` is off), which provider
secrets are missing, the database answers, and whether migrations are waiting. It exits 1 on a failure.
Staging runs ClamAV as a sidecar in the API task. The app refuses to start with fake providers or local storage outside
debug. See
`.env.example` and `infra/terraform/staging/services.tf`.
