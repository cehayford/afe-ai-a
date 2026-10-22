# Afe

Afe helps renters in Accra find homes without getting scammed, by verifying every landlord and property and holding
rent payments safely until move-in. AI strengthens detection on top of verified data; it is not a substitute for
verification.

The build follows [docs/Afe_Build_Plan.html](docs/Afe_Build_Plan.html). The software for its three phases is
written and tested:

- **Phase 1, verified listings (built).** Landlord ID checks, ownership documents, field visits,
  the review desk, listings, enquiries and viewings. Renters can also look up a number or listing reference on the
  web and on WhatsApp.
- **Phase 2, protected payments (built, switched off).** It stays off until counsel's opinion on holding rent and a
  licensed partner are in place (decision B7).
- **Phase 3, detection (built, in shadow).** The models score in shadow, and none of them can act on its own.

What's left is mostly outside the code: partners, counsel, Meta business verification, and setting up AWS.

## How it fits together

```
browser ──► frontend (SvelteKit, Node server) ──► backend API (FastAPI) ──► PostgreSQL
              holds sign-in tokens in                /api/v1 only            S3 (photos, KYC docs)
              httpOnly cookies                          ▲                    SMS / WhatsApp / email / payments
phone app (Flutter, Android + iOS) ─────────────────────┘ its own hostname, bearer tokens
worker (python -m app.cli worker) ── scheduled jobs: messages, alerts, reminders, scoring, the reviewer copilot
```

- **[backend/](backend/)** is API-only: 160+ endpoints under `/api/v1` with a `{ data, meta, error }` envelope and
  bearer tokens. All trust rules live here, in one module per area under `app/modules/` (accounts, identity,
  verification, listings, tenancies, detection, agents, notifications and so on). `python -m app.cli` lists the
  scheduled and admin commands.
- **[frontend/](frontend/)** is a separate app. Its server calls the API with the signed-in person's token; the
  browser never sees a token. Renters, landlords, reviewers and field verifiers each have their own pages.
- **[mobile/](mobile/)** is the Flutter app for Android and iOS: renters, landlords and agents, and field
  verifiers (with an offline photo queue). It calls the API directly on its own hostname.
- **[infra/terraform/staging/](infra/terraform/staging/)** describes staging on AWS (ECS Fargate, RDS, S3,
  CloudFront, backups, and the CI role that pushes images). It is validated but not yet applied.
- **[deploy/free-server/](deploy/free-server/)** runs the whole thing on one small server for development.

## Run it locally

The quickest way: `bash .claude/skills/run-afe/driver.sh up`. It creates a demo database in a temporary folder and
starts the API on :8000 and the website on :5173; `driver.sh down` stops them. It is tested on Windows (Git Bash);
see [.claude/skills/run-afe/SKILL.md](.claude/skills/run-afe/SKILL.md).

By hand, without Docker (SQLite and local files):

```bash
# terminal 1: API on :8000
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
export AFE_DEBUG=1
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.cli seed-demo
.venv/Scripts/uvicorn app.main:app --reload

# terminal 2: web on :5173
cd frontend
npm ci
npm run dev

# terminal 3 (optional): the scheduled jobs (message retries, saved-search alerts, viewing reminders, scoring)
cd backend
AFE_DEBUG=1 .venv/Scripts/python -m app.cli worker
```

With Docker (PostgreSQL and S3 via MinIO, like production): `docker compose up --build`, then
`docker compose run --rm api python -m app.cli seed-demo`. Web on :3000.

In development every provider is a stand-in. SMS and WhatsApp messages, including sign-in codes, are printed in the
API's console. The ID check passes any Ghana Card number except one ending in `-0`. Payment checkouts open a test
page with a Pay button.

### Demo accounts

Every demo account has the password `afe-demo-password`. Landlords, agents and staff then enter an authenticator
code: `python -m app.cli totp <username>` prints the current one (development only).

| Who | Username | Phone (sign in by code) |
|---|---|---|
| Renter | `yaa` | `0240000009` |
| Landlord | `ama` | `0244123456` |
| Agent | `kofi` | `0501234567` |
| Reviewer (admin) | `reviewer` | staff sign in with the password |
| Field verifiers | `verifier`, `verifier2` | staff sign in with the password |

Renters, landlords and agents normally sign in with a code sent to their phone. Staff use "Sign in with a password"
on the sign-in page.

## Switched off until a decision

| What | Switch | Turned on when |
|---|---|---|
| Protected payments (Phase 2) | `AFE_PROTECTED_PAYMENTS_ENABLED`, off | Counsel's opinion and a licensed partner (B7) |
| Real ID checks | No real provider yet; `AFE_ALLOW_FAKE_PROVIDERS` lets staging use the fake | The KYC partner is chosen (B5) |
| Detection models | Each model's mode, shadow | It beats the rules on labelled cases, and a second reviewer approves (Review desk → Models, then Rules) |
| Reviewer copilot (AI suggestions on home cases) | The `agent_copilot_level` rule, off; needs `AFE_ANTHROPIC_API_KEY` | Counsel clears sending masked case facts abroad (B11), then two reviewers set it to shadow |

The real senders exist: WhatsApp Cloud API, Hubtel SMS, and SES, Resend or SMTP email. So do Paystack for fees and
ClamAV for scanning uploads. Each provider is set by a dotted path in the settings; fakes are refused outside
development unless `AFE_ALLOW_FAKE_PROVIDERS` is on.

## Checks

GitLab CI ([.gitlab-ci.yml](.gitlab-ci.yml)) runs each job when its part of the repo changes:

- **Backend.** Lint (`ruff check`), migrations up, and a check that the models match them, then the tests, on SQLite
  **and** PostgreSQL. PostgreSQL also runs the migrations back down.
- **Frontend.** Type check, unit tests and build.
- **Terraform.** Format and validate.
- **Every push.** GitLab SAST and secret detection.
- **Images.** On `staging` and `main`, once `PUSH_IMAGES` is set, CI builds the API and web images and pushes them
  to ECR (see docs/deploy.md).

Locally:

```bash
cd backend && .venv/Scripts/ruff check . && .venv/Scripts/python -m pytest -p no:warnings
cd frontend && npm run check && npx vitest run && npm run build
bash .claude/skills/run-afe/driver.sh landing   # the landing page in a real browser (needs driver.sh up)
bash .claude/skills/run-afe/driver.sh pages     # every linked page at desktop and phone width
bash .claude/skills/run-afe/driver.sh a11y      # the accessibility audit (WCAG 2.1 AA), every role, light and dark
```

## Deploying

Staging isn't on AWS yet. [docs/deploy.md](docs/deploy.md) covers:

- the first setup;
- every release: images, `python -m app.preflight`, migrations, then the services;
- rolling back, and how to write migrations so that rolling back stays safe.

[docs/runbooks.md](docs/runbooks.md) says what to do when something goes wrong in production.

## Documents

- **Scope and order:** the build plan, [docs/Afe_Build_Plan.html](docs/Afe_Build_Plan.html), is the source of truth.
  The roadmap ([docs/Afe_Roadmap.html](docs/Afe_Roadmap.html)) covers the work after Phase 3.
- **WhatsApp and payments go-live:** [docs/Afe_WhatsApp_Payments.html](docs/Afe_WhatsApp_Payments.html).
- **Hosting and cost:** [docs/Deployment_Level_AWS.md](docs/Deployment_Level_AWS.md) covers where Afe runs at each
  stage, what it costs, and the free development server.
- **Accessibility:** [docs/accessibility.md](docs/accessibility.md) covers what the audit checks, what has been
  fixed, and the screen-reader checks a person must do before the beta gate.
- **Recent feature designs and plans:** [docs/superpowers/](docs/superpowers/) (WhatsApp go-live, go-live
  hardening, AI foundations, the reviewer copilot).
- **Background:** Project Statement v3.3, the Stack Amendment, the unit economics model and the validation surveys,
  all in [docs/](docs/).
