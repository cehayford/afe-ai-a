# AI Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get Afe's fraud-detection models ready to be judged on real cases. The Claude classifier moves onto the official SDK and becomes a detector of its own, scoring in shadow. A seeded test set of fake listings measures recall. A weekly report keeps every model's numbers and retrains the in-house wording model while it is still in shadow.

**Architecture:** Everything stays inside `backend/app/modules/detection`, plus one new API route and one new section on the existing reviewer Models page. The Claude classifier becomes its own detector (`scam_text_llm`), switched off by default, so it is scored and evaluated beside the in-house model instead of replacing it. Seeded cases are scored in memory, never written as listings, so they can't reach the site or the training data. Weekly snapshots go into one new table, keyed by detector and ISO week.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pytest, the `anthropic` Python SDK (structured outputs via `client.messages.parse`), SvelteKit 2 with Svelte 5 for the page change.

**Spec:**
- The Afe Trust Engine page: https://claude.ai/artifact/5DF5kN6Zb26MrVV9mXabfm. This plan covers "Step by step": Stage 0 items 3, 5 and 6, and Stage 1 items 1–3.
- The build plan, `docs/Afe_Build_Plan.html` §7 (AI and detection).

**Scope:** this is plan 1 of 3 for the AI work. Each later plan is written once this one ships, because both build on the SDK client and the evaluation snapshots made here.
- **Plan 2:** the agent platform (gateway, orchestrator on the SDK Tool Runner, a tool registry with read, propose and act scopes, run traces, and a human review queue), with the Reviewer copilot in shadow.
- **Plan 3:** the WhatsApp scam-check assistant and the document examiner.

Photo and document cases in the seeded set need image and PDF fixtures, so they wait for plan 3.

## Global Constraints

- **How to run things:** run every command from `backend/` with the project venv: `.venv/Scripts/python` on Windows, `.venv/bin/python` elsewhere.
- **Calling Claude:** only through the official `anthropic` Python SDK. No raw HTTP.
- **Model ID:** exactly `claude-haiku-4-5`, with no date suffix.
- **Redaction:** text sent to any outside model goes through `app.modules.detection.text.redact()` first.
- **Starting modes:** new detectors start `off` or `shadow`. A mode changes only through the two-reviewer rules flow (`compliance.propose`, then `compliance.approve` by a different reviewer).
- **What a model may do:** raise a flag, nothing more. It never rejects a verification, bans a person, or holds, releases or refunds money.
- **Detector names:** 20 characters at most, because `ModelScore.detector` and `ScoreJob.detector` are `String(20)`.
- **Lint:** `ruff check app tests` passes (line length 120).
- **Migrations:** they must match the models, so `pytest tests/test_flows.py::test_migrations_match_the_models` passes.
- **Frontend:** `npx svelte-check --threshold error` reports 0 errors. Page styles must not reuse class names defined in `frontend/src/app.css` (see "Gotchas" in `.claude/skills/run-afe/SKILL.md`).
- **Copy:** user-facing text is plain English in sentence case, like the rest of the back office.

## Review Focus

1. **Claude replies with no parsed verdict** (a refusal, `max_tokens`, or invalid output). The job raises, retries and then fails. It is never stored as a score of 0. Tested in Task 1.
2. **The Claude detector is switched on but `AFE_ANTHROPIC_API_KEY` is empty.** Its jobs fail with an error that names the setting, while the in-house detector's jobs still finish. Tested in Task 2.
3. **The team's seeded file has a mistake** (bad `kind`, repeated `id`, unknown field, missing field). Loading stops with a message that names the case. A case whose area isn't in the database skips only the price check and is counted as skipped. Tested in Task 4.
4. **The weekly job runs while the wording model is in canary or active.** It must not train a new version automatically, because the new version would act before anyone judged it. Tested in Task 6.
5. **The weekly job runs twice in one ISO week** (a worker restart, or both the worker and EventBridge). There is still one snapshot per detector for that week (updated, not duplicated), reviewers are told once, and there is at most one training run. Tested in Tasks 5 and 6.

---

### Task 1: Claude classifier on the official SDK with structured output

**Files:**
- Modify: `backend/requirements.txt` (Runtime block)
- Modify: `backend/app/config.py:96` (`anthropic_model` default)
- Modify: `backend/app/modules/detection/text.py` (imports at lines 11–20, `_PROMPT` and `ClaudeTextModel` at lines 143–183)
- Test: `backend/tests/test_detection_llm.py` (create)

**Interfaces:**
- Consumes: `redact(text) -> str` and `TextScore(score, reasons, version)` from `app/modules/detection/text.py`, both unchanged.
- Produces:
  - `Verdict`, a pydantic model with `score: int` and `reasons: list[str]`.
  - `ClaudeTextModel(trained=None, client=None)`, whose `.score(text: str) -> TextScore` raises `RuntimeError` when there is no verdict.
  - `get_settings().anthropic_model` defaults to `"claude-haiku-4-5"`.

- [ ] **Step 1: Install the SDK and pin it**

Run:
```bash
.venv/Scripts/pip install anthropic
.venv/Scripts/pip show anthropic
```
Add a line to the `# Runtime` block of `backend/requirements.txt` that pins the major version `pip show` printed. For example, for `Version: 1.4.0`:
```
anthropic>=1.4,<2
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_detection_llm.py`:
```python
"""The Claude wording classifier: the official SDK, structured output, redaction, and failures that
retry instead of scoring zero."""

from types import SimpleNamespace

import pytest

from app.config import Settings, get_settings
from app.modules.detection.text import ClaudeTextModel, Verdict

SCAM = "Pay GH₵500 viewing fee first. Send momo to 0244999888 or mail ama@example.com today only"


class FakeMessages:
    def __init__(self, verdict=None, stop_reason="end_turn"):
        self.verdict, self.stop_reason, self.calls = verdict, stop_reason, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self.verdict, stop_reason=self.stop_reason)


def fake_client(**kwargs):
    return SimpleNamespace(messages=FakeMessages(**kwargs))


def test_the_default_model_is_haiku_4_5():
    assert Settings.model_fields["anthropic_model"].default == "claude-haiku-4-5"


def test_sends_only_redacted_text_and_reads_the_verdict():
    reasons = ["Asks for a viewing fee", "Moves payment to MoMo", "Urgency", "A fourth reason"]
    client = fake_client(verdict=Verdict(score=87, reasons=reasons))
    result = ClaudeTextModel(client=client).score(SCAM)
    assert result.score == 87
    assert result.reasons == reasons[:3]
    assert result.version == get_settings().anthropic_model
    call = client.messages.calls[0]
    assert call["model"] == get_settings().anthropic_model and call["output_format"] is Verdict
    sent = call["messages"][0]["content"]
    assert "0244999888" not in sent and "ama@example.com" not in sent
    assert "[phone]" in sent and "[email]" in sent


@pytest.mark.parametrize(("raw", "kept"), [(140, 100), (-5, 0)])
def test_scores_are_kept_between_0_and_100(raw, kept):
    result = ClaudeTextModel(client=fake_client(verdict=Verdict(score=raw, reasons=[]))).score("hello")
    assert result.score == kept


def test_no_verdict_is_an_error_not_a_zero():
    model = ClaudeTextModel(client=fake_client(verdict=None, stop_reason="refusal"))
    with pytest.raises(RuntimeError, match="no verdict.*refusal"):
        model.score(SCAM)


def test_needs_a_key_when_no_client_is_given(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    with pytest.raises(RuntimeError, match="AFE_ANTHROPIC_API_KEY"):
        ClaudeTextModel()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_detection_llm.py -q -p no:cacheprovider`
Expected: collection fails with `ImportError: cannot import name 'Verdict' from 'app.modules.detection.text'`.

- [ ] **Step 4: Change the default model ID**

In `backend/app/config.py` replace:
```python
    anthropic_model: str = "claude-haiku-4-5-20251001"
```
with:
```python
    anthropic_model: str = "claude-haiku-4-5"
```

- [ ] **Step 5: Rewrite the classifier on the SDK**

In `backend/app/modules/detection/text.py`, replace the import block:
```python
import importlib
import json
import math
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass

from app.config import get_settings
from app.modules.risk.rules import scam_language
```
with:
```python
import importlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel

from app.config import get_settings
from app.modules.risk.rules import scam_language
```

Then replace everything from `_PROMPT = """You check rental listings` down to the end of `class ClaudeTextModel` (the line `        return TextScore(score, reasons, self.model)`) with:
```python
_PROMPT = """You check rental listings and messages in Accra, Ghana, for scams. Common scams: asking for \
money before a viewing ("viewing fee", "commitment fee", "send momo first"), moving the chat or payment off \
the platform (WhatsApp, direct MoMo), urgency and pressure, fake agents, and prices far below the area. \
Ghanaian English, Pidgin and Twi may be mixed. Personal details are masked as [phone], [email], [number].

Give a score from 0 to 100 for how likely this is a scam attempt, and up to 3 short reasons in plain English."""


class Verdict(BaseModel):
    """The shape Claude must answer in (structured output), so a reply is never free text."""

    score: int
    reasons: list[str]


class ClaudeTextModel:
    """The LLM classifier, called through the official Anthropic SDK. Text is redacted before it
    leaves Afe. Use it only after counsel clears sending redacted text to a processor abroad
    (Act 843, build plan B11). `client` is for tests; normally the SDK client is built here."""

    def __init__(self, trained=None, client=None):
        settings = get_settings()
        self.model = settings.anthropic_model
        if client is None:
            if not settings.anthropic_api_key:
                raise RuntimeError("AFE_ANTHROPIC_API_KEY is not set")
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=30.0, max_retries=2)
        self.client = client

    def score(self, text: str) -> TextScore:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=400,
            system=_PROMPT,
            messages=[{"role": "user", "content": redact(text)[:4000]}],
            output_format=Verdict,
        )
        verdict = response.parsed_output
        if verdict is None:
            # A refusal or a cut-off reply: fail the job so it is retried, never score it 0.
            raise RuntimeError(f"Claude gave no verdict (stop reason: {response.stop_reason})")
        score = max(0, min(100, int(verdict.score)))
        reasons = [str(r)[:160] for r in verdict.reasons][:3]
        return TextScore(score, reasons, self.model)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_detection_llm.py tests/test_detection.py -q -p no:cacheprovider`
Expected: all pass. The existing detection tests are unaffected because they use `HeuristicTextModel`.

- [ ] **Step 7: Lint**

Run: `.venv/Scripts/python -m ruff check app tests`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add requirements.txt app/config.py app/modules/detection/text.py tests/test_detection_llm.py
git commit -m "feat(detection): Claude classifier on the official SDK with structured output" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The Claude classifier as its own detector, off by default

**Files:**
- Modify: `backend/app/modules/detection/detectors.py`: the `.text` import at line 28, a new class after `ScamText` (after line 119), and `REGISTRY` at line 369
- Modify: `backend/app/modules/compliance/service.py:103-120` (`_DETECTOR_RULES` and its loop)
- Modify: `backend/app/modules/detection/hooks.py` (add `enqueue_text` after `enqueue`)
- Modify: `backend/app/modules/listings/service.py:68` (and its `hooks` import)
- Modify: `backend/app/modules/enquiries/service.py:140` (and its `hooks` import)
- Modify: `backend/app/modules/detection/text.py:1-9` (module docstring)
- Modify: `frontend/src/routes/review/detection/+page.server.ts:6` (`NAMES`)
- Test: `backend/tests/test_detection.py` (new tests at the end of the "Queue and shadow mode" section, and an update to `test_detection_over_the_api`)

**Interfaces:**
- Consumes: `ClaudeTextModel()` and `TextScore` from Task 1.
- Produces:
  - `ScamTextLLM`: detector name `"scam_text_llm"`, with a `make_model()` method that returns a `ClaudeTextModel`.
  - `REGISTRY["scam_text_llm"]`.
  - Rule keys `model_scam_text_llm_mode` (default `"off"`) and `model_scam_text_llm_threshold` (default `80`).
  - `enqueue_text(db, subject) -> None` in `app.modules.detection.hooks`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_detection.py`, add `TextScore` to the existing text import:
```python
from app.modules.detection.text import HeuristicTextModel, TextScore, redact, train_naive_bayes
```
Add these tests after `test_a_failing_model_is_retried_then_marked_failed`:
```python
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
```
In `test_detection_over_the_api`, replace:
```python
    assert {d["name"] for d in detectors} == {"scam_text", "price", "photos", "documents", "accounts"}
    assert all(d["mode"] == "shadow" for d in detectors)
```
with:
```python
    assert {d["name"] for d in detectors} == {"scam_text", "scam_text_llm", "price", "photos", "documents", "accounts"}
    modes = {d["name"]: d["mode"] for d in detectors}
    assert modes.pop("scam_text_llm") == "off"  # off until counsel clears sending text abroad (B11)
    assert set(modes.values()) == {"shadow"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_detection.py -q -p no:cacheprovider`
Expected: the new tests fail with `KeyError: 'model_scam_text_llm_mode'` or `ImportError: cannot import name 'ScamTextLLM'`, and `test_detection_over_the_api` fails on the detector set.

- [ ] **Step 3: Add the rule defaults**

In `backend/app/modules/compliance/service.py`, replace:
```python
_DETECTOR_RULES = {
    "scam_text": ("Scam wording in listings and messages", 80),
    "price": ("Price far below the area", 85),
    "photos": ("Photos matching another home", 80),
    "documents": ("Signs a document was edited", 70),
    "accounts": ("Accounts linked to known fraud", 70),
}
for _name, (_label, _threshold) in _DETECTOR_RULES.items():
    RULES[f"model_{_name}_mode"] = RuleDef(
        "shadow", str, f"Model mode: {_label}", "Build plan §7: shadow first; off, shadow, canary or active.",
        choices=MODEL_MODES,
    )
```
with:
```python
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
```
Leave the `model_{_name}_threshold` lines that follow unchanged.

- [ ] **Step 4: Add the detector**

In `backend/app/modules/detection/detectors.py`, change:
```python
from .text import get_text_model
```
to:
```python
from .text import ClaudeTextModel, get_text_model
```
Add this class right after the end of `class ScamText` (after its `score_for_label` method):
```python
class ScamTextLLM(ScamText):
    """The same job as ScamText, done by Claude on redacted text. It's a separate detector so it
    is scored and evaluated beside the in-house model instead of replacing it. Off until counsel
    clears sending redacted text abroad (B11); turning it on is a rule change two reviewers make."""

    name = "scam_text_llm"
    label = "Scam wording (Claude, redacted text)"

    def make_model(self):
        return ClaudeTextModel()

    def score(self, db, subject) -> Scored:
        text = f"{subject.title}\n{subject.description}" if isinstance(subject, Listing) else subject.body
        result = self.make_model().score(text)
        return Scored(result.score, result.reasons, result.version)
```
Change the registry to:
```python
REGISTRY: dict[str, Detector] = {
    d.name: d for d in (ScamText(), ScamTextLLM(), Price(), Photos(), Documents(), Accounts())
}
```

- [ ] **Step 5: Queue wording for both detectors from one helper**

In `backend/app/modules/detection/hooks.py`, add after `def enqueue(...)`:
```python
def enqueue_text(db: Session, subject) -> None:
    """Queue a listing or message for the wording detectors: the in-house model always, and the
    Claude detector only while its mode isn't off, so nothing is queued to leave Afe by default."""
    from app.modules.compliance.service import rule

    enqueue(db, "scam_text", subject)
    if rule(db, "model_scam_text_llm_mode") != "off":
        enqueue(db, "scam_text_llm", subject)
```
In `backend/app/modules/listings/service.py`, change `enqueue(db, "scam_text", listing)` to `enqueue_text(db, listing)`, and add `enqueue_text` to the file's existing `from app.modules.detection.hooks import ...` line.
In `backend/app/modules/enquiries/service.py`, change `enqueue(db, "scam_text", message)` to `enqueue_text(db, message)`, and do the same import change.

- [ ] **Step 6: Update the text module's docstring**

In `backend/app/modules/detection/text.py`, replace the bullet:
```
- optionally an LLM classifier (`AFE_TEXT_MODEL=app.modules.detection.text.ClaudeTextModel`).
  Text is redacted before it leaves Afe: phone numbers, emails and long digit runs are masked.
```
with:
```
- `ClaudeTextModel`, used by the separate `scam_text_llm` detector (off until counsel clears B11),
  so the LLM is evaluated beside the in-house model. Text is redacted before it leaves Afe.
```

- [ ] **Step 7: Let reviewers change the new detector's mode**

In `frontend/src/routes/review/detection/+page.server.ts` replace:
```ts
const NAMES = /^(scam_text|price|photos|documents|accounts)$/;
```
with:
```ts
const NAMES = /^(scam_text|scam_text_llm|price|photos|documents|accounts)$/;
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_detection.py tests/test_detection_llm.py tests/test_listings.py tests/test_enquiries.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 9: Lint and type-check**

Run: `.venv/Scripts/python -m ruff check app tests`, then from `frontend/`: `npx svelte-check --threshold error`.
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add app/modules/detection app/modules/compliance/service.py app/modules/listings/service.py app/modules/enquiries/service.py tests/test_detection.py ../frontend/src/routes/review/detection/+page.server.ts
git commit -m "feat(detection): Claude wording detector in its own lane, off by default" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Price scoring as a pure function

**Files:**
- Modify: `backend/app/modules/detection/detectors.py` (the `Price` class and the lines before it)
- Test: `backend/tests/test_detection.py` (new test after `test_price_model_scores_bait_prices`)

**Interfaces:**
- Produces:
  - `reference_rent(db, area_id: int, bedrooms: int, exclude_listing_id: int | None = None)`, which returns `tuple[float, str, str] | None`: the usual rent in pesewas, where it came from, and the version.
  - `score_rent(rent_pesewas: int, reference: float, source: str, version: str) -> Scored`.
  - `Price.score` keeps its behaviour exactly.

- [ ] **Step 1: Write the failing test**

Add after `test_price_model_scores_bait_prices` in `backend/tests/test_detection.py`:
```python
def test_rent_scoring_is_a_pure_function(db, area):
    from app.modules.detection.detectors import reference_rent, score_rent

    ref = reference_rent(db, area.id, 2)
    assert ref == (500_000, "Afe's price survey", "price-band-1")
    bait, fair = score_rent(150_000, *ref), score_rent(480_000, *ref)
    assert bait.score >= 90 and fair.score <= 10
    assert "30% of the usual" in bait.reasons[0]
    assert reference_rent(db, area.id, 5) is None  # no survey band for 5 bedrooms
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_detection.py::test_rent_scoring_is_a_pure_function -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'reference_rent'`.

- [ ] **Step 3: Extract the two functions**

In `backend/app/modules/detection/detectors.py`, add these right after `MIN_COMPARABLES = 8`:
```python
def reference_rent(db: Session, area_id: int, bedrooms: int, exclude_listing_id: int | None = None):
    """The usual rent for homes like this: the median of Afe's verified listings once there are
    enough, else the manual price survey. Returns (pesewas, where it came from, version), or None."""
    query = (
        select(Listing.rent_pesewas)
        .join(Listing.unit)
        .where(
            Unit.area_id == area_id,
            Unit.bedrooms == bedrooms,
            Listing.status.in_([ListingStatus.LIVE, ListingStatus.LET]),
        )
    )
    if exclude_listing_id is not None:
        query = query.where(Listing.id != exclude_listing_id)
    rents = list(db.scalars(query))
    if len(rents) >= MIN_COMPARABLES:
        return statistics.median(rents), f"{len(rents)} verified listings like it on Afe", "price-own-1"
    band = db.scalar(
        select(PriceBand)
        .where(PriceBand.area_id == area_id, PriceBand.bedrooms == bedrooms)
        .order_by(PriceBand.as_of.desc())
    )
    if band is None:
        return None
    return band.median_pesewas, "Afe's price survey", "price-band-1"


def score_rent(rent_pesewas: int, reference: float, source: str, version: str) -> Scored:
    position = rent_pesewas / reference
    score = round(_sigmoid(12 * (0.55 - position)) * 100)
    reasons = [
        f"Rent {format_ghs(rent_pesewas)} is {round(position * 100)}% of the usual "
        f"{format_ghs(round(reference))} ({source})"
    ]
    return Scored(score, reasons, version)
```
Replace the whole body of `Price.score` with:
```python
    def score(self, db, listing) -> Scored:
        unit = listing.unit
        ref = reference_rent(db, unit.area_id, unit.bedrooms, exclude_listing_id=listing.id)
        if ref is None:
            return Scored(0, ["No price data for this area and size yet"], "price-band-1")
        return score_rent(listing.rent_pesewas, *ref)
```

- [ ] **Step 4: Run the price tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_detection.py -q -p no:cacheprovider -k "price or rent"`
Expected: PASS, including the unchanged `test_price_model_scores_bait_prices`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/detection/detectors.py tests/test_detection.py
git commit -m "refactor(detection): price scoring as a pure function for the seeded set" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The seeded test set

**Files:**
- Create: `backend/app/modules/detection/seeded.py`
- Create: `backend/app/modules/detection/seeded_cases.json`
- Modify: `backend/app/cli.py` (docstring, a new sub-parser, a new dispatch branch)
- Test: `backend/tests/test_detection_seeded.py` (create)

**Interfaces:**
- Consumes:
  - `ScamTextLLM.make_model()` and `REGISTRY` (Task 2).
  - `reference_rent` and `score_rent` (Task 3).
  - `Tally`, `mode` and `threshold` from `app.modules.detection.service`.
  - `scam_language(text)` and `price_anomaly(db, rent_pesewas, area, bedrooms)` from `app.modules.risk.rules`.
- Produces:
  - `DEFAULT_PATH: Path`.
  - `SeededCase`, with the fields `id, kind, title, description, rent_ghs, bedrooms, area, tactic` and the properties `.fraud` and `.text`.
  - `load_cases(path=DEFAULT_PATH) -> list[SeededCase]`, which raises `InvalidInput`.
  - `SeededResult`, with the fields `detector, cases, fraud, skipped, model: Tally, rules: Tally, missed: list[str]` and the method `.as_dict() -> dict`.
  - `evaluate_seeded(db, cases) -> list[SeededResult]`.
  - The CLI command `python -m app.cli eval-seeded [--file PATH]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_detection_seeded.py`:
```python
"""The seeded test set: fake and genuine listings the team writes, scored in memory the way the
detectors score real listings, so recall can be measured before real fraud exists."""

import dataclasses
import json

import pytest

from app.core.errors import InvalidInput
from app.modules.compliance import service as compliance
from app.modules.detection.seeded import DEFAULT_PATH, evaluate_seeded, load_cases

FAKE = {
    "id": "fake-1", "kind": "fraud", "title": "2-bedroom flat, East Legon",
    "description": "Pay GH₵500 viewing fee first by momo, then I show you. Today only.",
    "rent_ghs": 1500, "bedrooms": 2, "area": "east-legon", "tactic": "viewing fee and bait price",
}
REAL = {
    "id": "real-1", "kind": "genuine", "title": "2-bedroom flat, East Legon",
    "description": "Quiet compound with a water tank. Viewing on Saturday afternoon.",
    "rent_ghs": 4800, "bedrooms": 2, "area": "east-legon",
}


def write(tmp_path, cases):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    return path


def test_the_starter_set_loads():
    cases = load_cases(DEFAULT_PATH)
    assert len(cases) >= 12
    assert {c.kind for c in cases} == {"fraud", "genuine"}
    assert len({c.id for c in cases}) == len(cases)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"kind": "maybe"}, "fake-1: kind must be fraud or genuine"),
        ({"rent_ghs": 0}, "fake-1: rent_ghs must be a positive number"),
        ({"bedrooms": 2.5}, "fake-1: bedrooms must be a whole number"),
        ({"colour": "red"}, "fake-1: unknown field colour"),
    ],
)
def test_mistakes_name_the_case(tmp_path, change, message):
    with pytest.raises(InvalidInput, match=message):
        load_cases(write(tmp_path, [{**FAKE, **change}]))


def test_missing_fields_and_repeated_ids_are_refused(tmp_path):
    with pytest.raises(InvalidInput, match="fake-1: missing area"):
        load_cases(write(tmp_path, [{k: v for k, v in FAKE.items() if k != "area"}]))
    with pytest.raises(InvalidInput, match="fake-1: this id is used twice"):
        load_cases(write(tmp_path, [FAKE, FAKE]))


def test_seeded_cases_are_scored_like_real_listings(db, area, tmp_path):
    results = {r.detector: r for r in evaluate_seeded(db, load_cases(write(tmp_path, [FAKE, REAL])))}
    assert set(results) == {"scam_text", "price"}  # the Claude detector is off
    wording, price = results["scam_text"], results["price"]
    assert (wording.cases, wording.fraud) == (2, 1)
    assert wording.model.recall == 1.0 and wording.model.fp == 0 and wording.missed == []
    assert wording.rules.recall == 1.0
    assert price.model.tp == 1 and price.model.fp == 0
    assert price.rules.tp == 1  # GH₵1,500 is under 60% of the survey's low of GH₵3,500


def test_an_unknown_area_skips_only_the_price_check(db, area, tmp_path):
    lost = {**FAKE, "id": "fake-2", "area": "atlantis"}
    results = {r.detector: r for r in evaluate_seeded(db, load_cases(write(tmp_path, [lost])))}
    assert results["scam_text"].cases == 1
    assert results["price"].skipped == 1 and results["price"].cases == 0


def test_claude_failures_are_counted_as_skipped(db, area, tmp_path, monkeypatch):
    from app.modules.detection.detectors import ScamTextLLM

    key = "model_scam_text_llm_mode"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default="shadow"))

    class Down:
        def score(self, text):
            raise RuntimeError("provider down")

    monkeypatch.setattr(ScamTextLLM, "make_model", lambda self: Down())
    results = {r.detector: r for r in evaluate_seeded(db, load_cases(write(tmp_path, [FAKE, REAL])))}
    assert results["scam_text_llm"].skipped == 2 and results["scam_text_llm"].cases == 0
    assert results["scam_text"].cases == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_detection_seeded.py -q -p no:cacheprovider`
Expected: collection fails with `ModuleNotFoundError: No module named 'app.modules.detection.seeded'`.

- [ ] **Step 3: Write the starter set**

Create `backend/app/modules/detection/seeded_cases.json`. It holds 12 starter cases; the team extends it to 50 (Trust Engine, Stage 0 item 3):
```json
[
  {"id": "fake-001", "kind": "fraud", "area": "east-legon", "bedrooms": 2, "rent_ghs": 1500,
   "title": "2-bedroom flat, East Legon", "tactic": "viewing fee, bait price",
   "description": "Pay GH₵300 viewing fee first by momo, then I show you the flat. Many people want it."},
  {"id": "fake-002", "kind": "fraud", "area": "madina-adenta", "bedrooms": 1, "rent_ghs": 1400,
   "title": "Self-contained, Madina", "tactic": "owner abroad, pay before viewing",
   "description": "Owner is abroad. Send the commitment fee to my MoMo number and the caretaker will give you keys. Today only."},
  {"id": "fake-003", "kind": "fraud", "area": "east-legon", "bedrooms": 3, "rent_ghs": 2500,
   "title": "3-bedroom house, East Legon", "tactic": "bait price, off-platform chat",
   "description": "Very cheap because the owner is travelling. Chat me on WhatsApp 0244999888 to book."},
  {"id": "fake-004", "kind": "fraud", "area": "madina-adenta", "bedrooms": 2, "rent_ghs": 2600,
   "title": "2-bedroom flat near Adenta", "tactic": "deposit before viewing",
   "description": "Send a deposit of GH₵1,000 to reserve before viewing. Transfer to my account number."},
  {"id": "fake-005", "kind": "fraud", "area": "east-legon", "bedrooms": 1, "rent_ghs": 900,
   "title": "Newly built 1-bedroom", "tactic": "agent fee for the address, bait price",
   "description": "Newly built. Pay the agent fee of GH₵200 first to get the address."},
  {"id": "fake-006", "kind": "fraud", "area": "madina-adenta", "bedrooms": 0, "rent_ghs": 250,
   "title": "Chamber and hall, Madina", "tactic": "reservation fee, urgency, bait price",
   "description": "Chamber and hall. Hurry, pay the reservation fee now by momo before it goes."},
  {"id": "real-001", "kind": "genuine", "area": "east-legon", "bedrooms": 2, "rent_ghs": 4800,
   "title": "2-bedroom flat, East Legon", "tactic": "",
   "description": "Quiet compound with a water tank and parking. Viewing on Saturday afternoon."},
  {"id": "real-002", "kind": "genuine", "area": "madina-adenta", "bedrooms": 1, "rent_ghs": 1500,
   "title": "Self-contained, Madina", "tactic": "",
   "description": "Self-contained, close to the university road. Prepaid meter. Book a viewing on Afe."},
  {"id": "real-003", "kind": "genuine", "area": "east-legon", "bedrooms": 3, "rent_ghs": 8500,
   "title": "3-bedroom house, East Legon", "tactic": "",
   "description": "Family house with a small garden and security. A two-year lease is preferred."},
  {"id": "real-004", "kind": "genuine", "area": "madina-adenta", "bedrooms": 2, "rent_ghs": 2500,
   "title": "2-bedroom flat near Adenta", "tactic": "",
   "description": "Second-floor flat with borehole water, near the Adenta barrier."},
  {"id": "real-005", "kind": "genuine", "area": "east-legon", "bedrooms": 1, "rent_ghs": 3000,
   "title": "1-bedroom flat, East Legon", "tactic": "",
   "description": "Newly painted with a fitted kitchen. Walking distance to the shopping mall."},
  {"id": "real-006", "kind": "genuine", "area": "madina-adenta", "bedrooms": 0, "rent_ghs": 800,
   "title": "Chamber and hall, Madina", "tactic": "",
   "description": "Chamber and hall with a porch in a shared compound with quiet neighbours."}
]
```

- [ ] **Step 4: Write the loader and the evaluator**

Create `backend/app/modules/detection/seeded.py`:
```python
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
        if item["id"] in seen:
            raise InvalidInput(f"{name}: this id is used twice.")
        if item["kind"] not in KINDS:
            raise InvalidInput(f"{name}: kind must be fraud or genuine.")
        if not isinstance(item["rent_ghs"], int | float) or item["rent_ghs"] <= 0:
            raise InvalidInput(f"{name}: rent_ghs must be a positive number.")
        if not isinstance(item["bedrooms"], int) or not 0 <= item["bedrooms"] <= 10:
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_detection_seeded.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 6: Add the CLI command**

In `backend/app/cli.py`, add this to the docstring after the `train-text` line:
```
eval-seeded    score the seeded test set of fake and genuine listings; prints recall and misses
```
Add after `sub.add_parser("train-text", ...)`:
```python
    seeded = sub.add_parser("eval-seeded", help="score the seeded test set against the models and rules")
    seeded.add_argument("--file", default="", help="another seeded set (defaults to the one in the repo)")
```
Add this branch after the `train-text` branch, inside `with SessionLocal.begin() as db:`:
```python
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
```

- [ ] **Step 7: Try the command on demo data**

Run:
```bash
AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/seeded-check.db .venv/Scripts/python -m alembic upgrade head
AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/seeded-check.db .venv/Scripts/python -m app.cli seed-demo
AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/seeded-check.db .venv/Scripts/python -m app.cli eval-seeded
```
Expected: a JSON list with `scam_text` and `price`, each with `"cases": 12`. Note which fake cases appear under `"missed"`; those are the first things the team improves. Delete `var/seeded-check.db` afterwards (`var/` is ignored by git).

- [ ] **Step 8: Lint and commit**

Run: `.venv/Scripts/python -m ruff check app tests`
```bash
git add app/modules/detection/seeded.py app/modules/detection/seeded_cases.json app/cli.py tests/test_detection_seeded.py
git commit -m "feat(detection): seeded test set of fake listings to measure recall" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Weekly evaluation snapshots

**Files:**
- Modify: `backend/app/modules/detection/models.py` (new model at the end)
- Modify: `backend/app/models.py` (import the new model)
- Create: `backend/migrations/versions/<generated>_evaluation_snapshots.py` (autogenerated, then reviewed)
- Create: `backend/app/modules/detection/reports.py`
- Modify: `backend/app/modules/notifications/service.py` (`TEMPLATES`: add `model_report`)
- Test: `backend/tests/test_detection_reports.py` (create)

**Interfaces:**
- Consumes:
  - `evaluate(db, name) -> Evaluation` from the service.
  - `REGISTRY`.
  - `evaluate_seeded`, `load_cases` and `DEFAULT_PATH` (Task 4).
  - `notify_on(db, user, template, channels, link="", **ctx)`.
- Produces:
  - `EvaluationSnapshot`: table `evaluation_snapshots`, unique on `(detector, week)`.
  - `iso_week(when: datetime) -> str`, formatted like `"2026-W42"`.
  - `take_snapshots(db, now=None, seeded_path=DEFAULT_PATH) -> tuple[list[EvaluationSnapshot], bool]`. The `bool` is `True` when this call created the week's rows.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_detection_reports.py`:
```python
"""The weekly model report: one snapshot per model per ISO week, the seeded set alongside, and
reviewers told once."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.detection.models import EvaluationSnapshot
from app.modules.detection.reports import iso_week, take_snapshots
from app.modules.notifications.models import Notification
from tests.test_detection import seed_evaluation

MONDAY = datetime(2026, 10, 12, 5, tzinfo=UTC)  # ISO week 2026-W42


def test_iso_week():
    assert iso_week(MONDAY) == "2026-W42"


def test_one_row_per_model_per_week_and_one_notice(db, reviewer):
    seed_evaluation(db, reviewer)
    first, created = take_snapshots(db, MONDAY)
    again, created_again = take_snapshots(db, MONDAY.replace(hour=9))
    assert created and not created_again
    rows = db.scalars(select(EvaluationSnapshot)).all()
    assert len(rows) == len(first) == len(again) == 6
    price = next(r for r in rows if r.detector == "price")
    assert price.week == "2026-W42" and price.promotable and price.labels == 30
    assert price.model["recall"] == 1.0 and price.rules["recall"] == 0.5
    notes = db.scalars(select(Notification).where(Notification.template == "model_report")).all()
    assert len(notes) == 1 and notes[0].user_id == reviewer.id
    assert "1 of 6 models could leave shadow (price)" in notes[0].body


def test_seeded_results_ride_along(db, reviewer):
    rows, _ = take_snapshots(db, MONDAY)
    by_model = {r.detector: r for r in rows}
    assert by_model["scam_text"].seeded["cases"] >= 12
    assert by_model["photos"].seeded is None  # the seeded set has no photo cases yet
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_detection_reports.py -q -p no:cacheprovider`
Expected: collection fails with `ImportError: cannot import name 'EvaluationSnapshot'`.

- [ ] **Step 3: Add the model**

Append to `backend/app/modules/detection/models.py`:
```python
class EvaluationSnapshot(Base):
    """One detector's evaluation for one ISO week (the weekly model report). Kept so reviewers can
    see a model improving or slipping; the live numbers are on the Models page."""

    __tablename__ = "evaluation_snapshots"
    __table_args__ = (Index("uq_evaluation_snapshots_week", "detector", "week", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    detector: Mapped[str] = mapped_column(String(20))
    week: Mapped[str] = mapped_column(String(8), comment="ISO week, e.g. 2026-W42")
    version: Mapped[str | None] = mapped_column(String(40))
    labels: Mapped[int] = mapped_column(default=0)
    fraud: Mapped[int] = mapped_column(default=0)
    model: Mapped[dict] = mapped_column(JSON, default=dict)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    promotable: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(String(300), default="")
    seeded: Mapped[dict | None] = mapped_column(JSON, comment="Results on the seeded test set, if it ran")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
```
In `backend/app/models.py` change the detection import to:
```python
from app.modules.detection.models import (  # noqa: F401
    DetectionLabel,
    EvaluationSnapshot,
    LinkEdge,
    ModelScore,
    ModelVersion,
    ScoreJob,
)
```

- [ ] **Step 4: Generate and review the migration**

Run:
```bash
AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/autogen.db .venv/Scripts/python -m alembic upgrade head
AFE_DEBUG=1 AFE_DATABASE_URL=sqlite:///var/autogen.db .venv/Scripts/python -m alembic revision --autogenerate -m "evaluation snapshots"
```
Open the new file in `migrations/versions/`. `upgrade()` must contain only `op.create_table("evaluation_snapshots", ...)` with the 13 columns above, plus the unique index `uq_evaluation_snapshots_week` on `detector, week`. `downgrade()` drops the index, then the table. Remove anything else the autogenerate added, then delete `var/autogen.db`.

- [ ] **Step 5: Add the notification text**

In `backend/app/modules/notifications/service.py`, add this entry to `TEMPLATES` after `"pilot_report"`:
```python
    "model_report": (
        "Weekly model report",
        "Week {week}: {summary}. {missed} misses on the seeded test set.",
    ),
```

- [ ] **Step 6: Write the snapshot function**

Create `backend/app/modules/detection/reports.py`:
```python
"""The weekly model report (Trust Engine, Stage 0): every detector's evaluation against the rules
and its results on the seeded test set, kept once per ISO week and sent to reviewers."""

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidInput
from app.db import utcnow
from app.modules.accounts.models import REVIEWER_ROLES, User

from .detectors import REGISTRY
from .models import EvaluationSnapshot
from .seeded import DEFAULT_PATH, evaluate_seeded, load_cases
from .service import evaluate


def iso_week(when: datetime) -> str:
    year, week, _ = when.isocalendar()
    return f"{year}-W{week:02d}"


def take_snapshots(
    db: Session, now: datetime | None = None, seeded_path: Path = DEFAULT_PATH
) -> tuple[list[EvaluationSnapshot], bool]:
    """Evaluate every detector and keep one row per detector for this week. Running it again in the
    same week updates those rows instead of adding more, and reviewers are told only the first time.
    Returns the rows and whether this call created them."""
    now = now or utcnow()
    week = iso_week(now)
    try:
        seeded = {r.detector: r.as_dict() for r in evaluate_seeded(db, load_cases(seeded_path))}
    except InvalidInput:
        seeded = {}  # a broken seeded file mustn't stop the report; `eval-seeded` shows why
    created, rows = False, []
    for name in REGISTRY:
        report = evaluate(db, name)
        row = db.scalar(
            select(EvaluationSnapshot).where(EvaluationSnapshot.detector == name, EvaluationSnapshot.week == week)
        )
        if row is None:
            row = EvaluationSnapshot(detector=name, week=week)
            db.add(row)
            created = True
        row.version, row.labels, row.fraud = report.version, report.labels, report.fraud
        row.model, row.rules = report.model.as_dict(), report.rules.as_dict()
        row.promotable, row.reason = report.promotable, report.reason[:300]
        row.seeded = seeded.get(name)
        rows.append(row)
    db.flush()
    if created:
        _tell_reviewers(db, rows, week)
    return rows, created


def _tell_reviewers(db: Session, rows: list[EvaluationSnapshot], week: str) -> None:
    from app.modules.notifications.service import notify_on

    ready = [r.detector for r in rows if r.promotable]
    missed = sum(len((r.seeded or {}).get("missed", [])) for r in rows)
    summary = f"{len(ready)} of {len(rows)} models could leave shadow" + (f" ({', '.join(ready)})" if ready else "")
    for person in db.scalars(select(User).where(User.role.in_(REVIEWER_ROLES), User.is_active.is_(True))):
        notify_on(db, person, "model_report", {"in_app"}, link="/review/detection", week=week, summary=summary,
                  missed=missed)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_detection_reports.py tests/test_flows.py::test_migrations_match_the_models -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 8: Lint and commit**

Run: `.venv/Scripts/python -m ruff check app tests`
```bash
git add app/modules/detection/models.py app/models.py migrations/versions app/modules/detection/reports.py app/modules/notifications/service.py tests/test_detection_reports.py
git commit -m "feat(detection): weekly evaluation snapshots with the seeded set, sent to reviewers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The weekly job, with retraining only in shadow

**Files:**
- Modify: `backend/app/modules/detection/reports.py` (add `weekly_models`)
- Modify: `backend/app/worker.py` (add a wrapper function and a `DAILY_JOBS` entry)
- Modify: `backend/app/cli.py` (docstring, sub-parser, dispatch branch)
- Modify: `infra/terraform/staging/operations.tf:11-16` (`jobs` map)
- Test: `backend/tests/test_detection_reports.py` (new tests)

**Interfaces:**
- Consumes:
  - `take_snapshots` and `iso_week` (Task 5).
  - `train_text(db, reviewer) -> ModelVersion`, which raises `RuleViolation` when it has too few examples.
  - `mode(db, name) -> str`.
- Produces:
  - `weekly_models(db, now=None, force=False) -> dict`, with the keys `ran`, plus either `why`, or `week`, `snapshots` and `trained`.
  - The CLI command `python -m app.cli weekly-models [--force]`.
  - A worker daily job named `weekly-models` at 05:00 UTC.
  - An EventBridge schedule that runs it on Mondays at 05:00.

- [ ] **Step 1: Write the failing tests**

Add these imports to the top of `backend/tests/test_detection_reports.py`:
```python
import dataclasses

from app.modules.compliance import service as compliance
from app.modules.detection.hooks import label_key
from app.modules.detection.models import ModelVersion
from app.modules.detection.reports import weekly_models
from tests.conftest import make_listing
```
Then add the tests:
```python
def labelled_text(db, unit, landlord, reviewer):
    """Six scam listings and six genuine ones, decided by a reviewer: enough to train on."""
    for i in range(6):
        scam = make_listing(db, unit, landlord, title=f"Room {i}", description="Send momo commitment fee first, viewing after")
        label_key(db, "listings", str(scam.id), True, "verification", reviewer)
        fine = make_listing(db, unit, landlord, title=f"Flat {i}", description="Quiet compound with a water tank")
        label_key(db, "listings", str(fine.id), False, "verification", reviewer)


def test_weekly_job_waits_for_monday(db):
    tuesday = datetime(2026, 10, 13, 5, tzinfo=UTC)
    assert weekly_models(db, tuesday) == {"ran": False, "why": "the weekly report runs on Mondays"}
    assert db.scalar(select(EvaluationSnapshot)) is None


def test_weekly_job_reports_and_retrains_once_in_shadow(db, unit, landlord, reviewer):
    labelled_text(db, unit, landlord, reviewer)
    out = weekly_models(db, MONDAY)
    assert out == {"ran": True, "week": "2026-W42", "snapshots": 6, "trained": "nb-1"}
    again = weekly_models(db, MONDAY.replace(hour=9))
    assert again["trained"] == "already ran this week"
    assert len(db.scalars(select(ModelVersion)).all()) == 1


def test_an_acting_model_is_not_retrained_automatically(db, monkeypatch, unit, landlord, reviewer):
    labelled_text(db, unit, landlord, reviewer)
    key = "model_scam_text_mode"
    monkeypatch.setitem(compliance.RULES, key, dataclasses.replace(compliance.RULES[key], default="canary"))
    out = weekly_models(db, MONDAY)
    assert out["trained"] == "not trained: the model is acting, so a reviewer retrains it"
    assert db.scalar(select(ModelVersion)) is None


def test_too_few_labels_is_reported_not_raised(db):
    out = weekly_models(db, MONDAY)
    assert out["ran"] and out["trained"].startswith("not trained: Not enough labelled text")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_detection_reports.py -q -p no:cacheprovider`
Expected: collection fails with `ImportError: cannot import name 'weekly_models'`.

- [ ] **Step 3: Write the weekly job**

In `backend/app/modules/detection/reports.py`, add to the imports:
```python
from app.core.errors import InvalidInput, RuleViolation
```
(replacing the existing `from app.core.errors import InvalidInput`) and:
```python
from .service import evaluate, mode, train_text
```
(replacing `from .service import evaluate`). Then append:
```python
def weekly_models(db: Session, now: datetime | None = None, force: bool = False) -> dict:
    """Mondays: take the weekly report, then retrain the in-house wording model while it's in shadow.
    A model that is already acting (canary or active) is retrained only by a reviewer, because a new
    version would act before anyone had judged it. Runs at most once a week, however often it's called."""
    now = now or utcnow()
    if now.weekday() != 0 and not force:
        return {"ran": False, "why": "the weekly report runs on Mondays"}
    rows, first_run = take_snapshots(db, now)
    if not first_run:
        trained = "already ran this week"
    elif mode(db, "scam_text") not in ("off", "shadow"):
        trained = "not trained: the model is acting, so a reviewer retrains it"
    else:
        try:
            trained = train_text(db, None).version
        except RuleViolation as exc:
            trained = f"not trained: {exc}"
    return {"ran": True, "week": iso_week(now), "snapshots": len(rows), "trained": trained}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_detection_reports.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Schedule it in the worker, the CLI and Terraform**

In `backend/app/worker.py`, add after `def pilot_report(db):`:
```python
def weekly_models(db):
    from app.modules.detection.reports import weekly_models as run

    return run(db)
```
and add to `DAILY_JOBS` (it no-ops except on Mondays):
```python
    DailyJob("weekly-models", 86400, "app.worker:weekly_models", at_hour=5),
```
In `backend/app/cli.py`, add to the docstring after the `eval-seeded` line:
```
weekly-models  the weekly model report, and shadow retraining of the wording model (Mondays)
```
Add after the `eval-seeded` sub-parser:
```python
    weekly = sub.add_parser("weekly-models", help="weekly model report, and retraining while in shadow")
    weekly.add_argument("--force", action="store_true", help="run even if today isn't Monday")
```
Add this branch after the `eval-seeded` branch:
```python
        elif args.command == "weekly-models":
            from app.modules.detection.reports import weekly_models

            print(weekly_models(db, force=args.force))
```
In `infra/terraform/staging/operations.tf`, add to `locals.jobs`, keeping the `=` signs aligned:
```hcl
    "weekly-models"  = "cron(0 5 ? * MON *)" # weekly model report and shadow retraining, Mondays 05:00
```
If Terraform is installed, run `terraform -chdir=../infra/terraform/staging fmt -check`.

- [ ] **Step 6: Run the worker and detection tests**

Run: `.venv/Scripts/python -m pytest tests/test_worker.py tests/test_detection_reports.py -q -p no:cacheprovider`
Expected: all pass. `test_real_daily_jobs_run_against_the_database` now also runs `weekly-models`, which returns "runs on Mondays" on any other day.

- [ ] **Step 7: Lint and commit**

Run: `.venv/Scripts/python -m ruff check app tests`
```bash
git add app/modules/detection/reports.py app/worker.py app/cli.py tests/test_detection_reports.py ../infra/terraform/staging/operations.tf
git commit -m "feat(detection): weekly model report job; retrains only while the model is in shadow" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Weekly reports on the reviewers' Models page

**Files:**
- Modify: `backend/app/api/schemas.py` (after `DetectorOut`: add `SeededOut` and `SnapshotOut`)
- Modify: `backend/app/api/v1/review.py` (imports, and a new route after `detectors`)
- Modify: `frontend/src/lib/api/types.ts` (after `Detector`: add `EvaluationSnapshot`)
- Modify: `frontend/src/routes/review/detection/+page.server.ts` (`load`)
- Modify: `frontend/src/routes/review/detection/+page.svelte` (a new section before "Scam-wording versions", and one style rule)
- Test: `backend/tests/test_detection_reports.py` (API test)

**Interfaces:**
- Consumes: `EvaluationSnapshot` and `take_snapshots` (Task 5); `TallyOut` and `Out` from the schemas.
- Produces:
  - `GET /api/v1/review/detection/history`, for reviewers only. It returns `list[SnapshotOut]`, newest week first, covering at most 12 weeks.
  - The `EvaluationSnapshot` TypeScript type, and `data.history` on the Models page.

- [ ] **Step 1: Write the failing API test**

Add to `backend/tests/test_detection_reports.py`:
```python
from tests.conftest import api_login


def test_history_over_the_api(client, db, reviewer):
    seed_evaluation(db, reviewer)
    take_snapshots(db, MONDAY)
    db.flush()
    h = api_login(client, "reviewer")
    rows = client.get("/api/v1/review/detection/history", headers=h).json()["data"]
    price = next(r for r in rows if r["detector"] == "price")
    assert price["week"] == "2026-W42" and price["model"]["recall"] == 1.0 and price["promotable"]
    assert next(r for r in rows if r["detector"] == "scam_text")["seeded"]["cases"] >= 12
    assert client.get("/api/v1/review/detection/history").status_code == 401
```
Move the `from tests.conftest import api_login` line up to the file's import block (merged with the existing `from tests.conftest import make_listing`).

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_detection_reports.py::test_history_over_the_api -q -p no:cacheprovider`
Expected: FAIL, with a 404 on `/api/v1/review/detection/history`, so `rows` has no `"data"` list.

- [ ] **Step 3: Add the schemas and the route**

In `backend/app/api/schemas.py`, add after `class DetectorOut`:
```python
class SeededOut(BaseModel):
    cases: int
    fraud: int
    skipped: int
    model: TallyOut
    rules: TallyOut
    missed: list[str]


class SnapshotOut(Out):
    detector: str
    week: str
    version: str | None
    labels: int
    fraud: int
    model: TallyOut
    rules: TallyOut
    promotable: bool
    reason: str
    seeded: SeededOut | None
    created_at: datetime
```
In `backend/app/api/v1/review.py`, change:
```python
from app.modules.detection.models import ModelVersion
```
to:
```python
from app.modules.detection.models import EvaluationSnapshot, ModelVersion
```
and add after the `detectors` route:
```python
@router.get("/detection/history", response_model=Envelope[list[s.SnapshotOut]])
def detection_history(db: DB, user: Reviewer):
    """The weekly model reports, newest week first: the last 12 weeks for every model."""
    rows = db.scalars(
        select(EvaluationSnapshot)
        .order_by(EvaluationSnapshot.week.desc(), EvaluationSnapshot.detector)
        .limit(12 * len(REGISTRY))
    )
    return ok([s.SnapshotOut.model_validate(r) for r in rows])
```

- [ ] **Step 4: Run the API test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_detection_reports.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Add the frontend type and loader**

In `frontend/src/lib/api/types.ts`, add after `export interface Detector {...}`:
```ts
export interface EvaluationSnapshot {
	detector: string;
	week: string;
	version: string | null;
	labels: number;
	fraud: number;
	model: Tally;
	rules: Tally;
	promotable: boolean;
	reason: string;
	seeded: { cases: number; fraud: number; skipped: number; model: Tally; rules: Tally; missed: string[] } | null;
	created_at: string;
}
```
In `frontend/src/routes/review/detection/+page.server.ts`, change the types import to:
```ts
import type { Detector, EvaluationSnapshot, ModelVersion } from '$lib/api/types';
```
and replace `load` with:
```ts
export const load: PageServerLoad = async ({ locals }) => {
	const [{ data, meta }, history] = await Promise.all([
		locals.api.withMeta<Detector[]>('/review/detection'),
		locals.api.get<EvaluationSnapshot[]>('/review/detection/history')
	]);
	return { detectors: data, versions: (meta.versions as ModelVersion[]) ?? [], history };
};
```

- [ ] **Step 6: Show the weekly reports on the page**

In `frontend/src/routes/review/detection/+page.svelte`, insert this section immediately before `<section class="case" aria-labelledby="ver-h">`:
```svelte
<section class="case" aria-labelledby="hist-h">
	<div class="case-head">
		<b id="hist-h">Weekly reports</b>
		<span class="small muted">Every Monday at 05:00, kept for 12 weeks</span>
	</div>
	{#if data.history.length}
		<div class="scroll">
			<table class="q hist-t">
				<thead>
					<tr><th>Week</th><th>Model</th><th>Decided cases</th><th>Precision</th><th>Recall</th><th>Rules recall</th><th>Seeded recall</th><th>Ready</th></tr>
				</thead>
				<tbody>
					{#each data.history as h (h.week + h.detector)}
						<tr>
							<td class="mono">{h.week}</td>
							<td>{h.detector}</td>
							<td class="mono">{h.labels} · {h.fraud} fraud</td>
							<td class="mono">{pct(h.model.precision)}</td>
							<td class="mono">{pct(h.model.recall)}</td>
							<td class="mono">{pct(h.rules.recall)}</td>
							<td class="mono">{h.seeded ? `${pct(h.seeded.model.recall)} of ${h.seeded.fraud}` : '—'}</td>
							<td>{#if h.promotable}<span class="pill ok">Ready</span>{:else}<span class="small muted">No</span>{/if}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="case-body small muted">No weekly report yet. The first one runs on Monday at 05:00.</div>
	{/if}
</section>
```
Add to the page's `<style>` block:
```css
	.hist-t {
		min-width: 720px;
	}
```

- [ ] **Step 7: Type-check the frontend**

Run from `frontend/`: `npx svelte-kit sync && npx svelte-check --threshold error`
Expected: `0 ERRORS`.

- [ ] **Step 8: Commit**

```bash
git add app/api/schemas.py app/api/v1/review.py tests/test_detection_reports.py ../frontend/src/lib/api/types.ts ../frontend/src/routes/review/detection
git commit -m "feat(review): weekly model reports on the Models page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Final check (after Task 7)

- [ ] **Backend:** `.venv/Scripts/python -m ruff check app tests && .venv/Scripts/python -m pytest -p no:warnings -q`. Expected: all pass. The suite had 246 tests before this plan and gains the new ones.
- [ ] **Frontend:** from `frontend/`, run `npx svelte-check --threshold error && npx vitest run && npm run build`. Expected: 0 errors, all tests pass, and the build succeeds.
- [ ] **In the running app:** `bash .claude/skills/run-afe/driver.sh up`, then sign in as `reviewer` and open `/review/detection`.
  - There are six models. The Claude one reads `off`, with a "Turn on in shadow" button.
  - The "Weekly reports" section is present.
  - Run `.venv/Scripts/python -m app.cli weekly-models --force` against the demo database (`AFE_DATABASE_URL` from `/tmp/afe-run`) and reload: the table fills with this week's rows, and the reviewer has a "Weekly model report" notification.
  - `bash .claude/skills/run-afe/driver.sh down` when done.
- [ ] **Turning Claude on (not code):** it stays `off` until counsel answers B11. Then a reviewer proposes `shadow` on the Models page and a second reviewer approves it on the Rules page, with `AFE_ANTHROPIC_API_KEY` set in Secrets Manager first.
