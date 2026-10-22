# Afe incident runbooks

What to do when something goes wrong in production. Each runbook says how you'll notice, what to do in the
first 15 minutes, how to fix it, and who to tell. Commands run as a one-off ECS task with the **jobs** task
definition (see `infra/terraform/staging/README.md`), e.g. `python -m app.cli reconcile`.

Rules that apply to every incident:

- **Money first.** If anything could move money wrongly, turn protected payments off before investigating:
  set `AFE_PROTECTED_PAYMENTS_ENABLED=0` and redeploy. Offers, accepts and payments stop; money already held stays
  with the partner.
- **Write it down.** Open an incident note with times, what you saw and what you did. The audit log records staff
  actions on its own, but not your reasoning.
- **Never edit the ledger or audit tables by hand.** They are append-only by design. Corrections are new entries
  made through the app.

---

## Reconciliation difference

**You'll notice:** the `reconcile` job fails (email from the alerts topic), or the Money page shows a difference.

1. Open **Review → Money**. Each difference names the tenancy, the partner reference and what doesn't match.
2. "In Afe's ledger, not in the partner's statement": the partner may be late. Wait for the next statement, then re-run
   `reconcile`. If it's still there after a day, call the partner with the reference.
3. "In the partner's statement, not in Afe's ledger": a confirmation never reached Afe. Check the load balancer rule
   includes `/api/v1/tenancies/webhook`, then ask the partner to resend it. Confirmations are idempotent, so a resend is
   safe.
4. "Amounts differ": turn protected payments off, and escalate to the founder and the partner the same day.

**Tell:** founder (same day); the partner, for anything older than a day.

## Partner confirmations failing

**You'll notice:** tenants say they paid but the tenancy still shows "Waiting for payment"; `webhook rejected` in API logs.

1. Check the API logs for `/api/v1/tenancies/webhook` responses. 422 means the signature check failed: the partner's
   signing secret was changed or is wrong in Secrets Manager.
2. Fix the secret, redeploy, and ask the partner to resend confirmations since the first failure.
3. Tell affected tenants their payment is safe with the partner and will show shortly.

## Release stuck or failed

**You'll notice:** a `money.release_failed` flag, or a tenancy stuck in "Paying the landlord".

1. A failed release returns the tenancy to "Release being checked". Look at the flag's explanation for the partner's reason.
2. Usually the landlord's payout account was closed or the name check failed. Ask the landlord to update their payout
   account. The 72-hour wait applies, and there is no way round it: it protects landlords from account takeover.
3. After the wait, approve the release again on the Money page.

## Refund failed

**You'll notice:** a `money.refund_failed` flag.

1. Call the partner with the tenancy reference; the money is still with them.
2. Tell the tenant what happened and when to expect the refund. Don't promise a date the partner hasn't given.

## Suspected payout-account takeover

**You'll notice:** a landlord reports a payout account change they didn't make (they get an SMS on every change).

1. An admin opens the landlord on **Review → the person's page** and uses **Suspend account**, giving the reason. That
   signs them out everywhere, stops them signing in, and stops any money being released to them. Releases wait
   for a reviewer instead.
2. The changed payout account can't receive money for 72 hours in any case. Suspending covers the time after that.
3. Confirm who the landlord is in person, have them set their real payout account (the 72-hour wait applies again), then
   **Restore account** and approve the waiting releases on the Money page.

**Tell:** the landlord; the founder; if personal data was exposed, see "Personal data breach".

## Malware scanner down

**You'll notice:** landlords can't upload documents ("We couldn't check this file for viruses"); the ClamAV container
restarts in the API task.

1. Uploads are refused, not let through, so nothing unsafe gets in. This is not an emergency, but it blocks verification.
2. Check the `clamav` log stream. On first start, loading signatures takes a few minutes. If it's short of memory, the
   task needs its 4 GB.
3. Redeploy the API service if the container keeps failing.

## SMS or WhatsApp provider down

**You'll notice:** sign-in codes don't arrive; `retry-messages` keeps finding failures.

1. Other messages are retried automatically for a day. Sign-in codes are not; people ask for a new code.
2. Check the provider's status page, then the credentials in Secrets Manager.
3. If SMS is down for more than an hour, post a notice on WhatsApp and the website.

## Database restore

**You'll notice:** data loss or corruption, or a failed migration.

1. Stop writes: scale the API and jobs to zero.
2. Restore to a new instance with point-in-time recovery to just before the problem (RDS console or CLI). Recovery
   target: back within 4 hours, losing at most 1 hour of data.
3. Point `AFE_DATABASE_URL` at the new instance, run `alembic upgrade head`, scale back up, then run `reconcile` to
   check the ledger against the partner.
4. Practise this: a restore drill before each launch (build plan §8).

## A deploy went wrong

**You'll notice:** new tasks keep restarting and ECS rolls back by itself, alarms after a deploy, or errors that
started with the release.

1. If the old tasks are still serving (ECS waits for new tasks to pass health checks before it stops old ones),
   nothing is down: read the new tasks' logs (`/afe/staging/api`, stream `api/...` or `worker/...`) for the error.
2. Settings or secrets: run `../../scripts/run-job.sh python -m app.preflight` from `infra/terraform/staging/`. It
   names what's wrong without printing secret values.
3. To go back: put the previous `images.auto.tfvars` back and `terraform apply` (`docs/deploy.md`, Rolling back).
   Read the release's migrations first: roll back only if every one just added tables or columns.
4. A migration failed half-way: PostgreSQL ran it in a transaction, so nothing changed. Fix the migration in a new
   release; never edit the `alembic_version` table by hand.

**Tell:** the founder, if the site was down or money flows were affected.

## Scam wave

**You'll notice:** several scam reports about the same number or listing in a day; open flags climbing.

1. On **Review → Reports**, uphold the reports that hold up. That flags the account and blocks its listings from going
   live.
2. Open the person's page and look at the linked-accounts graph for others in the same ring.
3. If fake listings mention Afe outside Afe (Facebook, WhatsApp groups), post a warning with "Check before you pay".

## Personal data breach

**You'll notice:** anything suggesting personal data was seen by someone who shouldn't have seen it.

1. Contain it first: revoke keys, turn off accounts, close the hole.
2. Record what data, whose, when and how. The audit log shows who opened private documents.
3. Tell counsel the same day. Under the Data Protection Act, 2012 (Act 843), the Data Protection Commission and the
   people affected must be told. Counsel decides the wording and the timing.

## Verifier misconduct

**You'll notice:** a failed quality re-check (`qa.verifier_reversal` flag), or a report about a verifier.

1. Turn the verifier's account off on **Review → Staff**. That signs them out everywhere at once.
2. List every home they passed (Verifier quality page) and schedule re-checks by other verifiers.
3. Revoke verifications that don't hold up. Their listings pause, and the landlords are told why.
