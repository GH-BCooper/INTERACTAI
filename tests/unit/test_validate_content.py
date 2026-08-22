"""docs/phase-0-BUILD.md TASK 0.6 acceptance: the validator passes on real content and fails
loudly on deliberately broken fixtures. Operates on in-memory dicts (matching the loaded-YAML
shape) rather than writing throwaway files — scripts/validate_content.py's validate_* functions
take already-parsed data, so this is exercising the real validation logic, not a copy of it.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validate_content import (
    validate_all,
    validate_personas,
    validate_rubrics,
    validate_scenarios,
)

FAKE_PATH = Path("fake.yaml")

VALID_ANCHORS = {
    "1": "No discernible organisation. The answer starts mid-thought or never resolves.",
    "2": "Facts in the order they occurred to the speaker; no signposting anywhere at all.",
    "3": "Recognisable beginning and end, but the middle wanders noticeably throughout it.",
    "4": "A clear arc with one weak transition or a missing close. Still easy to follow.",
    "5": "Opens by naming the situation, moves through action to outcome, and closes well.",
}

VALID_RUBRIC = {
    "slug": "test_rubric",
    "aggregation_policy": {"method": "mean_weighted_by_confidence", "min_turns_with_signal": 2},
    "criteria": [
        {
            "key": "structure",
            "anchor_descriptors": VALID_ANCHORS,
        }
    ],
}


def test_real_authored_content_passes() -> None:
    assert validate_all() == []


class TestRubricValidation:
    def test_valid_rubric_has_no_errors(self) -> None:
        assert validate_rubrics([(FAKE_PATH, VALID_RUBRIC)]) == []

    def test_missing_scale_point_is_rejected(self) -> None:
        incomplete = dict(VALID_ANCHORS)
        del incomplete["5"]
        rubric = {
            "slug": "broken",
            "criteria": [{"key": "structure", "anchor_descriptors": incomplete}],
        }
        errors = validate_rubrics([(FAKE_PATH, rubric)])
        assert any("missing scale point" in e for e in errors)

    def test_short_descriptor_is_rejected(self) -> None:
        rubric = {
            "slug": "broken",
            "criteria": [
                {
                    "key": "structure",
                    "anchor_descriptors": {**VALID_ANCHORS, "1": "Too short."},
                }
            ],
        }
        errors = validate_rubrics([(FAKE_PATH, rubric)])
        assert any("needs >=" in e for e in errors)

    def test_bare_quality_judgement_is_rejected(self) -> None:
        for bad_text in ["Good structure and clear delivery throughout the whole answer."]:
            rubric = {
                "slug": "broken",
                "criteria": [
                    {"key": "structure", "anchor_descriptors": {**VALID_ANCHORS, "3": bad_text}}
                ],
            }
            errors = validate_rubrics([(FAKE_PATH, rubric)])
            assert any("bare quality judgement" in e for e in errors)

    def test_rubric_with_no_criteria_is_rejected(self) -> None:
        errors = validate_rubrics([(FAKE_PATH, {"slug": "empty", "criteria": []})])
        assert any("no criteria" in e for e in errors)


class TestScenarioValidation:
    def test_short_brief_is_rejected(self) -> None:
        scenario = {
            "slug": "s1",
            "brief": "Too short.",
            "opening_strategy": "Open.",
            "difficulty_params": {"standard": {}},
        }
        errors = validate_scenarios([(FAKE_PATH, scenario)])
        assert any("needs >= 200" in e for e in errors)

    def test_valid_scenario_has_no_errors(self) -> None:
        scenario = {
            "slug": "s1",
            "brief": "x" * 210,
            "opening_strategy": "Open with a question.",
            "difficulty_params": {"standard": {}},
        }
        assert validate_scenarios([(FAKE_PATH, scenario)]) == []

    def test_missing_difficulty_params_is_rejected(self) -> None:
        scenario = {"slug": "s1", "brief": "x" * 210, "opening_strategy": "Open."}
        errors = validate_scenarios([(FAKE_PATH, scenario)])
        assert any("no difficulty_params" in e for e in errors)


class TestPersonaValidation:
    def test_unknown_voice_id_is_rejected(self) -> None:
        persona = {"slug": "p1", "voice_id": "not-a-real-voice"}
        errors = validate_personas([(FAKE_PATH, persona)])
        assert any("no matching" in e for e in errors)

    def test_real_downloaded_voice_id_passes(self) -> None:
        persona = {"slug": "p1", "voice_id": "en_US-lessac-medium"}
        assert validate_personas([(FAKE_PATH, persona)]) == []
