from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.collect_boundaries import append_label, parse_end_input


def test_parse_end_input_blank_means_full_duration() -> None:
    assert parse_end_input("", 3000.0) == 3000.0
    assert parse_end_input("   ", 3000.0) == 3000.0


def test_parse_end_input_accepts_a_valid_value() -> None:
    assert parse_end_input("1234", 3000.0) == 1234.0


def test_parse_end_input_rejects_non_numeric() -> None:
    with pytest.raises(ValueError):
        parse_end_input("soon", 3000.0)


def test_parse_end_input_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        parse_end_input("5000", 3000.0)
    with pytest.raises(ValueError):
        parse_end_input("-1", 3000.0)


def test_append_label_writes_one_jsonl_row(tmp_path: Path) -> None:
    out = tmp_path / "labels.jsonl"
    append_label(out, audio_path="a.wav", true_end_ms=1200.5, notes="clean")
    append_label(out, audio_path="b.wav", true_end_ms=800.0, notes="")

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first == {"audio_path": "a.wav", "true_end_ms": 1200.5, "notes": "clean"}
