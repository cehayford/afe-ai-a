"""The copilot's test cases: hand-written home verifications with the right answer, so the copilot is measured before
it sees a real case. Each case lists only what differs from a clean home (`base`); the loader builds the full packet,
the same shape copilot.packet() makes. Reviewers check the answers and add cases, especially Accra-specific tricks."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import InvalidInput

from . import copilot

DEFAULT_PATH = Path(__file__).with_name("copilot_cases.json")
FIELDS = {"id", "note", "changes", "answer"}
AGREEMENT_BAR = 0.85


@dataclass(frozen=True)
class Case:
    id: str
    note: str
    packet: dict
    decision: str
    reason_codes: list[str]


def _merge(base: dict, changes: dict) -> dict:
    """Changes replace what's in the base, except that objects merge key by key (a list is replaced whole)."""
    out = dict(base)
    for key, value in changes.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def load_cases(path: Path = DEFAULT_PATH) -> list[Case]:
    """Read and check the file. Every mistake names the case, so the team can fix it."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidInput(f"Can't read the copilot's test cases at {path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("base"), dict) or not isinstance(raw.get("cases"), list):
        raise InvalidInput("The test cases file needs a base packet and a list of cases.")
    base = raw["base"]
    if tuple(base) != copilot.PACKET_SECTIONS:
        raise InvalidInput(f"The base packet needs these sections, in order: {', '.join(copilot.PACKET_SECTIONS)}.")
    cases, seen = [], set()
    for n, item in enumerate(raw["cases"], start=1):
        if not isinstance(item, dict):
            raise InvalidInput(f"case {n}: each case must be an object.")
        name = item.get("id", f"case {n}")
        missing, unknown = FIELDS - set(item), set(item) - FIELDS
        if missing:
            raise InvalidInput(f"{name}: missing {', '.join(sorted(missing))}.")
        if unknown:
            raise InvalidInput(f"{name}: unknown field {', '.join(sorted(unknown))}.")
        if not isinstance(name, str) or not isinstance(item["note"], str):
            raise InvalidInput(f"{name}: id and note must be text.")
        if name in seen:
            raise InvalidInput(f"{name}: this id is used twice.")
        changes, answer = item["changes"], item["answer"]
        if not isinstance(changes, dict) or set(changes) - set(copilot.PACKET_SECTIONS):
            raise InvalidInput(f"{name}: changes may only touch {', '.join(copilot.PACKET_SECTIONS)}.")
        if (not isinstance(answer, dict) or answer.get("decision") not in ("approve", "reject")
                or not isinstance(answer.get("reason_codes"), list)):
            raise InvalidInput(f"{name}: answer needs a decision (approve or reject) and a list of reason_codes.")
        try:
            copilot.check(copilot.CopilotAnswer(decision=answer["decision"], reason_codes=answer["reason_codes"],
                                                summary="", concerns=[]))
        except (copilot.NoAnswer, ValueError) as exc:
            raise InvalidInput(f"{name}: {exc}") from exc
        seen.add(name)
        cases.append(Case(name, item["note"], _merge(base, changes), answer["decision"], list(answer["reason_codes"])))
    return cases


@dataclass(frozen=True)
class EvalReport:
    results: list[dict]
    agreement: float
    false_approvals: int
    code_overlap: float
    cost_usd: float
    errors: int

    @property
    def passed(self) -> bool:
        return self.errors == 0 and self.false_approvals == 0 and self.agreement >= AGREEMENT_BAR


def run_eval(cases: list[Case], suggest: Callable[[dict], copilot.Suggestion]) -> EvalReport:
    """Send each case's packet through `suggest` and score the answers against the bar. A case that errors counts as
    a disagreement, and any error fails the run."""
    results, agreed, false_approvals, overlaps, cost, errors = [], 0, 0, [], 0.0, 0
    for case in cases:
        row = {"id": case.id, "expected": f"{case.decision} {','.join(case.reason_codes)}", "suggested": "",
               "agrees": False, "false_approval": False, "error": ""}
        try:
            s = suggest(case.packet)
        except (copilot.NoAnswer, *copilot.FAILURES) as exc:
            errors += 1
            row["error"] = f"{type(exc).__name__}: {exc}"
            results.append(row)
            continue
        result = copilot.compare(s.answer.decision, s.answer.reason_codes, case.decision, case.reason_codes)
        agreed += result.agrees
        false_approvals += result.false_approval
        overlaps.append(result.overlap)
        cost += s.cost_usd
        row.update(suggested=f"{s.answer.decision} {','.join(s.answer.reason_codes)}", agrees=result.agrees,
                   false_approval=result.false_approval)
        results.append(row)
    return EvalReport(results, agreed / len(cases) if cases else 0.0, false_approvals,
                      sum(overlaps) / len(overlaps) if overlaps else 0.0, round(cost, 4), errors)
