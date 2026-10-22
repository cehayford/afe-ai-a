# Afe staging on AWS

Terraform for the staging environment: the web app and API on ECS Fargate behind one load balancer,
PostgreSQL 16 on RDS (Multi-AZ, point-in-time recovery, cross-region backup copies), S3 buckets split
by sensitivity with KMS on the private one, CloudFront for listing photos, and scheduled jobs.

| File | What it holds |
|---|---|
| `network.tf` | VPC, subnets and security groups |
| `database.tf` | RDS PostgreSQL and AWS Backup |
| `storage.tf` | S3 buckets, KMS and CloudFront |
| `services.tf` | ECS cluster, API (with the ClamAV sidecar) and web services, load balancer, secrets, IAM |
| `operations.tf` | Scheduled jobs, alarms, SES email |
| `ci.tf` | GitLab CI's role: push the two images to ECR, nothing else (OIDC, no stored keys) |

The order of a first setup and of every release (state bucket, CI role, images, apply, secrets, `preflight`,
migrations, rollback) is in `docs/deploy.md`.

## Before the first apply

1. Choose the region (decision B11) and set `region`, `web_domain`, `certificate_arn`, `api_image` and
   `web_image` in a `terraform.tfvars` file (not committed).
2. Set `alert_email` for alarms (confirm the subscription email AWS sends), `email_domain` for
   outgoing email, and `whatsapp_phone_number_id` from Meta.
3. Until the KYC partner is chosen (B5), the API only starts with `allow_fake_providers = true`.
   Turn it off as soon as the real KYC adapter is deployed. Never set it in production.

## After the first apply

Fill in the secrets it created (empty) in Secrets Manager, never in code:

| Secret | From |
|---|---|
| `AFE_SECRET_KEY`, `AFE_PII_HASH_KEY` | Random, 48+ characters each |
| `AFE_DATABASE_URL` | `postgresql+psycopg://…` built from the RDS master secret (output) |
| `AFE_PAYSTACK_SECRET_KEY` | Paystack dashboard |
| `AFE_WHATSAPP_ACCESS_TOKEN`, `AFE_WHATSAPP_APP_SECRET`, `AFE_WHATSAPP_VERIFY_TOKEN` | Meta app (system user token) |
| `AFE_HUBTEL_CLIENT_ID`, `AFE_HUBTEL_CLIENT_SECRET` | Hubtel account; register the sender ID "Afe" |

Then:

- Add the SES DNS records from the `ses_dns_records` output at the domain's DNS host, and ask AWS to
  move SES out of its sandbox so it can email anyone.
- Set `whatsapp_business_account_id`, then submit the WhatsApp templates once: `python -m app.cli
  whatsapp-templates --submit` (a jobs task, or any machine with the access token). Each event Afe sends on
  WhatsApp has its own template; the command prints each one's status, and Meta reviews them within a day or two.
  Run it again after changing a message's wording: it edits only the templates that changed (Meta allows one
  edit a day to an approved template). Fix and rerun any it reports as rejected or filed under a different
  category. Subscribe the webhook to the `messages`,
  `phone_number_quality_update`, `message_template_status_update` and `template_category_update` fields: a quality
  warning (flagged, or a lower messaging limit) goes to admins at once; a rejected, paused or recategorised template
  does too.
- Run the database migrations once: an ECS task with the jobs task definition and the command
  `alembic upgrade head`.

## Scheduled jobs

The frequent jobs run in one always-on **worker** service (`python -m app.cli worker`, 0.25 vCPU,
0.5 GB). Starting a task per run would mean about 120,000 task starts a month, each downloading the image.
The daily jobs are started by EventBridge Scheduler as `python -m app.cli <job>` in a small task (no ClamAV):

| Job | When | Runs in | Does |
|---|---|---|---|
| `run-due` | every 5 min | worker | Expires offers, refunds undelivered homes, applies the move-in rule |
| `retry-messages` | every 5 min | worker | Retries failed SMS, WhatsApp and email (never sign-in codes) |
| `expire-whatsapp` | every 5 min | worker | WhatsApp messages with no delivery report after their time-to-live go by SMS |
| `send-alerts` | every 5 min | worker | Tells saved searches about new matching homes |
| `remind-viewings` | every 5 min | worker | Reminds both people a day and an hour before a viewing |
| `score-pending` | every minute | worker | Runs queued detection models |
| `publish-outbox` | every minute | worker | Publishes money events |
| `reconcile` | 02:00 | scheduler | Ledger against the partner's statement; admins are told about any difference, and the job exits with an error |
| `detect-graph` | 03:00 | scheduler | Rebuilds linked-account edges |
| `reverify` | 04:00 | scheduler | Warns 30 days before a verification ends; pauses listings whose verification lapsed |
| `rent-reminders` | 07:00 | scheduler | Landlord tools: rent due in 7 days, or 3 days overdue |
| `pilot-report` | 08:00 | scheduler | Money report to admins while protected payments are on |
| `weekly-models` | Mondays 05:00 | scheduler | Weekly model report; retrains the wording model while it's in shadow |
| `whatsapp-health` | 06:00 | scheduler | Tells admins about WhatsApp templates with 3 or more failures (a fifth or more of the day's), or no delivery reports |

A scheduled job that exits with an error emails the alert address. A worker job that fails 3 times in
15 minutes raises the `worker-job-failed` alarm; the worker keeps running the others.

## Alarms

Server errors (more than 10 in 5 minutes), slow pages (p95 over 2 s for 15 minutes), no running API,
web or worker tasks, database storage under 5 GB, and any failed scheduled or worker job. They all go to the
`alerts` SNS topic.
