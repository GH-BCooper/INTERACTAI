"""docs/phase-5-BUILD.md TASK 5.2c acceptance criteria: "Speaker-leakage assertion present and
passing; a deliberately leaked fixture fails it" plus the split/hash/cap properties around it.
Pure unit tests — no database, matching split.py's own no-I/O design.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "services" / "training" / "dataset"))

import pytest  # noqa: E402
from records import SpeakerLeakageError, TurnRecord  # noqa: E402
from split import (  # noqa: E402
    assert_no_speaker_leakage,
    compute_dataset_revision_hash,
    enforce_synthetic_cap,
    mark_double_labeled,
    source_breakdown,
    split_counts,
    split_dataset,
)


def _make_turns(n_speakers: int, turns_per_speaker: int, source: str = "self") -> list[TurnRecord]:
    turns = []
    for s in range(n_speakers):
        for t in range(turns_per_speaker):
            turns.append(
                TurnRecord(
                    turn_id=f"turn-{s}-{t}",
                    session_id=f"session-{s}",
                    speaker_key=f"speaker-{s}",
                    source=source,
                )
            )
    return turns


def test_speaker_never_split_across_train_val_test() -> None:
    turns = _make_turns(n_speakers=20, turns_per_speaker=10)
    assignments = split_dataset(turns)
    assert_no_speaker_leakage(assignments)  # must not raise

    speaker_to_splits: dict[str, set[str]] = {}
    for a in assignments:
        speaker_to_splits.setdefault(a.speaker_key, set()).add(a.split)
    assert all(len(splits) == 1 for splits in speaker_to_splits.values())


def test_split_targets_roughly_70_15_15() -> None:
    turns = _make_turns(n_speakers=40, turns_per_speaker=10)
    assignments = split_dataset(turns)
    counts = split_counts(assignments)
    total = sum(counts.values())
    assert total == 400
    assert 0.60 <= counts["train"] / total <= 0.80
    assert 0.08 <= counts["validation"] / total <= 0.22
    assert 0.08 <= counts["test"] / total <= 0.22


def test_deliberately_leaked_fixture_is_rejected() -> None:
    """The acceptance criterion, verbatim: a fixture that leaks a speaker across splits must
    fail the assertion. Built by hand here (not via split_dataset, which never produces a leak)
    to prove the *assertion itself* — not just split_dataset's own correctness — actually
    detects the failure mode it exists to catch.
    """
    from records import SplitAssignment

    leaked = [
        SplitAssignment(
            turn_id="t1", session_id="s1", speaker_key="alice", source="self", split="train"
        ),
        SplitAssignment(
            turn_id="t2", session_id="s2", speaker_key="alice", source="self", split="test"
        ),
    ]
    with pytest.raises(SpeakerLeakageError) as exc_info:
        assert_no_speaker_leakage(leaked)
    assert "alice" in str(exc_info.value)


def test_synthetic_turns_never_enter_validation_or_test() -> None:
    turns = _make_turns(n_speakers=20, turns_per_speaker=10, source="self")
    turns += [
        TurnRecord(
            turn_id=f"synth-{i}",
            session_id=f"synth-session-{i}",
            speaker_key=f"synthetic:batch-{i}",
            source="synthetic",
        )
        for i in range(30)
    ]
    assignments = split_dataset(turns)
    synthetic_assignments = [a for a in assignments if a.source == "synthetic"]
    assert len(synthetic_assignments) == 30
    assert all(a.split == "train" for a in synthetic_assignments)


def test_synthetic_cap_enforced_at_35_percent_of_train() -> None:
    real = _make_turns(n_speakers=20, turns_per_speaker=10, source="self")  # 200 real
    synthetic = [
        TurnRecord(
            turn_id=f"synth-{i}",
            session_id=f"synth-session-{i}",
            speaker_key=f"synthetic:batch-{i}",
            source="synthetic",
        )
        for i in range(500)  # deliberately far over any reasonable cap
    ]
    assignments = split_dataset(real + synthetic)
    capped = enforce_synthetic_cap(assignments)

    train = [a for a in capped if a.split == "train"]
    synthetic_in_train = [a for a in train if a.source == "synthetic"]
    real_in_train = [a for a in train if a.source != "synthetic"]
    fraction = len(synthetic_in_train) / len(train)
    assert fraction <= 0.351  # small float slack
    assert len(real_in_train) == sum(
        1 for a in assignments if a.split == "train" and a.source != "synthetic"
    )


def test_single_speaker_falls_back_to_session_level_split_without_leaking() -> None:
    """<= 2 real speakers makes true speaker-holdout degenerate (one speaker would have to
    occupy every split alone). split_dataset falls back to session-level splitting for that one
    speaker rather than dumping everything into a single split — still must not leak a *session*
    across splits, which the assertion doesn't check (it checks speakers) but is verified here
    directly.
    """
    turns = [
        TurnRecord(
            turn_id=f"t-{s}-{i}",
            session_id=f"session-{s}",
            speaker_key="only-speaker",
            source="self",
        )
        for s in range(10)
        for i in range(10)
    ]
    assignments = split_dataset(turns)
    counts = split_counts(assignments)
    assert counts["train"] > 0
    assert counts["validation"] > 0 or counts["test"] > 0  # some holdout still happens

    session_to_splits: dict[str, set[str]] = {}
    for a in assignments:
        session_to_splits.setdefault(a.session_id, set()).add(a.split)
    assert all(len(s) == 1 for s in session_to_splits.values())


def test_hash_reproducible_across_two_identical_builds() -> None:
    turns = _make_turns(n_speakers=10, turns_per_speaker=5)
    assignments_a = split_dataset(list(turns))
    assignments_b = split_dataset(list(reversed(turns)))  # different input order

    hash_a = compute_dataset_revision_hash(assignments_a, label_ids=["l1", "l2"])
    hash_b = compute_dataset_revision_hash(assignments_b, label_ids=["l2", "l1"])
    assert hash_a == hash_b


def test_hash_changes_when_split_assignment_changes() -> None:
    turns = _make_turns(n_speakers=10, turns_per_speaker=5)
    assignments = split_dataset(turns)
    hash_before = compute_dataset_revision_hash(assignments, label_ids=[])

    mutated = list(assignments)
    from dataclasses import replace

    flipped_split = "validation" if mutated[0].split != "validation" else "test"
    mutated[0] = replace(mutated[0], split=flipped_split)
    hash_after = compute_dataset_revision_hash(mutated, label_ids=[])
    assert hash_before != hash_after


def test_mark_double_labeled_only_tags_requested_turns() -> None:
    turns = _make_turns(n_speakers=5, turns_per_speaker=4)
    assignments = split_dataset(turns)
    subset = {assignments[0].turn_id, assignments[1].turn_id}
    tagged = mark_double_labeled(assignments, subset)
    for a in tagged:
        assert a.double_labeled == (a.turn_id in subset)


def test_source_breakdown_counts_each_source() -> None:
    turns = _make_turns(n_speakers=5, turns_per_speaker=2, source="self")
    assignments = split_dataset(turns)
    breakdown = source_breakdown(assignments)
    assert breakdown["self"] == 10
    assert breakdown["recruited"] == 0
    assert breakdown["synthetic"] == 0
