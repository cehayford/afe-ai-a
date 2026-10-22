"""The seeded test set (Trust Engine, Stage 0): fake listings the team writes, mixed with genuine
ones, scored the way the detectors score real listings. Fraud on verified homes should be near
zero, so real labels alone can't show recall; this set can. Cases are scored in memory and never
written as listings, so the set can't appear on the site or leak into training."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput
from app.modules.areas.models import ServiceArea
from app.modules.risk.rules import price_anomaly, scam_language

from .detectors import REGISTRY, reference_rent, score_rent
from .models import ModelVersion
from .service import Tally, mode, threshold
from .text import get_text_model

DEFAULT_PATH = Path(__file__).with_name("seeded_cases.json")
KINDS = ("fraud", "genuine")
REQUIRED = {"id", "kind", "title", "description", "rent_ghs", "bedrooms", "area"}
FIELDS = REQUIRED | {"tactic"}


@dataclass(frozen=True)
class SeededCase:
    id: str
    kind: str
    title: str
    description: str
    rent_ghs: float
    bedrooms: int
    area: str
    tactic: str = ""

    @property
    def fraud(self) -> bool:
        return self.kind == "fraud"

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}"


def load_cases(path: Path = DEFAULT_PATH) -> list[SeededCase]:
    """Read and check the file. Every mistake names the case, so the team can fix it."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidInput(f"Can't read the seeded set at {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise InvalidInput("The seeded set must be a JSON list of cases.")
    cases, seen = [], set()
    for n, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise InvalidInput(f"case {n}: each case must be an object.")
        name = item.get("id", f"case {n}")
        missing, unknown = REQUIRED - set(item), set(item) - FIELDS
        if missing:
            raise InvalidInput(f"{name}: missing {', '.join(sorted(missing))}.")
        if unknown:
            raise InvalidInput(f"{name}: unknown field {', '.join(sorted(unknown))}.")
        for key in ("id", "title", "description", "area", "tactic"):
            if key in item and not isinstance(item[key], str):
                raise InvalidInput(f"{name}: {key} must be text.")
        if item["id"] in seen:
            raise InvalidInput(f"{name}: this id is used twice.")
        if item["kind"] not in KINDS:
            raise InvalidInput(f"{name}: kind must be fraud or genuine.")
        rent = item["rent_ghs"]
        if isinstance(rent, bool) or not isinstance(rent, int | float) or rent <= 0:
            raise InvalidInput(f"{name}: rent_ghs must be a positive number.")
        beds = item["bedrooms"]
        if isinstance(beds, bool) or not isinstance(beds, int) or not 0 <= beds <= 10:
            raise InvalidInput(f"{name}: bedrooms must be a whole number from 0 to 10.")
        seen.add(item["id"])
        cases.append(SeededCase(**item))
    return cases


@dataclass
class SeededResult:
    detector: str
    cases: int = 0
    fraud: int = 0
    skipped: int = 0
    model: Tally = field(default_factory=Tally)
    rules: Tally = field(default_factory=Tally)
    missed: list[str] = field(default_factory=list)  # fraud cases the model didn't flag

    def as_dict(self) -> dict:
        return {"detector": self.detector, "cases": self.cases, "fraud": self.fraud, "skipped": self.skipped,
                "model": self.model.as_dict(), "rules": self.rules.as_dict(), "missed": self.missed}


def _add(result: SeededResult, case: SeededCase, score: int, limit: int, rule_hit: bool) -> None:
    result.cases += 1
    result.fraud += case.fraud
    flagged = score >= limit
    result.model.add(flagged, case.fraud)
    result.rules.add(rule_hit, case.fraud)
    if case.fraud and not flagged:
        result.missed.append(case.id)


def evaluate_seeded(db: Session, cases: list[SeededCase]) -> list[SeededResult]:
    """Score every case with the wording and price detectors (and the Claude detector while it's
    on), next to the Phase 1 rules, each at its own threshold."""
    newest = db.scalar(
        select(ModelVersion).where(ModelVersion.detector == "scam_text").order_by(ModelVersion.id.desc())
    )
    text_model = get_text_model((newest.version, newest.params) if newest else None)
    wording, price = SeededResult("scam_text"), SeededResult("price")
    results = [wording]
    claude, llm = None, None
    if mode(db, "scam_text_llm") != "off":
        claude = SeededResult("scam_text_llm")
        results.append(claude)
        try:
            llm = REGISTRY["scam_text_llm"].make_model()
        except Exception:  # noqa: BLE001 - no key or no SDK: every case counts as skipped
            llm = None
    results.append(price)
    areas = {a.slug: a for a in db.scalars(select(ServiceArea))}
    for case in cases:
        rule_hit = bool(scam_language(case.text))
        _add(wording, case, text_model.score(case.text).score, threshold(db, "scam_text"), rule_hit)
        if claude is not None:
            try:
                if llm is None:
                    raise RuntimeError("Claude isn't available")
                llm_score = llm.score(case.text).score
            except Exception:  # noqa: BLE001 - one provider failure mustn't sink the report
                claude.skipped += 1
            else:
                _add(claude, case, llm_score, threshold(db, "scam_text_llm"), rule_hit)
        area = areas.get(case.area)
        if area is None:
            price.skipped += 1
            continue
        pesewas = round(case.rent_ghs * 100)
        ref = reference_rent(db, area.id, case.bedrooms)
        model_score = score_rent(pesewas, *ref).score if ref else 0
        ruled = price_anomaly(db, pesewas, area, case.bedrooms) is not None
        _add(price, case, model_score, threshold(db, "price"), ruled)
    return results
