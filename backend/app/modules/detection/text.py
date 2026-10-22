"""Scam-wording models for listings and messages (build plan §7).

Three layers, all behind one `score(text)` call:
- a feature model that weighs the Phase 1 rule hits with other signals (always on);
- a naive Bayes model trained on reviewer labels (`python -m app.cli train-text`), blended in
  once a trained version exists;
- `ClaudeTextModel`, used by the separate `scam_text_llm` detector (off until counsel clears B11),
  so the LLM is evaluated beside the in-house model. Text is redacted before it leaves Afe.
"""

import importlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel

from app.config import get_settings
from app.modules.risk.rules import scam_language

_PHONE = re.compile(r"(?:\+?233|0)\s?[2-5]\d(?:[\s-]?\d){7}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_DIGITS = re.compile(r"\d{6,}")
_WORD = re.compile(r"[a-z₵']+")
_MONEY = re.compile(r"\b(?:gh(?:[₵c]|s)?|cedis?)\s?\d|\d[\d,]{2,}\s?(?:gh(?:[₵c]|s)?|cedis?)\b|₵\s?\d", re.IGNORECASE)
_PAYMENT_WORDS = re.compile(r"\b(?:momo|mobile money|transfer|account number|send (?:it|the money)|pay (?:now|today))\b", re.I)
_ADVANCE_WORDS = re.compile(r"\b(?:advance|deposit|commitment|reservation|booking)\b", re.I)


def redact(text: str) -> str:
    """Mask personal details before text is logged in a model call or sent to a provider."""
    text = _PHONE.sub("[phone]", text or "")
    text = _EMAIL.sub("[email]", text)
    return _DIGITS.sub("[number]", text)


@dataclass(frozen=True)
class TextScore:
    score: int  # 0-100
    reasons: list[str]
    version: str


# --- Feature model ------------------------------------------------------------------------------------

_WEIGHTS = {
    "language.pay_before_viewing": 3.2,
    "language.move_off_platform": 1.8,
    "language.phone_number_in_text": 1.1,
    "language.urgency": 0.9,
    "money_amount": 0.6,
    "payment_words": 0.9,
    "advance_with_money": 0.7,
}
_BIAS = -2.6
_REASON_TEXT = {
    "money_amount": "Mentions an amount of money",
    "payment_words": "Talks about sending money or mobile money",
    "advance_with_money": "Asks for an advance or deposit with an amount",
}


def _features(text: str) -> dict[str, str]:
    found = {hit.rule: hit.explanation for hit in scam_language(text)}
    if _MONEY.search(text):
        found["money_amount"] = _REASON_TEXT["money_amount"]
    if _PAYMENT_WORDS.search(text):
        found["payment_words"] = _REASON_TEXT["payment_words"]
    if _ADVANCE_WORDS.search(text) and "money_amount" in found:
        found["advance_with_money"] = _REASON_TEXT["advance_with_money"]
    return found


def feature_score(text: str) -> tuple[float, list[str]]:
    found = _features(text)
    z = _BIAS + sum(_WEIGHTS[f] for f in found)
    return 1 / (1 + math.exp(-z)), list(found.values())


# --- Naive Bayes, trained on labels -------------------------------------------------------------------


def tokens(text: str) -> list[str]:
    words = _WORD.findall(redact(text).lower())
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]


def train_naive_bayes(examples: list[tuple[str, bool]]) -> dict:
    """examples: (text, is_fraud). Returns parameters to store in a ModelVersion."""
    counts = {"fraud": Counter(), "legit": Counter()}
    docs = Counter()
    for text, is_fraud in examples:
        cls = "fraud" if is_fraud else "legit"
        docs[cls] += 1
        counts[cls].update(set(tokens(text)))
    vocab = {t for c in counts.values() for t in c if sum(cc[t] for cc in counts.values()) >= 2}
    return {
        "docs": dict(docs),
        "counts": {cls: {t: n for t, n in c.items() if t in vocab} for cls, c in counts.items()},
        "vocab_size": len(vocab),
    }


def naive_bayes_probability(params: dict, text: str) -> float:
    docs = params["docs"]
    total = sum(docs.values())
    if not total or not docs.get("fraud") or not docs.get("legit"):
        return 0.5
    log = {}
    for cls in ("fraud", "legit"):
        n = docs[cls]
        counts = params["counts"][cls]
        log[cls] = math.log(n / total)
        for t in set(tokens(text)):
            if t in params["counts"]["fraud"] or t in params["counts"]["legit"]:
                p = (counts.get(t, 0) + 1) / (n + 2)  # Bernoulli NB with Laplace smoothing
                log[cls] += math.log(p)
    diff = max(min(log["fraud"] - log["legit"], 30), -30)
    return 1 / (1 + math.exp(-diff))


# --- Models ------------------------------------------------------------------------------------------


class HeuristicTextModel:
    """Feature model, blended with the newest trained naive Bayes version when one exists."""

    def __init__(self, trained: tuple[str, dict] | None = None):
        self.trained = trained

    def score(self, text: str) -> TextScore:
        p, reasons = feature_score(text)
        version = "features-1"
        if self.trained:
            name, params = self.trained
            nb = naive_bayes_probability(params, text)
            p = 0.5 * p + 0.5 * nb
            version = f"features-1+{name}"
            if nb >= 0.8:
                reasons = [*reasons, "Wording resembles past scams reviewers confirmed"]
        return TextScore(round(p * 100), reasons, version)


_PROMPT = """You check rental listings and messages in Accra, Ghana, for scams. Common scams: asking for \
money before a viewing ("viewing fee", "commitment fee", "send momo first"), moving the chat or payment off \
the platform (WhatsApp, direct MoMo), urgency and pressure, fake agents, and prices far below the area. \
Ghanaian English, Pidgin and Twi may be mixed. Personal details are masked as [phone], [email], [number].

Give a score from 0 to 100 for how likely this is a scam attempt, and up to 3 short reasons in plain English."""


class Verdict(BaseModel):
    """The shape Claude must answer in (structured output), so a reply is never free text."""

    score: int
    reasons: list[str]


_clients: dict[str, object] = {}


def _sdk_client(api_key: str):
    """One SDK client per process, so jobs share its connection pool. The job queue already retries
    a failed job three times, so the SDK doesn't retry on its own, and a slow reply fails in 10 s
    instead of holding the worker that also runs the payment jobs."""
    if api_key not in _clients:
        import anthropic

        _clients[api_key] = anthropic.Anthropic(api_key=api_key, timeout=10.0, max_retries=0)
    return _clients[api_key]


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
            client = _sdk_client(settings.anthropic_api_key)
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


def get_text_model(trained: tuple[str, dict] | None = None):
    module, _, cls = get_settings().text_model.rpartition(".")
    model = getattr(importlib.import_module(module), cls)
    if model is ClaudeTextModel:
        # Sending text abroad goes through the scam_text_llm detector only, behind its off switch
        # and two reviewers (B11). This setting must not be a way round that.
        raise RuntimeError("AFE_TEXT_MODEL can't be ClaudeTextModel: turn on the scam_text_llm detector instead")
    return model(trained)
