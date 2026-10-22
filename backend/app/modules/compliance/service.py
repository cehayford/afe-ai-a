"""Versioned rules for money and tenancies. Code reads rules through `rule()`; a rule with
no approved row uses the default below, so the system works before anyone edits a rule.
Every default names where it comes from, and the ones waiting on counsel say so."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput, NotAllowed, RuleViolation
from app.db import utcnow
from app.modules.audit.log import record

from .models import ComplianceRule, RuleStatus


@dataclass(frozen=True)
class RuleDef:
    default: object
    kind: type
    label: str
    source: str
    choices: tuple = ()
    maximum: int | None = None


RULES: dict[str, RuleDef] = {
    "advance_cap_months_long": RuleDef(
        6, int, "Most months of rent in advance, tenancies over 6 months",
        "Rent Act, 1963 (Act 220). How Afe enforces it is decision B10 (counsel).",
    ),
    "advance_cap_months_short": RuleDef(
        2, int, "Most months of rent in advance, tenancies of 6 months or less",
        "Statement §6.3. Confirm with counsel (B10).",
    ),
    "max_deposit_months": RuleDef(2, int, "Most months of deposit", "Afe policy, pending counsel (B10)."),
    "protection_fee_bps": RuleDef(
        350, int, "Protection fee, in basis points of the amount held (350 = 3.5%)",
        "Statement §12.1 working figure; decision B9 sets it from pilot leakage.",
    ),
    "protection_fee_payer": RuleDef(
        "tenant", str, "Who pays the protection fee: tenant, landlord or split", "Decision B9.",
        choices=("tenant", "landlord", "split"),
    ),
    "refund_gateway_fee_bps": RuleDef(
        195, int, "Gateway fee kept from a refund, in basis points of the amount held",
        "Statement §6.3 (refund minus gateway fee). Match the partner's contract (B4).",
    ),
    "offer_valid_hours": RuleDef(72, int, "Hours a tenancy offer stays open", "Afe policy."),
    "move_in_grace_days": RuleDef(
        3, int, "Days after the move-in date before an undelivered home is refunded", "Build plan §6."
    ),
    "auto_release_days": RuleDef(
        7, int, "Days after the move-in date before money is released on the landlord's evidence alone",
        "Decision B8 (fallback when a tenant never confirms). Only with landlord evidence and no dispute.",
    ),
    "pilot_max_tenancy_pesewas": RuleDef(
        6_000_000, int, "Pilot limit: most one tenancy can hold, in pesewas", "Build plan §6 pilot limits (W24-27)."
    ),
    "pilot_max_held_pesewas": RuleDef(
        60_000_000, int, "Pilot limit: most Afe holds in total at once, in pesewas", "Build plan §6 pilot limits."
    ),
    "pilot_manual_release": RuleDef(
        True, bool, "Pilot: a reviewer approves every release", "Build plan §6 pilot limits."
    ),
    "payee_cooling_off_hours": RuleDef(
        72, int, "Hours before a changed payout account can receive money", "Build plan §6 (account-takeover defence)."
    ),
    "featured_fee_pesewas": RuleDef(15_000, int, "Price of featuring a listing, in pesewas", "Statement §12.1; placeholder."),
    "featured_days": RuleDef(14, int, "Days a featured listing stays featured", "Afe policy."),
    "plan_standard_pesewas": RuleDef(
        5_000, int, "Landlord tools, Standard plan, per month (pesewas)", "Placeholder until decision B19."
    ),
    "plan_pro_pesewas": RuleDef(15_000, int, "Landlord tools, Pro plan, per month (pesewas)", "Placeholder until decision B19."),
    "verifier_hour_cost_pesewas": RuleDef(
        2_500, int, "Cost of one verifier hour, in pesewas, for the cost of a verification",
        "Placeholder until Phase 0 measures pay and overheads (build plan §5).",
    ),
    "visits_per_verifier_day": RuleDef(
        3, int, "Visits one verifier is planned for in a day", "Build plan §5: 2-3 visits a day in a compact area.",
        maximum=12,
    ),
    "qa_recheck_percent": RuleDef(
        15, int, "Share of approved homes a second verifier re-checks unannounced, in percent",
        "Build plan §5: controls on our own verifiers.", maximum=100,
    ),
    # Launch offer: every Afe charge is free for the first 8 months of Year 1 (W1 = 5 Oct 2026).
    "free_period_until": RuleDef(
        "2027-06-05", date, "Launch offer: Afe's charges are free before this date (YYYY-MM-DD)",
        "Founder decision, 24 Sep 2026: free for the first 8 months of Year 1 (5 Oct 2026 to 4 Jun 2027).",
    ),
    # Phase 3: detection models. Every model starts in shadow (build plan §3, §7). Moving one to
    # canary or active is a rule change: it needs a passing evaluation and a second reviewer.
    "model_canary_percent": RuleDef(
        10, int, "Canary: share of cases a canary model acts on, in percent", "Build plan §7 (10% canary).", maximum=100
    ),
    "model_min_labels": RuleDef(
        30, int, "Labelled cases a model needs before it can leave shadow", "Build plan §7 promotion rule."
    ),
}

MODEL_MODES = ("off", "shadow", "canary", "active")
_DETECTOR_RULES = {
    "scam_text": ("Scam wording in listings and messages", 80, "shadow"),
    "scam_text_llm": ("Scam wording by Claude, on redacted text", 80, "off"),
    "price": ("Price far below the area", 85, "shadow"),
    "photos": ("Photos matching another home", 80, "shadow"),
    "documents": ("Signs a document was edited", 70, "shadow"),
    "accounts": ("Accounts linked to known fraud", 70, "shadow"),
}
for _name, (_label, _threshold, _mode) in _DETECTOR_RULES.items():
    RULES[f"model_{_name}_mode"] = RuleDef(
        _mode, str, f"Model mode: {_label}",
        "Build plan §7: shadow first; off, shadow, canary or active."
        + (" Off until counsel clears sending redacted text abroad (B11)." if _mode == "off" else ""),
        choices=MODEL_MODES,
    )
    RULES[f"model_{_name}_threshold"] = RuleDef(
        _threshold, int, f"Model threshold: {_label} (score out of 100 that raises a flag)", "Build plan §7.",
        maximum=100,
    )

RULES["agent_copilot_level"] = RuleDef(
    "off", str, "Reviewer copilot: off, or shadow (it runs and is measured; nobody sees what it suggests)",
    "Trust Engine, Stage 1. Off until counsel clears sending masked case facts to a model abroad (B11).",
    choices=("off", "shadow"),
)
RULES["agent_copilot_daily_tokens"] = RuleDef(
    200_000, int, "Reviewer copilot: most tokens a day, in and out (about 30 cases)",
    "Trust Engine: a daily token budget for every agent.",
)


def rule(db: Session, key: str, country: str = "GH"):
    row = active_row(db, key, country)
    return row.value["v"] if row else RULES[key].default


def free_until(db: Session) -> date:
    """The day Afe's charges start. Before it, verification, protection and featuring are free."""
    return date.fromisoformat(rule(db, "free_period_until"))


def charges_free(db: Session, on: date | None = None) -> bool:
    return (on or utcnow().date()) < free_until(db)


def rule_versions(db: Session, keys: list[str], country: str = "GH") -> dict[str, int]:
    """Which version of each rule applied (0 = the built-in default). Stored on tenancies."""
    return {k: (row.version if (row := active_row(db, k, country)) else 0) for k in keys}


def active_row(db: Session, key: str, country: str = "GH") -> ComplianceRule | None:
    return db.scalar(
        select(ComplianceRule).where(
            ComplianceRule.country == country, ComplianceRule.key == key, ComplianceRule.status == RuleStatus.ACTIVE
        )
    )


def propose(db: Session, reviewer, key: str, value, source: str, country: str = "GH") -> ComplianceRule:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can propose rule changes.")
    definition = RULES.get(key)
    if definition is None:
        raise InvalidInput(f"Unknown rule: {key}")
    if definition.kind is bool and not isinstance(value, bool):
        raise InvalidInput("This rule is yes or no.")
    if definition.kind is int and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise InvalidInput("This rule needs a whole number, 0 or more.")
    if definition.maximum is not None and value > definition.maximum:
        raise InvalidInput(f"This rule can be at most {definition.maximum}.")
    if definition.kind is str and not isinstance(value, str):
        raise InvalidInput("This rule needs text.")
    if definition.kind is date:
        try:
            date.fromisoformat(str(value))
        except ValueError as exc:
            raise InvalidInput("This rule needs a date like 2027-06-05.") from exc
    if definition.choices and value not in definition.choices:
        raise InvalidInput(f"Choose one of: {', '.join(definition.choices)}.")
    if key.startswith("model_") and key.endswith("_mode") and value in ("canary", "active"):
        # A model leaves shadow only when it beats the rules on labelled cases (build plan §7).
        from app.modules.detection.service import evaluate

        report = evaluate(db, key.removeprefix("model_").removesuffix("_mode"))
        if not report.promotable:
            raise RuleViolation(f"This model can't leave shadow yet: {report.reason}")
    if len((source or "").strip()) < 5:
        raise InvalidInput("Say which law, decision or policy this comes from.")
    latest = db.scalar(
        select(func.max(ComplianceRule.version)).where(ComplianceRule.country == country, ComplianceRule.key == key)
    )
    row = ComplianceRule(country=country, key=key, value={"v": value}, version=(latest or 0) + 1,
                         source=source.strip()[:300], proposed_by_id=reviewer.id)
    db.add(row)
    db.flush()
    record(db, reviewer, "compliance.proposed", row, key=key, value=value)
    return row


def approve(db: Session, row: ComplianceRule, reviewer) -> ComplianceRule:
    """The second of two named approvers (Statement §7.1)."""
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can approve rule changes.")
    if row.status != RuleStatus.PROPOSED:
        raise RuleViolation("Only proposed rules can be approved.")
    if row.proposed_by_id == reviewer.id:
        raise RuleViolation("A different reviewer must approve this change.")
    current = active_row(db, row.key, row.country)
    if current:
        current.status = RuleStatus.SUPERSEDED
        db.flush()
    row.status = RuleStatus.ACTIVE
    row.approved_by_id = reviewer.id
    row.approved_at = utcnow()
    db.flush()
    record(db, reviewer, "compliance.approved", row, key=row.key, value=row.value["v"], version=row.version)
    return row


def reject(db: Session, row: ComplianceRule, reviewer) -> ComplianceRule:
    if not reviewer.can_review:
        raise NotAllowed("Only reviewers can reject rule changes.")
    if row.status != RuleStatus.PROPOSED:
        raise RuleViolation("Only proposed rules can be rejected.")
    row.status = RuleStatus.REJECTED
    row.approved_by_id = reviewer.id
    row.approved_at = utcnow()
    db.flush()
    record(db, reviewer, "compliance.rejected", row, key=row.key)
    return row


def rollback(db: Session, key: str, reviewer, country: str = "GH") -> ComplianceRule:
    """One-click rollback (Statement §7.1) is itself a proposal: it proposes the previous
    version's value, and still needs a second reviewer to approve."""
    previous = db.scalar(
        select(ComplianceRule)
        .where(ComplianceRule.country == country, ComplianceRule.key == key, ComplianceRule.status == RuleStatus.SUPERSEDED)
        .order_by(ComplianceRule.version.desc())
    )
    if previous is None:
        if active_row(db, key, country) is None:
            raise RuleViolation("There is no earlier version to go back to.")
        return propose(db, reviewer, key, RULES[key].default, "Rollback to the built-in default", country)
    return propose(db, reviewer, key, previous.value["v"], f"Rollback to version {previous.version}", country)


def all_rules(db: Session, country: str = "GH") -> list[dict]:
    out = []
    for key, definition in RULES.items():
        row = active_row(db, key, country)
        pending = list(db.scalars(
            select(ComplianceRule).where(ComplianceRule.country == country, ComplianceRule.key == key,
                                         ComplianceRule.status == RuleStatus.PROPOSED)
        ))
        out.append({
            "key": key, "label": definition.label, "value": row.value["v"] if row else definition.default,
            "version": row.version if row else 0, "source": row.source if row else definition.source,
            "pending": pending,
        })
    return out
