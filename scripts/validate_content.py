#!/usr/bin/env python3
"""Validates content/{scenarios,personas,rubrics}/*.yaml before `make seed` writes anything.

docs/phase-0-BUILD.md TASK 0.6 — fails loudly on:
  - a rubric criterion missing any of the five scale points
  - an anchor descriptor under 40 characters
  - an anchor descriptor that is a bare adjective phrase (matches the forbidden pattern)
  - a scenario brief under 200 characters
  - a persona whose voice_id has no matching file in models/piper/

Run standalone: `uv run python scripts/validate_content.py`
Also imported by scripts/seed.py, which refuses to write anything if this fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"
PIPER_DIR = REPO_ROOT / "models" / "piper"

SCALE_POINTS = {"1", "2", "3", "4", "5"}
MIN_DESCRIPTOR_LENGTH = 40
MIN_BRIEF_LENGTH = 200
FORBIDDEN_DESCRIPTOR_PATTERN = re.compile(
    r"^(very )?(good|bad|poor|excellent|adequate|fine)\b", re.IGNORECASE
)


def _load_yaml_files(subdir: str) -> list[tuple[Path, dict]]:
    directory = CONTENT_DIR / subdir
    if not directory.exists():
        return []
    docs = []
    for path in sorted(directory.glob("*.yaml")):
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        docs.append((path, data))
    return docs


def validate_rubrics(rubrics: list[tuple[Path, dict]]) -> list[str]:
    errors: list[str] = []
    for path, rubric in rubrics:
        slug = rubric.get("slug", "?")
        criteria = rubric.get("criteria", [])
        if not criteria:
            errors.append(f"{path.name}: rubric '{slug}' has no criteria")
            continue

        # docs/phase-2-BUILD.md TASK 2.5f: "stored on the rubric, not hardcoded" — enforced at
        # content-authoring time too, not just the DB CHECK constraint (a broken policy should
        # never reach `make seed`'s upsert in the first place).
        policy = rubric.get("aggregation_policy")
        method = policy.get("method") if isinstance(policy, dict) else None
        if not isinstance(method, str) or not method:
            errors.append(f"{path.name}: rubric '{slug}' has no valid aggregation_policy.method")
        elif isinstance(policy, dict):
            min_turns = policy.get("min_turns_with_signal")
            if min_turns is not None and not isinstance(min_turns, int):
                errors.append(f"{path.name}: rubric '{slug}' min_turns_with_signal must be an int")

        for criterion in criteria:
            key = criterion.get("key", "?")
            descriptors = criterion.get("anchor_descriptors", {})
            where = f"{path.name}: rubric '{slug}' criterion '{key}'"

            missing = SCALE_POINTS - set(descriptors.keys())
            if missing:
                errors.append(f"{where}: missing scale point(s) {sorted(missing)}")

            for point, text in descriptors.items():
                if point not in SCALE_POINTS:
                    continue
                if not isinstance(text, str):
                    errors.append(f"{where} point {point}: descriptor is not a string")
                    continue
                if len(text) < MIN_DESCRIPTOR_LENGTH:
                    errors.append(
                        f"{where} point {point}: descriptor is {len(text)} chars, "
                        f"needs >= {MIN_DESCRIPTOR_LENGTH}"
                    )
                if FORBIDDEN_DESCRIPTOR_PATTERN.match(text.strip()):
                    errors.append(
                        f"{where} point {point}: descriptor is a bare quality judgement, "
                        f"not an observable ('{text[:50]}...')"
                    )
    return errors


def validate_scenarios(scenarios: list[tuple[Path, dict]]) -> list[str]:
    errors: list[str] = []
    for path, scenario in scenarios:
        slug = scenario.get("slug", "?")
        brief = scenario.get("brief", "")
        if len(brief) < MIN_BRIEF_LENGTH:
            errors.append(
                f"{path.name}: scenario '{slug}' brief is {len(brief)} chars, "
                f"needs >= {MIN_BRIEF_LENGTH}"
            )
        if not scenario.get("opening_strategy"):
            errors.append(f"{path.name}: scenario '{slug}' has no opening_strategy")
        if not scenario.get("difficulty_params"):
            errors.append(f"{path.name}: scenario '{slug}' has no difficulty_params")
    return errors


def validate_personas(personas: list[tuple[Path, dict]]) -> list[str]:
    errors: list[str] = []
    available_voices = {p.stem for p in PIPER_DIR.glob("*.onnx")} if PIPER_DIR.exists() else set()
    for path, persona in personas:
        slug = persona.get("slug", "?")
        voice_id = persona.get("voice_id")
        if not voice_id:
            errors.append(f"{path.name}: persona '{slug}' has no voice_id")
        elif voice_id not in available_voices:
            errors.append(
                f"{path.name}: persona '{slug}' voice_id '{voice_id}' has no matching "
                f"file in models/piper/ (found: {sorted(available_voices) or 'none'})"
            )
    return errors


def validate_all() -> list[str]:
    errors: list[str] = []
    errors += validate_rubrics(_load_yaml_files("rubrics"))
    errors += validate_scenarios(_load_yaml_files("scenarios"))
    errors += validate_personas(_load_yaml_files("personas"))
    return errors


def main() -> int:
    errors = validate_all()
    if errors:
        print(f"content validation FAILED - {len(errors)} error(s):\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("content validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
