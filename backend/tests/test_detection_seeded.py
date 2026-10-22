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


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": 13}, "13: id must be text"),
        ({"id": ["a"]}, "id must be text"),
        ({"area": 5}, "fake-1: area must be text"),
        ({"bedrooms": True}, "fake-1: bedrooms must be a whole number"),
        ({"rent_ghs": True}, "fake-1: rent_ghs must be a positive number"),
    ],
)
def test_values_of_the_wrong_type_are_refused(tmp_path, change, message):
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
