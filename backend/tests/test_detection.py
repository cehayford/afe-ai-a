"""Phase 3: detection models in shadow, labels from human decisions, evaluation against the
rules, the promotion gate, and what models may do once promoted."""

import dataclasses

import pytest
from sqlalchemy import select

from app.core.errors import RuleViolation
from app.db import utcnow
from app.modules.accounts.models import Role
from app.modules.compliance import service as compliance
from app.modules.detection import service as detection
from app.modules.detection.documents import tamper_score
from app.modules.detection.hooks import label, label_key
from app.modules.detection.models import DetectionLabel, JobStatus, LinkEdge, ModelScore, ScoreJob
from app.modules.detection.text import HeuristicTextModel, TextScore, redact, train_naive_bayes
from app.modules.enquiries import service as enquiries
from app.modules.identity.service import check_ghana_card
from app.modules.listings.service import publish, submit_for_review
from app.modules.risk.flags import open_flags, raise_flag, resolve_flag
from app.modules.risk.models import RiskFlag
from app.modules.scamcheck import service as scamcheck
from app.modules.units.service import register_unit
from app.modules.verification.service import add_visit_photo, complete_visit, decide_party
from tests.conftest import api_login, begin_visit, make_listing, make_user, photo_bytes

SCAM = "Hello, pay GH₵500 viewing fee first then I show you the room. Send momo to 0244999888 today only"
BENIGN = "Hello, yes the flat is available. You can come and see it on Saturday afternoon."


def set_mode(monkeypatch, detector: str, mode: str):
    """Tests jump a model straight to a mode; in the app that needs a passing evaluation and two reviewers."""
    key = f"model_{detector}_mode"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default=mode))


@pytest.fixture
def live(db, verified_unit, verified_landlord, reviewer):
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    return publish(db, listing, reviewer)


@pytest.fixture
def renter(db):
    return make_user(db, "yaa", Role.RENTER, phone="0240000009")


@pytest.fixture
def thread(db, live, renter):
    return enquiries.start_enquiry(db, renter, live, "Is it still available?")


# --- Text model ---------------------------------------------------------------------------------------


def test_redaction_masks_personal_details():
    text = redact("Call 024 499 9888 or mail ama@example.com, account 1234567890")
    assert "999" not in text and "example.com" not in text and "1234567890" not in text
    assert "[phone]" in text and "[email]" in text and "[number]" in text


def test_feature_model_separates_scam_from_ordinary_messages():
    model = HeuristicTextModel()
    scam, benign = model.score(SCAM), model.score(BENIGN)
    assert scam.score >= 90 and benign.score <= 10
    assert any("money before a viewing" in r for r in scam.reasons)


@pytest.mark.parametrize("text", ["GH₵300", "GH 300", "gh300", "GHS 1,200", "300 cedis", "1500gh", "₵ 450"])
def test_amounts_are_recognised_however_they_are_written(text):
    assert any("amount of money" in r for r in HeuristicTextModel().score(f"Pay {text} now").reasons)


def test_trained_naive_bayes_is_blended_in():
    examples = [(f"send momo commitment fee first {i}", True) for i in range(6)]
    examples += [(f"lovely flat with water tank near the road {i}", False) for i in range(6)]
    params = train_naive_bayes(examples)
    model = HeuristicTextModel(("nb-1", params))
    result = model.score("please send momo commitment fee")
    assert result.version == "features-1+nb-1"
    assert result.score > HeuristicTextModel(("nb-1", params)).score("lovely flat with water tank").score


# --- Documents -------------------------------------------------------------------------------------------


def test_document_tamper_signals():
    edited = (
        b"%PDF-1.4\n/Producer (Adobe Photoshop 25.0)\n/CreationDate (D:20190101)\n/ModDate (D:20260901)\n"
        b"/Subtype /FreeText\n%%EOF\nmore\n%%EOF\n"
    )
    score, reasons = tamper_score(edited)
    assert score >= 80
    assert any("Photoshop" in r for r in reasons) and any("typed text" in r for r in reasons)
    clean_score, _ = tamper_score(b"%PDF-1.4\n/Producer (Scanner)\n%%EOF\n")
    assert clean_score < 20


# --- Queue and shadow mode --------------------------------------------------------------------------------


def test_messages_are_scored_in_shadow_without_acting(db, thread, verified_landlord):
    message = enquiries.send_message(db, thread, verified_landlord, SCAM)
    job = db.scalar(select(ScoreJob).where(ScoreJob.detector == "scam_text", ScoreJob.subject_type == "messages"))
    assert job.status == JobStatus.PENDING
    assert detection.process_pending(db)["scored"] >= 1
    score = db.scalar(select(ModelScore).where(ModelScore.subject_type == "messages", ModelScore.subject_id == str(message.id)))
    assert score.score >= 90 and score.mode == "shadow" and not score.acted
    assert not any(f.rule.startswith("model.") for f in open_flags(db, verified_landlord))


def test_active_model_flags_the_sender_and_warns(db, monkeypatch, thread, verified_landlord):
    set_mode(monkeypatch, "scam_text", "active")
    key = "model_scam_text_threshold"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default=35))
    # Wording the Phase 1 rules miss: no "pay first", but money, a deposit and a transfer.
    missed = enquiries.send_message(db, thread, verified_landlord, "Kindly transfer the GH₵300 deposit to my account number")
    assert missed.warning == ""
    ruled = enquiries.send_message(db, thread, verified_landlord, "Kindly send the commitment fee GH₵300 by momo")
    rule_warning = ruled.warning
    detection.process_pending(db)
    flags = [f for f in open_flags(db, verified_landlord) if f.rule == "model.scam_text"]
    assert flags and flags[0].severity == "medium"  # a model flag asks for a look; it doesn't block
    assert missed.warning.startswith("Afe's checks think")
    assert ruled.warning == rule_warning  # the rule's more specific warning stays


def test_off_mode_skips_scoring(db, monkeypatch, thread, verified_landlord):
    set_mode(monkeypatch, "scam_text", "off")
    enquiries.send_message(db, thread, verified_landlord, SCAM)
    assert detection.process_pending(db)["skipped"] >= 1
    assert db.scalar(select(ModelScore).where(ModelScore.subject_type == "messages")) is None


def test_canary_is_a_stable_share(db):
    picked = [i for i in range(2000) if detection.in_canary(db, "messages", str(i))]
    assert 140 < len(picked) < 260  # about 10%
    assert picked == [i for i in range(2000) if detection.in_canary(db, "messages", str(i))]  # same answer every time


def test_a_failing_model_is_retried_then_marked_failed(db, monkeypatch, thread, verified_landlord):
    from app.modules.detection.detectors import REGISTRY

    def boom(*_):
        raise RuntimeError("provider down")

    monkeypatch.setattr(REGISTRY["scam_text"], "score", boom)
    enquiries.send_message(db, thread, verified_landlord, BENIGN)
    for _ in range(3):
        detection.process_pending(db)
    job = db.scalar(select(ScoreJob).where(ScoreJob.subject_type == "messages"))
    assert job.status == JobStatus.FAILED and job.attempts == 3 and "provider down" in job.error


# --- The Claude wording detector ------------------------------------------------------------------------------


class FakeClaude:
    def __init__(self, score=91, error=None):
        self.value, self.error = score, error

    def score(self, text):
        if self.error:
            raise RuntimeError(self.error)
        return TextScore(self.value, ["Asks for money before a viewing"], "claude-haiku-4-5")


def test_claude_detector_is_off_and_nothing_is_queued_for_it(db, thread, verified_landlord):
    enquiries.send_message(db, thread, verified_landlord, SCAM)
    queued = {j.detector for j in db.scalars(select(ScoreJob).where(ScoreJob.subject_type == "messages"))}
    assert queued == {"scam_text"}
    assert detection.mode(db, "scam_text_llm") == "off"


def test_claude_detector_scores_in_shadow_beside_the_in_house_model(db, monkeypatch, thread, verified_landlord):
    from app.modules.detection.detectors import ScamTextLLM

    set_mode(monkeypatch, "scam_text_llm", "shadow")
    monkeypatch.setattr(ScamTextLLM, "make_model", lambda self: FakeClaude(91))
    message = enquiries.send_message(db, thread, verified_landlord, SCAM)
    detection.process_pending(db)
    scores = {
        s.detector: s
        for s in db.scalars(
            select(ModelScore).where(ModelScore.subject_type == "messages", ModelScore.subject_id == str(message.id))
        )
    }
    assert set(scores) == {"scam_text", "scam_text_llm"}
    llm = scores["scam_text_llm"]
    assert llm.score == 91 and llm.version == "claude-haiku-4-5" and llm.mode == "shadow" and not llm.acted


def test_claude_detector_failures_fail_its_jobs_only(db, monkeypatch, thread, verified_landlord):
    from app.modules.detection.detectors import ScamTextLLM

    set_mode(monkeypatch, "scam_text_llm", "shadow")
    monkeypatch.setattr(
        ScamTextLLM, "make_model", lambda self: FakeClaude(error="AFE_ANTHROPIC_API_KEY is not set")
    )
    enquiries.send_message(db, thread, verified_landlord, SCAM)
    for _ in range(3):
        detection.process_pending(db)
    jobs = {j.detector: j for j in db.scalars(select(ScoreJob).where(ScoreJob.subject_type == "messages"))}
    assert jobs["scam_text_llm"].status == JobStatus.FAILED
    assert "AFE_ANTHROPIC_API_KEY" in jobs["scam_text_llm"].error
    assert jobs["scam_text"].status == JobStatus.DONE


def test_claude_jobs_are_capped_per_run(db, monkeypatch, thread, verified_landlord):
    from app.modules.detection.detectors import ScamTextLLM

    set_mode(monkeypatch, "scam_text_llm", "shadow")
    monkeypatch.setattr(ScamTextLLM, "make_model", lambda self: FakeClaude(12))
    monkeypatch.setitem(detection.PER_RUN, "scam_text_llm", 2)
    for i in range(3):
        enquiries.send_message(db, thread, verified_landlord, f"Is it still free on Saturday? ({i})")

    def waiting():
        return len(db.scalars(select(ScoreJob).where(ScoreJob.detector == "scam_text_llm",
                                                     ScoreJob.status == JobStatus.PENDING)).all())

    counts = detection.process_pending(db)
    assert counts["deferred"] == 1 and waiting() == 1  # the rest wait for the next run
    detection.process_pending(db)
    assert waiting() == 0


def test_submitted_listings_are_queued_for_both_wording_detectors(db, monkeypatch, verified_unit, verified_landlord):
    set_mode(monkeypatch, "scam_text_llm", "shadow")
    listing = make_listing(db, verified_unit, verified_landlord)
    submit_for_review(db, listing, verified_landlord)
    queued = {j.detector for j in db.scalars(select(ScoreJob).where(ScoreJob.subject_type == "listings"))}
    assert {"scam_text", "scam_text_llm", "price"} <= queued


def test_claude_detector_is_judged_against_the_same_rules():
    from app.modules.detection.detectors import REGISTRY

    assert REGISTRY["scam_text_llm"].rule_prefixes == REGISTRY["scam_text"].rule_prefixes
    assert len("scam_text_llm") <= 20  # fits ModelScore.detector and ScoreJob.detector


# --- Price and photos ---------------------------------------------------------------------------------------


def test_price_model_scores_bait_prices(db, verified_unit, verified_landlord):
    bait = make_listing(db, verified_unit, verified_landlord, rent_pesewas=150_000)  # band median is 500,000
    submit_for_review(db, bait, verified_landlord)
    detection.process_pending(db)
    score = db.scalar(select(ModelScore).where(ModelScore.detector == "price"))
    assert score.score >= 90 and "30% of the usual" in score.reasons[0]


def test_rent_scoring_is_a_pure_function(db, area):
    from app.modules.detection.detectors import reference_rent, score_rent

    ref = reference_rent(db, area.id, 2)
    assert ref == (500_000, "Afe's price survey", "price-band-1")
    bait, fair = score_rent(150_000, *ref), score_rent(480_000, *ref)
    assert bait.score >= 90 and fair.score <= 10
    assert "30% of the usual" in bait.reasons[0]
    assert reference_rent(db, area.id, 5) is None  # no survey band for 5 bedrooms


def test_photo_model_scores_a_copied_home(db, area, unit, landlord, verifier):
    other = register_unit(db, landlord, area, "GA-418-3310", "", 5.6331, -0.1662, "house", 2)
    first = begin_visit(db, unit, verifier)
    add_visit_photo(db, first, verifier, photo_bytes(7), *unit.point, utcnow())
    second = begin_visit(db, other, verifier)
    add_visit_photo(db, second, verifier, photo_bytes(7, fmt="PNG"), *other.point, utcnow())
    complete_visit(db, second, verifier, {"unit_exists": True})
    detection.process_pending(db)
    score = db.scalar(select(ModelScore).where(ModelScore.detector == "photos", ModelScore.subject_id == str(other.id)))
    assert score.score >= 90


# --- Linked accounts ------------------------------------------------------------------------------------------


def test_accounts_linked_to_known_fraud(db, landlord, reviewer):
    other = make_user(db, "impostor", Role.AGENT)
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    check_ghana_card(db, other, "GHA-712345678-3", other.name, selfie=b"s")
    label(db, other, fraud=True, source="verification", decided_by=reviewer)
    counts = detection.run_graph(db)
    assert counts == {"edges": 1, "accounts_queued": 2}
    edge = db.scalar(select(LinkEdge))
    assert edge.kind == "ghana_card" and "712345678" not in edge.evidence
    detection.process_pending(db)
    score = db.scalar(select(ModelScore).where(ModelScore.detector == "accounts", ModelScore.subject_id == str(landlord.id)))
    assert score.score >= 70 and any("already found to be fraudulent" in r for r in score.reasons)


# --- Labels ------------------------------------------------------------------------------------------------------


def labels_for(db, subject_type, subject_id):
    return [
        (row.outcome, row.source)
        for row in db.scalars(
            select(DetectionLabel).where(DetectionLabel.subject_type == subject_type, DetectionLabel.subject_id == str(subject_id))
        )
    ]


def test_reviewer_decisions_become_labels(db, landlord, reviewer):
    other = make_user(db, "kojo", Role.LANDLORD)
    check_ghana_card(db, landlord, "GHA-712345678-3", landlord.name, selfie=b"s")
    decide_party(db, landlord, reviewer, True, ["ID_MATCH"])
    assert labels_for(db, "users", landlord.id) == [("legit", "verification")]

    check_ghana_card(db, other, "GHA-712345679-1", other.name, selfie=b"s")
    decide_party(db, other, reviewer, False, ["DOCS_MISSING"], "No documents at all")
    assert labels_for(db, "users", other.id) == []  # missing paperwork isn't evidence of fraud
    decide_party(db, other, reviewer, False, ["ID_MISMATCH"], "Face does not match the card")
    assert labels_for(db, "users", other.id) == [("fraud", "verification")]


def test_flag_resolutions_and_publishing_become_labels(db, live, reviewer, verified_landlord):
    assert ("legit", "publish") in labels_for(db, "listings", live.id)
    flag = raise_flag(db, verified_landlord, "message.language.pay_before_viewing", "high", "Asked for a viewing fee")
    resolve_flag(db, flag, reviewer, True, "Confirmed with the renter")
    assert ("fraud", "flag") in labels_for(db, "users", verified_landlord.id)


def test_upheld_report_labels_and_flags_the_account(db, verified_landlord, reviewer):
    report = scamcheck.report(db, "He asked me to pay a viewing fee by momo", reported_phone="0244123456")
    scamcheck.decide_report(db, reviewer, report, True, "Renter sent screenshots of the chat")
    assert ("fraud", "report") in labels_for(db, "users", verified_landlord.id)
    assert "report.upheld" in [f.rule for f in open_flags(db, verified_landlord)]
    with pytest.raises(RuleViolation, match="already decided"):
        scamcheck.decide_report(db, reviewer, report, False, "Changed my mind about it")


# --- Evaluation and the promotion gate -----------------------------------------------------------------------------


def seed_evaluation(db, reviewer, n_fraud=10, n_legit=20, rule_catches=5):
    """Synthetic labelled cases: the model scores fraud 90 and genuine 10; the rules caught
    only some of the fraud."""
    for i in range(n_fraud + n_legit):
        fraud = i < n_fraud
        sid = str(10_000 + i)
        db.add(ModelScore(detector="price", version="price-band-1", subject_type="listings", subject_id=sid,
                          score=90 if fraud else 10, reasons=[], mode="shadow"))
        if fraud and i < rule_catches:
            db.add(RiskFlag(subject_type="listings", subject_id=sid, rule="price.far_below_area", severity="high",
                            explanation="rule"))
        db.flush()
        label_key(db, "listings", sid, fraud, "verification", reviewer)


def test_evaluation_compares_model_with_rules(db, reviewer):
    seed_evaluation(db, reviewer)
    report = detection.evaluate(db, "price")
    assert (report.labels, report.fraud) == (30, 10)
    assert report.model.precision == 1.0 and report.model.recall == 1.0
    assert report.rules.recall == 0.5
    assert report.promotable, report.reason


def test_too_few_labels_blocks_promotion(db, reviewer):
    seed_evaluation(db, reviewer, n_fraud=6, n_legit=6, rule_catches=3)
    report = detection.evaluate(db, "price")
    assert not report.promotable and "needs 30" in report.reason
    with pytest.raises(RuleViolation, match="can't leave shadow"):
        compliance.propose(db, reviewer, "model_price_mode", "canary", "Try it on real listings")


def test_promotion_needs_a_passing_evaluation_and_a_second_reviewer(db, reviewer):
    seed_evaluation(db, reviewer)
    second = make_user(db, "reviewer2", Role.REVIEWER)
    row = compliance.propose(db, reviewer, "model_price_mode", "canary", "Beats the price rule on 30 labels")
    with pytest.raises(RuleViolation):
        compliance.approve(db, row, reviewer)
    compliance.approve(db, row, second)
    assert detection.mode(db, "price") == "canary"
    with pytest.raises(Exception, match="Choose one of"):
        compliance.propose(db, reviewer, "model_price_mode", "turbo", "Not a real mode")


def test_training_needs_enough_labelled_text(db, reviewer):
    with pytest.raises(RuleViolation, match="Not enough labelled text"):
        detection.train_text(db, reviewer)


# --- API ----------------------------------------------------------------------------------------------------------


def test_detection_over_the_api(client, db, verified_landlord, reviewer):
    report = scamcheck.report(db, "Asked for a commitment fee before viewing", reported_phone="0244123456")
    db.flush()
    h = api_login(client, "reviewer")
    detectors = client.get("/api/v1/review/detection", headers=h).json()["data"]
    assert {d["name"] for d in detectors} == {"scam_text", "scam_text_llm", "price", "photos", "documents", "accounts"}
    modes = {d["name"]: d["mode"] for d in detectors}
    assert modes.pop("scam_text_llm") == "off"  # off until counsel clears sending text abroad (B11)
    assert set(modes.values()) == {"shadow"}

    reports = client.get("/api/v1/review/reports", headers=h).json()["data"]
    assert reports[0]["matched_user_name"] == verified_landlord.name
    res = client.post(f"/api/v1/review/reports/{report.id}/decision", headers=h,
                      json={"upheld": True, "note": "Screenshots confirm the request"})
    assert res.json()["data"]["status"] == "upheld"

    person = client.get(f"/api/v1/review/people/{verified_landlord.id}", headers=h).json()["data"]
    assert "model_notes" in person and "links" in person
    assert client.post("/api/v1/review/detection/scam_text/train", headers=h).status_code == 409
