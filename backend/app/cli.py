"""Command-line tasks: python -m app.cli <command>

seed-demo      load demo areas, people and verified homes (development only)
create-user    create a staff or lister account
run-due        expire offers, refund undelivered homes, apply the move-in rule (every few minutes)
reconcile      compare the ledger with the escrow partner's statement (nightly)
publish-outbox mark pending outbox events as published (every minute, until a broker is added)
score-pending  run queued detection models (every minute)
run-agents     run queued agent runs: the reviewer copilot, in shadow (every minute)
detect-graph   rebuild linked-account edges and queue those accounts for scoring (nightly)
train-text     train a new scam-wording model version from reviewer labels
eval-seeded    score the seeded test set of fake and genuine listings; prints recall and misses
weekly-models  the weekly model report, and shadow retraining of the wording model (Mondays)
eval-copilot   run the reviewer copilot on its test cases and check the bar (spends real money: about US$1.50)
copilot-report the reviewer copilot's shadow numbers against reviewers' decisions
retry-messages try failed SMS, WhatsApp and email again (every 5 minutes)
expire-whatsapp WhatsApp messages with no delivery report after their time-to-live go by SMS (every 5 minutes)
send-alerts    tell saved searches about new matching homes (every 5 minutes)
remind-viewings remind both people before a confirmed viewing (every 5 minutes)
reverify       warn before verifications expire; pause listings whose verification lapsed (daily)
rent-reminders rent due in 7 days, or 3 days overdue, for landlords' tenant records (daily)
pilot-report   the founder's daily money report while protected payments are on (daily)
whatsapp-templates  print the WhatsApp templates (--submit creates or updates them at Meta, --bodies prints the wording)
whatsapp-health  tell admins about WhatsApp templates that keep failing (daily)
worker         run the every-minute and every-5-minute jobs above in one long-running process
               (--with-daily also runs the daily jobs at their hour: for servers with no scheduler)
import-external-photos CSV  flag homes whose photos appear on other sites (permitted crawls only)
"""

import argparse
import getpass
import sys

from app.config import get_settings
from app.db import SessionLocal
from app.modules.accounts.models import Role


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-demo", help="load demo data by running the real verification flow")
    seed.add_argument("--force", action="store_true", help="run even when AFE_DEBUG is off")
    user = sub.add_parser("create-user", help="create an account")
    user.add_argument("username")
    user.add_argument("--role", choices=[r.value for r in Role], required=True)
    user.add_argument("--name", default="")
    user.add_argument("--phone")
    code = sub.add_parser("totp", help="print the current authenticator code for an account (debug only)")
    code.add_argument("username", nargs="?", default="reviewer")
    sub.add_parser("run-due", help="scheduled tenancy work: expiries, refunds, move-in releases")
    sub.add_parser("reconcile", help="compare Afe's ledger with the escrow partner's statement")
    sub.add_parser("publish-outbox", help="publish pending outbox events")
    sub.add_parser("score-pending", help="run queued detection models")
    sub.add_parser("run-agents", help="run queued agent runs (the reviewer copilot)")
    sub.add_parser("detect-graph", help="rebuild linked-account edges, then queue those accounts")
    sub.add_parser("train-text", help="train a scam-wording model version from labels")
    seeded = sub.add_parser("eval-seeded", help="score the seeded test set against the models and rules")
    seeded.add_argument("--file", default="", help="another seeded set (defaults to the one in the repo)")
    weekly = sub.add_parser("weekly-models", help="weekly model report, and retraining while in shadow")
    weekly.add_argument("--force", action="store_true", help="run even if today isn't Monday")
    copilot_eval = sub.add_parser("eval-copilot", help="run the reviewer copilot on its test cases")
    copilot_eval.add_argument("--model", default="", help="try another model (default: AFE_AGENT_COPILOT_MODEL)")
    copilot_eval.add_argument("--file", default="", help="another test cases file (defaults to the one in the repo)")
    copilot_report = sub.add_parser("copilot-report", help="the reviewer copilot's shadow numbers")
    copilot_report.add_argument("--days", type=int, default=7, help="how many days back (default 7)")
    sub.add_parser("retry-messages", help="retry failed SMS, WhatsApp and email")
    sub.add_parser("expire-whatsapp", help="send by SMS the WhatsApp messages that never arrived")
    sub.add_parser("send-alerts", help="send new-listing alerts to saved searches")
    sub.add_parser("remind-viewings", help="send viewing reminders")
    sub.add_parser("reverify", help="expiry warnings and pausing lapsed listings")
    sub.add_parser("rent-reminders", help="rent due and overdue reminders")
    sub.add_parser("pilot-report", help="daily money report to admins during the pilot")
    sub.add_parser("whatsapp-health", help="daily check for WhatsApp templates that keep failing")
    templates = sub.add_parser("whatsapp-templates", help="print the WhatsApp message templates for Meta")
    templates.add_argument("--submit", action="store_true", help="submit every template to Meta for review")
    templates.add_argument("--bodies", action="store_true", help="print each template's wording (the test snapshot)")
    wk = sub.add_parser("worker", help="run the frequent jobs on their intervals until stopped")
    wk.add_argument("--with-daily", action="store_true", help="also run the daily jobs (no external scheduler)")
    wk.add_argument("--state-file", default="", help="where --with-daily records the days each job ran")
    ext = sub.add_parser("import-external-photos", help="import photo hashes from a permitted crawl")
    ext.add_argument("csv_path")
    args = parser.parse_args(argv)

    if args.command == "worker":
        import logging

        from app.worker import run_forever

        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        run_forever(with_daily=args.with_daily, state_file=args.state_file)
        return 0

    if args.command == "whatsapp-templates":
        import json

        from app.modules.notifications.providers import DeliveryError
        from app.modules.notifications.whatsapp_templates import registry, sync_all

        if args.bodies:
            print(json.dumps({wa.name: wa.body for wa in registry().values()}, indent=2, sort_keys=True))
            return 0
        if not args.submit:
            print(json.dumps([wa.submission() for wa in registry().values()], indent=2))
            return 0
        try:
            results = sync_all()
        except DeliveryError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(json.dumps(results, indent=2))
        return 1 if any("error" in r for r in results) else 0

    if args.command == "eval-copilot":
        from pathlib import Path

        from app.core.errors import InvalidInput
        from app.modules.agents import copilot
        from app.modules.agents.cases import AGREEMENT_BAR, DEFAULT_PATH, load_cases, run_eval

        try:
            cases = load_cases(Path(args.file) if args.file else DEFAULT_PATH)
        except InvalidInput as exc:
            print(exc, file=sys.stderr)
            return 1
        report = run_eval(cases, lambda packet: copilot.suggest(packet, model=args.model or None))
        for row in report.results:
            verdict = "FALSE APPROVAL" if row["false_approval"] else ("ok" if row["agrees"] else "differs")
            detail = row["error"] or f"right: {row['expected']}; copilot: {row['suggested']}"
            print(f"{row['id']}: {verdict} ({detail})")
        print(f"Agreement {report.agreement:.0%} (bar {AGREEMENT_BAR:.0%}), false approvals {report.false_approvals}, "
              f"reason-code overlap {report.code_overlap:.0%}, errors {report.errors}, cost US${report.cost_usd:.2f}.")
        return 0 if report.passed else 1

    with SessionLocal.begin() as db:
        if args.command == "seed-demo":
            if not get_settings().debug and not args.force:
                print("seed-demo is for development. Set AFE_DEBUG=1 or pass --force.", file=sys.stderr)
                return 1
            from app.seed import DEMO_PASSWORD, seed_demo

            loaded = seed_demo(db)
            if loaded:
                print(
                    f"Loaded {loaded} verified listings. Staff sign in with a password ({DEMO_PASSWORD}) and an "
                    "authenticator code from `python -m app.cli totp <username>`."
                )
            else:
                print("Demo data already loaded.")
        elif args.command == "create-user":
            from app.modules.accounts.service import create_user

            password = getpass.getpass("Password (10+ characters): ")
            created = create_user(db, args.username, password, Role(args.role), args.name, args.phone)
            print(f"Created {created.username} ({created.role}).")
        elif args.command == "totp":
            if not get_settings().debug:
                print("totp is for development only.", file=sys.stderr)
                return 1
            from sqlalchemy import select

            from app.core.totp import now_code
            from app.modules.accounts.models import User

            user = db.scalar(select(User).where(User.username == args.username))
            if user is None or not user.totp_secret:
                print(f"No authenticator set up for {args.username}.", file=sys.stderr)
                return 1
            print(now_code(user.totp_secret))
        elif args.command == "run-due":
            from app.modules.tenancies.service import run_due

            print(run_due(db))
        elif args.command == "reconcile":
            from app.modules.tenancies.service import nightly_reconcile

            problems = nightly_reconcile(db)
            for p in problems:
                print(f"{p['tenancy']} {p['kind']} {p['partner_ref']}: {p['problem']} (ours {p['ours']}, theirs {p['theirs']})")
            print(f"{len(problems)} difference(s).")
            return 1 if problems else 0
        elif args.command == "publish-outbox":
            from app.modules.tenancies.service import publish_outbox

            print(f"Published {publish_outbox(db)} event(s).")
        elif args.command == "score-pending":
            from app.modules.detection.service import process_pending

            print(process_pending(db))
        elif args.command == "copilot-report":
            from app.modules.agents.service import numbers

            print(numbers(db, days=args.days))
        elif args.command == "run-agents":
            from app.modules.agents.service import run_pending

            print(run_pending(db))
        elif args.command == "detect-graph":
            from app.modules.detection.service import process_pending, run_graph

            print(run_graph(db), process_pending(db, limit=5000))
        elif args.command == "train-text":
            from app.core.errors import RuleViolation
            from app.modules.detection.service import train_text

            try:
                version = train_text(db, None)
            except RuleViolation as exc:
                print(exc, file=sys.stderr)
                return 1
            print(f"Trained {version.version} on {version.trained_on} examples ({version.notes}).")
        elif args.command == "eval-seeded":
            import json
            from pathlib import Path

            from app.core.errors import InvalidInput
            from app.modules.detection.seeded import DEFAULT_PATH, evaluate_seeded, load_cases

            try:
                cases = load_cases(Path(args.file) if args.file else DEFAULT_PATH)
            except InvalidInput as exc:
                print(exc, file=sys.stderr)
                return 1
            print(json.dumps([r.as_dict() for r in evaluate_seeded(db, cases)], indent=2))
        elif args.command == "weekly-models":
            from app.modules.detection.reports import weekly_models

            print(weekly_models(db, force=args.force))
        elif args.command == "retry-messages":
            from app.modules.notifications.service import retry_failed

            print(retry_failed(db))
        elif args.command == "expire-whatsapp":
            from app.modules.notifications.service import expire_undelivered

            print(expire_undelivered(db))
        elif args.command == "send-alerts":
            from app.modules.alerts.service import send_alerts

            print(send_alerts(db))
        elif args.command == "remind-viewings":
            from app.modules.enquiries.service import send_viewing_reminders

            print(send_viewing_reminders(db))
        elif args.command == "reverify":
            from app.modules.ops.service import reverify

            print(reverify(db))
        elif args.command == "rent-reminders":
            from app.modules.rentals.service import send_rent_reminders

            print(send_rent_reminders(db))
        elif args.command == "pilot-report":
            from app.modules.tenancies.service import send_pilot_report

            print(send_pilot_report(db) or "Protected payments are off: no report.")
        elif args.command == "whatsapp-health":
            from app.modules.notifications.alarms import whatsapp_health

            print(whatsapp_health(db))
        elif args.command == "import-external-photos":
            from app.modules.ops.service import import_external_photos

            print(import_external_photos(db, args.csv_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
