"""The Claude wording classifier: the official SDK, structured output, redaction, and failures that
retry instead of scoring zero."""

from types import SimpleNamespace

import pytest

from app.config import Settings, get_settings
from app.modules.detection.text import ClaudeTextModel, Verdict, get_text_model

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


def test_the_sdk_client_is_shared_and_fails_fast(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test-key")
    first, second = ClaudeTextModel(), ClaudeTextModel()
    assert first.client is second.client  # one connection pool per process, not one per job
    assert first.client.max_retries == 0  # the job queue already retries a failed job three times
    assert first.client.timeout == 10.0  # a slow reply fails fast instead of holding the worker


def test_the_in_house_detector_cannot_be_pointed_at_claude(monkeypatch):
    # Claude runs only as the scam_text_llm detector, behind its off switch and two reviewers (B11).
    monkeypatch.setattr(get_settings(), "text_model", "app.modules.detection.text.ClaudeTextModel")
    with pytest.raises(RuntimeError, match="scam_text_llm"):
        get_text_model()
