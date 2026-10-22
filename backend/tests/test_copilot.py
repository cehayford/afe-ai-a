"""The reviewer copilot: the masked packet, the call, the test cases, the runs in shadow, and measuring them against
reviewers' decisions."""

import dataclasses
import json
import re
from datetime import timedelta
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from sqlalchemy import select

from app.cli import main
from app.config import get_settings
from app.core.errors import InvalidInput
from app.db import utcnow
from app.modules.agents import copilot, gateway, service
from app.modules.agents.cases import DEFAULT_PATH, load_cases, run_eval
from app.modules.agents.copilot import Comparison, Concern, CopilotAnswer
from app.modules.agents.models import AgentRun
from app.modules.compliance import service as compliance
from app.modules.detection.hooks import FRAUD_CODES
from app.modules.identity.service import latest_check
from app.modules.units.models import PropertyType
from app.modules.units.service import register_unit
from app.modules.verification.models import CHECKLIST_ITEMS
from app.modules.verification.service import add_visit_photo, complete_visit, decide_unit
from tests.conftest import PIN, accept_owner_authority, api_login, begin_visit, passed_visit, photo_bytes


@pytest.fixture
def visited(db, unit, verified_landlord, reviewer, verifier):
    """A home with an accepted owner record and a passed visit whose notes name people and give a phone number."""
    record = accept_owner_authority(db, unit, verified_landlord, reviewer)
    record.owner_name, record.owner_phone = "Kwame Mensah", "+233201234567"
    visit = begin_visit(db, unit, verifier)
    for n in range(4):
        add_visit_photo(db, visit, verifier, photo_bytes(n), *unit.point, utcnow())
    return complete_visit(db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, True),
                          notes="Met Ama and her uncle Kwame Mensah (0244123456). Water tank on the roof.")


# --- The packet ----------------------------------------------------------------------------------------------


def test_the_packet_carries_the_facts_a_reviewer_uses(db, unit, visited):
    p = copilot.packet(db, unit, visited)
    assert tuple(p) == copilot.PACKET_SECTIONS
    assert p["home"] == {"area": "East Legon", "property_type": "apartment", "bedrooms": 2, "bathrooms": 1,
                         "listing_rent_ghs": None, "usual_rent_ghs": 5000.0, "usual_rent_source": "Afe's price survey"}
    landlord = p["landlord"]
    assert landlord["role"] == "landlord" and landlord["identity_verified"] is True and landlord["other_homes"] == 0
    assert landlord["id_check"] == {"name_matches": True, "liveness_passed": True}
    assert [(a["relationship"], a["document_type"], a["status"]) for a in p["authorities"]] == [
        ("owner", "indenture", "accepted")]
    visit = p["visit"]
    assert visit["outcome"] == "passed" and visit["photos"] == 4 and all(visit["checklist"].values())
    assert visit["metres_from_pin"] == 0 and visit["days_ago"] == 0
    assert p["history"] == {"open_flags": [], "decisions": []}


def test_the_packet_leaves_out_names_contacts_and_places(db, unit, visited):
    sent = copilot.serialise(copilot.packet(db, unit, visited))
    for secret in ("Ama", "Kwame", "Mensah", "0244123456", "233244123456", "233201234567", "GA-492-7424", "Flat 2B"):
        assert secret not in sent, secret
    assert "[landlord]" in sent and "[owner]" in sent and "[phone]" in sent


def test_masking_replaces_whole_names_and_contact_details():
    names = [("Ama", "[landlord]"), ("Kwame Mensah", "[owner]"), ("Al", "[verifier]")]
    text = "Ama met KWAME at the gate; Mensah's sister Amanda called 0244123456, ama@example.com, plot 1234567. Al said ok."
    assert gateway.mask(text, names) == (
        "[landlord] met [owner] at the gate; [owner]'s sister Amanda called [phone], [email], plot [number]. Al said ok."
    )


def test_a_bare_home_still_makes_a_packet(db, unit, verifier):
    visit = begin_visit(db, unit, verifier)
    visit = complete_visit(db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, False), result="fail",
                           fail_reason="UNIT_NOT_FOUND")
    p = copilot.packet(db, unit, visit)
    assert p["authorities"] == [] and p["models"] == []
    assert p["landlord"]["id_check"] is None and p["landlord"]["identity_verified"] is False
    assert p["home"]["listing_rent_ghs"] is None and p["visit"]["outcome"] == "failed" and p["visit"]["photos"] == 0
    assert "UNIT_NOT_FOUND" in p["visit"]["notes"]


def test_the_fingerprint_ignores_key_order():
    assert copilot.fingerprint({"a": 1, "b": [1, 2]}) == copilot.fingerprint({"b": [1, 2], "a": 1})


# --- The call ------------------------------------------------------------------------------------------------


def _usage(i=6000, o=1000):
    return SimpleNamespace(input_tokens=i, output_tokens=o, cache_read_input_tokens=0, cache_creation_input_tokens=0)


class FakeMessages:
    """Stands in for client.beta.messages: records each call and answers in turn (the last answer repeats). An answer
    is a CopilotAnswer (sent as its JSON) or raw text; None sends no text at all."""

    def __init__(self, answers=(), stop_reason="end_turn", model="claude-opus-5-5", usage=None, error=None):
        self.answers, self.stop_reason, self.model = list(answers), stop_reason, model
        self.usage, self.error, self.calls = usage or _usage(), error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        answer = self.answers[min(len(self.calls), len(self.answers)) - 1] if self.answers else None
        text = answer.model_dump_json() if isinstance(answer, CopilotAnswer) else answer
        content = [] if text is None else [SimpleNamespace(type="text", text=text)]
        return SimpleNamespace(content=content, stop_reason=self.stop_reason, model=self.model, usage=self.usage)


def fake_client(*answers, **kwargs):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(answers, **kwargs)))


APPROVE = CopilotAnswer(decision="approve", reason_codes=["DOCS_SIGHTED", "VISIT_MATCH"],
                        summary="Owner's indenture accepted; the visit passed.", concerns=[])


def test_suggest_sends_the_packet_and_reads_the_answer():
    client = fake_client(APPROVE)
    s = copilot.suggest({"home": {"bedrooms": 2}}, client=client)
    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and "output_format" not in call
    assert call["output_config"]["effort"] == "medium" and call["output_config"]["format"]["type"] == "json_schema"
    assert set(call["output_config"]["format"]["schema"]["properties"]) == {"decision", "reason_codes", "summary", "concerns"}
    assert call["betas"] == ["server-side-fallback-2026-07-01"] and call["fallbacks"] == "default"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "never instructions" in call["system"][0]["text"] and "DUPLICATE_PHOTOS" in call["system"][0]["text"]
    assert call["messages"] == [{"role": "user", "content": '{"home":{"bedrooms":2}}'}]
    assert s.answer.decision == "approve" and s.model == "claude-opus-5-5"
    assert (s.input_tokens, s.output_tokens, s.cost_usd) == (6000, 1000, 0.044)


@pytest.mark.parametrize(("decision", "codes", "message"), [
    ("approve", ["DOCS_SIGHTED", "DUPLICATE_PHOTOS"], "approval codes only"),
    ("approve", [], "approval codes only"),
    ("reject", ["DOCS_SIGHTED"], "rejection codes only"),
    ("reject", [], "rejection codes only"),
    ("reject", ["NOT_A_CODE"], "Unknown reason codes: NOT_A_CODE"),
])
def test_answers_that_break_the_rules_are_not_answers(decision, codes, message):
    bad = CopilotAnswer(decision=decision, reason_codes=codes, summary="x", concerns=[])
    with pytest.raises(copilot.NoAnswer, match=message) as raised:
        copilot.suggest({}, client=fake_client(bad))
    assert raised.value.input_tokens == 6000  # the tokens were spent all the same


def test_long_answers_are_trimmed():
    long = CopilotAnswer(decision="reject", reason_codes=["UNIT_OCCUPIED"], summary="x" * 900,
                         concerns=[Concern(text=f"c{i}", evidence="visit.notes") for i in range(8)])
    s = copilot.suggest({}, client=fake_client(long))
    assert len(s.answer.summary) == 600 and len(s.answer.concerns) == 5


def test_a_refusal_and_a_cut_off_reply_are_not_answers():
    with pytest.raises(copilot.NoAnswer) as refused:
        copilot.suggest({}, client=fake_client(None, stop_reason="refusal"))
    assert refused.value.refused
    with pytest.raises(copilot.NoAnswer, match="max_tokens") as cut:
        copilot.suggest({}, client=fake_client(None, stop_reason="max_tokens"))
    assert not cut.value.refused


def test_it_needs_a_key_when_no_client_is_given(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    with pytest.raises(RuntimeError, match="AFE_ANTHROPIC_API_KEY"):
        copilot.suggest({})


def test_compare_marks_agreement_and_false_approvals():
    assert copilot.compare("approve", ["DOCS_SIGHTED"], "reject", ["DUPLICATE_PHOTOS"]) == Comparison(False, True, 0.0)
    assert copilot.compare("approve", ["DOCS_SIGHTED"], "reject", ["OWNER_UNREACHABLE"]).false_approval is False
    assert copilot.compare("reject", ["UNIT_OCCUPIED"], "reject", ["UNIT_OCCUPIED", "UNIT_MISMATCH"]) == (
        Comparison(True, False, 0.5))


# --- Test cases ----------------------------------------------------------------------------------------------


def _answering_right(cases):
    right = {copilot.fingerprint(c.packet): c for c in cases}

    def suggest(packet, client=None, model=None):
        c = right[copilot.fingerprint(packet)]
        answer = CopilotAnswer(decision=c.decision, reason_codes=c.reason_codes, summary="", concerns=[])
        return copilot.Suggestion(answer, "claude-opus-5-5", 100, 10, 0.001)

    return suggest


def test_the_shipped_cases_load_and_cover_every_fraud_reason():
    cases = load_cases()
    assert len(cases) == 30 and sum(c.decision == "approve" for c in cases) == 18
    assert FRAUD_CODES <= {code for c in cases for code in c.reason_codes}
    assert all(tuple(c.packet) == copilot.PACKET_SECTIONS for c in cases)
    assert len({copilot.fingerprint(c.packet) for c in cases}) == 30  # no two cases are the same home


def _write_cases(tmp_path, *cases):
    base = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))["base"]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"base": base, "cases": list(cases)}), encoding="utf-8")
    return path


GOOD_ANSWER = {"decision": "approve", "reason_codes": ["VISIT_MATCH"]}


@pytest.mark.parametrize(("case", "message"), [
    ({"id": "a", "note": "", "changes": {}, "answer": GOOD_ANSWER, "extra": 1}, "a: unknown field extra"),
    ({"id": "b", "note": "", "changes": {}}, "b: missing answer"),
    ({"id": "c", "note": "", "changes": {"garden": {}}, "answer": GOOD_ANSWER}, "c: changes may only touch"),
    ({"id": "d", "note": "", "changes": {}, "answer": {"decision": "maybe", "reason_codes": []}},
     "d: answer needs a decision"),
    ({"id": "e", "note": "", "changes": {}, "answer": {"decision": "reject", "reason_codes": ["NOPE"]}},
     "e: Unknown reason codes: NOPE"),
    ({"id": "f", "note": "", "changes": {}, "answer": {"decision": "approve", "reason_codes": ["UNIT_OCCUPIED"]}},
     "f: An approval needs approval codes only"),
])
def test_a_broken_case_is_refused_by_name(tmp_path, case, message):
    with pytest.raises(InvalidInput, match=re.escape(message)):
        load_cases(_write_cases(tmp_path, case))


def test_a_repeated_id_is_refused(tmp_path):
    case = {"id": "same", "note": "", "changes": {}, "answer": GOOD_ANSWER}
    with pytest.raises(InvalidInput, match="same: this id is used twice"):
        load_cases(_write_cases(tmp_path, case, case))


def test_the_eval_passes_a_perfect_copilot_and_fails_one_that_approves_everything():
    cases = load_cases()
    perfect = run_eval(cases, _answering_right(cases))
    assert perfect.passed and perfect.agreement == 1.0 and perfect.false_approvals == 0
    lax = run_eval(cases, lambda packet: copilot.Suggestion(APPROVE, "claude-opus-5-5", 100, 10, 0.001))
    assert not lax.passed and lax.false_approvals == 8 and lax.agreement == 0.6


def test_an_error_on_one_case_fails_the_eval_but_not_the_others():
    cases = load_cases()
    right = _answering_right(cases)

    def flaky(packet):
        if packet is cases[0].packet:
            raise copilot.NoAnswer("Claude gave no answer (stop reason: max_tokens)")
        return right(packet)

    report = run_eval(cases, flaky)
    assert report.errors == 1 and not report.passed and "max_tokens" in report.results[0]["error"]


def test_the_eval_command_prints_each_case_and_exits_on_the_bar(monkeypatch, capsys):
    monkeypatch.setattr(copilot, "suggest", _answering_right(load_cases()))
    assert main(["eval-copilot"]) == 0
    assert "Agreement 100%" in capsys.readouterr().out
    monkeypatch.setattr(copilot, "suggest", lambda packet, client=None, model=None: copilot.Suggestion(
        APPROVE, "claude-opus-5-5", 100, 10, 0.001))
    assert main(["eval-copilot"]) == 1
    assert "FALSE APPROVAL" in capsys.readouterr().out


# --- Runs in shadow ------------------------------------------------------------------------------------------


def _set_rule(monkeypatch, key, value):
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default=value))


@pytest.fixture
def shadow(monkeypatch):
    _set_rule(monkeypatch, "agent_copilot_level", "shadow")


@pytest.fixture
def ready(db, unit, verified_landlord, reviewer, verifier):
    """A home ready to decide: an accepted owner record and a passed visit."""
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    return passed_visit(db, unit, verifier)


def _runs(db):
    return list(db.scalars(select(AgentRun).order_by(AgentRun.id)))


def test_the_copilot_is_off_until_two_reviewers_turn_it_on(db, ready):
    assert compliance.rule(db, "agent_copilot_level") == "off" and _runs(db) == []


def test_its_level_can_only_be_off_or_shadow(db, reviewer):
    with pytest.raises(InvalidInput):
        compliance.propose(db, reviewer, "agent_copilot_level", "suggest", "Not yet")
    assert compliance.propose(db, reviewer, "agent_copilot_level", "shadow", "Counsel cleared B11").key == (
        "agent_copilot_level")


def test_a_completed_visit_queues_one_run(db, shadow, ready, unit):
    [run] = _runs(db)
    assert (run.agent, run.unit_id, run.visit_id, run.status) == ("copilot", unit.id, ready.id, "queued")
    assert service.queue_copilot(db, unit, ready) is run  # one run per visit


def test_the_worker_stores_the_answer_and_what_it_cost(db, shadow, ready):
    assert service.run_pending(db, client=fake_client(APPROVE))["done"] == 1
    [run] = _runs(db)
    assert run.status == "done" and run.decision == "approve" and run.reason_codes == ["DOCS_SIGHTED", "VISIT_MATCH"]
    assert (run.input_tokens, run.output_tokens, run.cost_usd, run.model) == (6000, 1000, 0.044, "claude-opus-5-5")
    assert run.packet["visit"]["photos"] == 4 and run.packet_sha256 == copilot.fingerprint(run.packet)
    assert run.prompt_version == "copilot-1" and run.finished_at is not None


def test_errors_are_retried_then_the_run_fails(db, shadow, ready):
    client = fake_client(error=RuntimeError("AFE_ANTHROPIC_API_KEY is not set"))
    for _ in range(4):
        service.run_pending(db, client=client)
    [run] = _runs(db)
    assert run.status == "failed" and run.attempts == 3 and "AFE_ANTHROPIC_API_KEY" in run.error
    assert len(client.beta.messages.calls) == 3


def test_an_answer_that_breaks_the_rules_is_never_stored(db, shadow, ready):
    bad = CopilotAnswer(decision="approve", reason_codes=["DUPLICATE_PHOTOS"], summary="x", concerns=[])
    for _ in range(3):
        service.run_pending(db, client=fake_client(bad))
    [run] = _runs(db)
    assert run.status == "failed" and run.decision == "" and "approval codes only" in run.error
    assert run.input_tokens == 18000  # the three attempts' tokens still count against the budget


def test_a_refusal_is_recorded(db, shadow, ready):
    assert service.run_pending(db, client=fake_client(None, stop_reason="refusal"))["refused"] == 1
    assert _runs(db)[0].status == "refused"


def test_switching_off_cancels_queued_runs(db, shadow, ready, monkeypatch):
    _set_rule(monkeypatch, "agent_copilot_level", "off")
    client = fake_client(APPROVE)
    assert service.run_pending(db, client=client)["cancelled"] == 1 and client.beta.messages.calls == []


def test_a_home_decided_first_is_too_late(db, shadow, ready, unit, reviewer):
    decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    client = fake_client(APPROVE)
    assert service.run_pending(db, client=client)["too_late"] == 1 and client.beta.messages.calls == []


def test_the_daily_budget_holds_runs_until_tomorrow(db, shadow, ready, unit, verifier, monkeypatch):
    _set_rule(monkeypatch, "agent_copilot_daily_tokens", 5000)
    passed_visit(db, unit, verifier, seed=1)  # a second visit, so a second run
    client = fake_client(APPROVE)
    counts = service.run_pending(db, client=client)
    assert (counts["done"], counts["waiting"]) == (1, 1)
    assert service.run_pending(db, client=client, now=utcnow() + timedelta(days=1))["done"] == 1


# --- Measuring against reviewers -------------------------------------------------------------------------------


@pytest.fixture
def done_run(db, shadow, ready):
    service.run_pending(db, client=fake_client(APPROVE))
    return _runs(db)[0]


def test_a_reviewer_decision_is_measured_against_the_copilot(db, done_run, unit, reviewer):
    decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    assert (done_run.reviewer_decision, done_run.reviewer_codes) == ("approve", ["DOCS_SIGHTED", "VISIT_MATCH"])
    assert done_run.agrees is True and done_run.false_approval is False


@pytest.mark.parametrize(("codes", "false_approval"), [(["DUPLICATE_PHOTOS"], True), (["OWNER_UNREACHABLE"], False)])
def test_approving_what_a_reviewer_rejects_for_fraud_is_a_false_approval(db, done_run, unit, reviewer, codes,
                                                                         false_approval):
    decide_unit(db, unit, reviewer, False, codes, note="See the visit.")
    assert done_run.agrees is False and done_run.false_approval is false_approval


def test_a_decision_on_a_newer_visit_leaves_the_older_run_uncounted(db, done_run, unit, verifier, reviewer):
    newer = passed_visit(db, unit, verifier, seed=1)
    decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    older, latest = _runs(db)
    assert older.reviewer_decision == "" and older.agrees is None
    assert latest.visit_id == newer.id and latest.status == "queued"
    assert service.run_pending(db, client=fake_client(APPROVE))["too_late"] == 1


def test_the_numbers_for_the_models_page(client, db, done_run, unit, reviewer):
    decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    db.commit()
    body = client.get("/api/v1/review/agents/copilot", headers=api_login(client, "reviewer")).json()["data"]
    assert body == {"level": "shadow", "days": 7, "runs": 1, "done": 1, "failed": 0, "refused": 0, "too_late": 0,
                    "decided": 1, "agreement": 1.0, "false_approvals": 0, "code_overlap": 1.0, "cost_usd": 0.044}


# --- Review fixes ---------------------------------------------------------------------------------------------


def _visit_with_notes(db, unit, verifier, notes, seed=0):
    visit = begin_visit(db, unit, verifier)
    for n in range(4):
        add_visit_photo(db, visit, verifier, photo_bytes(seed * 10 + n), *unit.point, utcnow())
    return complete_visit(db, visit, verifier, dict.fromkeys(CHECKLIST_ITEMS, True), notes=notes)


def test_flags_go_with_a_fixed_text_never_their_stored_explanation(db, area, landlord, unit, verifier):
    other = register_unit(db, landlord, area, "GA-111-2222", "Room 9", PIN[0], PIN[1], PropertyType.APARTMENT, 2)
    passed_visit(db, other, verifier, seed=7)
    visit = _visit_with_notes(db, unit, verifier, "", seed=7)  # the same photos as the other home
    p = copilot.packet(db, unit, visit)
    assert "GA-111-2222" not in copilot.serialise(p) and "Room 9" not in copilot.serialise(p)
    assert p["history"]["open_flags"] == [{"rule": "photos.duplicate_of_other_unit", "severity": "high",
                                           "explanation": "A visit photo matches a photo of another home."}]


def test_masking_covers_card_names_hyphens_the_address_and_phone_formats(db, unit, verified_landlord, reviewer,
                                                                        verifier):
    verified_landlord.display_name = "Kwame Ofori-Atta"
    latest_check(db, verified_landlord).name_on_card = "Ama Serwaa Boateng"
    unit.landmark = "Behind the Shell filling station"
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    visit = _visit_with_notes(db, unit, verifier, (
        "Mr Atta and Mrs Boateng (Serwaa) met me behind the Shell filling station, GA-492-7424 at 5.6402, -0.1583. "
        "Call (024) 412 3456, 024.412.3456 or +233-24-412-3456; photos at https://jiji.com.gh/ad/123. Flat 2B, "
        "GH₵ 4,800.00 from 2026-10-01."))
    notes = copilot.packet(db, unit, visit)["visit"]["notes"]
    for leaked in ("Atta", "Boateng", "Serwaa", "Shell filling station", "GA-492-7424", "5.6402", "0.1583", "412",
                   "jiji", "Flat 2B"):
        assert leaked not in notes, (leaked, notes)
    assert "GH₵ 4,800.00 from 2026-10-01" in notes  # amounts and dates are kept


def _sdk_client(body):
    """The real SDK, answering from a canned response: no network."""
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200, json=body))
    return anthropic.Anthropic(api_key="x", max_retries=0, http_client=httpx2.Client(transport=transport))


def _api_reply(text, stop_reason, output_tokens):
    return {"id": "m", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 900, "output_tokens": output_tokens}}


def test_a_cut_off_reply_still_counts_its_tokens(db, shadow, ready):
    client = _sdk_client(_api_reply('{"decision": "approve", "reason_co', "max_tokens", 8000))
    with pytest.raises(copilot.NoAnswer, match="max_tokens") as raised:
        copilot.suggest({}, client=client)
    assert (raised.value.input_tokens, raised.value.output_tokens) == (900, 8000)
    service.run_pending(db, client=client)
    assert _runs(db)[0].output_tokens == 8000


def test_a_refusal_after_some_text_is_a_refusal(db, shadow, ready):
    client = _sdk_client(_api_reply('{"decision": "rej', "refusal", 50))
    assert service.run_pending(db, client=client)["refused"] == 1


def test_a_fallback_served_reply_counts_every_hop_at_its_own_price():
    hops = [SimpleNamespace(type="message", input_tokens=6000, output_tokens=200, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0),
            SimpleNamespace(type="fallback_message", model="claude-opus-5", input_tokens=6000, output_tokens=1000,
                            cache_read_input_tokens=0, cache_creation_input_tokens=0)]
    usage = SimpleNamespace(input_tokens=6000, output_tokens=1000, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0, iterations=hops)
    s = copilot.suggest({}, client=fake_client(APPROVE, model="claude-opus-5", usage=usage))
    assert (s.input_tokens, s.output_tokens) == (12000, 1200)
    assert s.cost_usd == 0.083  # the declined hop at Opus 5.5's price (0.028), the answer at Opus 5's (0.055)
    assert copilot.cost("claude-new-9", _usage()) == copilot.cost("claude-opus-5-5", _usage())  # no price: priced high


def test_one_call_per_pass(db, shadow, ready, unit, verifier):
    passed_visit(db, unit, verifier, seed=1)
    counts = service.run_pending(db, client=fake_client(APPROVE))
    assert (counts["done"], counts["waiting"]) == (1, 1)


def test_an_unexpected_error_counts_as_an_attempt_and_never_stalls_the_queue(db, shadow, ready, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("a bug in the packet")

    monkeypatch.setattr(copilot, "packet", broken)
    for _ in range(3):
        service.run_pending(db, client=fake_client(APPROVE))
    [run] = _runs(db)
    assert run.status == "failed" and run.attempts == 3 and "a bug in the packet" in run.error


def test_the_copilot_never_blocks_a_reviewer_or_a_verifier(db, shadow, unit, verified_landlord, reviewer, verifier,
                                                          monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("agent_runs is missing")

    monkeypatch.setattr(service, "queue_copilot", broken)
    monkeypatch.setattr(service, "record_decision", broken)
    accept_owner_authority(db, unit, verified_landlord, reviewer)
    visit = passed_visit(db, unit, verifier)
    assert visit.outcome == "passed"
    verification = decide_unit(db, unit, reviewer, True, ["DOCS_SIGHTED", "VISIT_MATCH"])
    assert verification.status == "approved"
