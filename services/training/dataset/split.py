"""Pure split logic — docs/phase-5-BUILD.md TASK 5.2c, the critical part.

    def split_dataset(turns) -> tuple[Train, Val, Test]:
        '''Split by SESSION, and hold out entire SPEAKERS where possible.
        NEVER split by turn.'''

No database, no I/O. services/training/dataset/build.py is the only caller that touches
Postgres; everything here takes/returns plain dataclasses so it can be (and is, in
tests/unit/training/test_dataset_split.py) exercised with hand-built fixtures, including one
that deliberately leaks a speaker across splits to prove the assertion actually fires.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling flat-module convention
from records import (  # noqa: E402
    MAX_SYNTHETIC_TRAIN_FRACTION,
    TARGET_SPLIT_FRACTIONS,
    SpeakerLeakageError,
    SplitAssignment,
    TurnRecord,
)


def _speaker_sort_key(speaker: str) -> str:
    """Deterministic pseudo-random ordering: a hash of the speaker id, not insertion order or
    speaker-id lexical order (which would bias toward whichever ids happen to sort first).
    Reproducible across runs given the same input — required for TASK 5.2d's "dataset revision
    hash reproducible across two identical builds."
    """
    return hashlib.sha256(speaker.encode("utf-8")).hexdigest()


def split_dataset(turns: list[TurnRecord]) -> list[SplitAssignment]:
    """Group by session_id, then by speaker. Assign whole sessions to splits. Hold out entire
    speakers for the test split wherever speaker count allows. Target 70/15/15 by turn count.
    Synthetic turns never enter validation or test (TASK 5.2b: "0% of the evaluation split") —
    they have no real speaker to hold out anyway, so they are assigned to train directly and
    excluded from the speaker-bucketing below entirely.
    """
    real_turns = [t for t in turns if t.source != "synthetic"]
    synthetic_turns = [t for t in turns if t.source == "synthetic"]

    turns_by_speaker: dict[str, list[TurnRecord]] = defaultdict(list)
    for t in real_turns:
        turns_by_speaker[t.speaker_key].append(t)

    speakers = sorted(turns_by_speaker.keys(), key=_speaker_sort_key)
    total_real = len(real_turns)
    target_test = round(total_real * TARGET_SPLIT_FRACTIONS["test"])
    target_val = round(total_real * TARGET_SPLIT_FRACTIONS["validation"])

    assignments: list[SplitAssignment] = []
    speaker_split: dict[str, str] = {}
    test_count = 0
    val_count = 0

    # Greedy bin-packing by whole speaker, in the deterministic pseudo-random order above:
    # fill test first, then validation, everything left over is train. A speaker's turns never
    # split across bins — the entire point of TASK 5.2c.
    for speaker in speakers:
        n = len(turns_by_speaker[speaker])
        if test_count < target_test:
            speaker_split[speaker] = "test"
            test_count += n
        elif val_count < target_val:
            speaker_split[speaker] = "validation"
            val_count += n
        else:
            speaker_split[speaker] = "train"

    # If there's only one speaker (or very few), the loop above dumps everyone into "test" —
    # correct per speaker-holdout rules but useless as a dataset. Fall back to session-level
    # splitting *within* that single speaker's sessions rather than violate the no-single-split
    # guarantee for multi-speaker data. This only engages when true speaker-holdout is
    # impossible (<=2 distinct real speakers); see docs/decisions/0020.
    if len(speakers) <= 2:
        speaker_split = {}
        sessions: dict[str, list[TurnRecord]] = defaultdict(list)
        for t in real_turns:
            sessions[t.session_id].append(t)
        session_ids = sorted(sessions.keys(), key=_speaker_sort_key)
        test_count = val_count = 0
        session_split: dict[str, str] = {}
        for sid in session_ids:
            n = len(sessions[sid])
            if test_count < target_test:
                session_split[sid] = "test"
                test_count += n
            elif val_count < target_val:
                session_split[sid] = "validation"
                val_count += n
            else:
                session_split[sid] = "train"
        for t in real_turns:
            assignments.append(
                SplitAssignment(
                    turn_id=t.turn_id,
                    session_id=t.session_id,
                    speaker_key=t.speaker_key,
                    source=t.source,
                    split=session_split[t.session_id],
                )
            )
    else:
        for t in real_turns:
            assignments.append(
                SplitAssignment(
                    turn_id=t.turn_id,
                    session_id=t.session_id,
                    speaker_key=t.speaker_key,
                    source=t.source,
                    split=speaker_split[t.speaker_key],
                )
            )

    for t in synthetic_turns:
        assignments.append(
            SplitAssignment(
                turn_id=t.turn_id,
                session_id=t.session_id,
                speaker_key=t.speaker_key,
                source=t.source,
                split="train",
            )
        )

    return assignments


def enforce_synthetic_cap(assignments: list[SplitAssignment]) -> list[SplitAssignment]:
    """TASK 5.2b: "Cap synthetic at <= 35% of the training split." If a build's synthetic pool
    exceeds the cap, drop the excess (deterministically, by turn_id order) rather than silently
    over-representing generated tails — an oversized synthetic share is exactly the shortcut
    TASK 5.2b warns against ("does not learn 'the synthetic style' as a shortcut feature").
    """
    train = [a for a in assignments if a.split == "train"]
    synthetic_train = sorted((a for a in train if a.source == "synthetic"), key=lambda a: a.turn_id)
    real_train_count = sum(1 for a in train if a.source != "synthetic")
    if real_train_count == 0:
        max_synthetic = 0
    else:
        # cap × real / (1 - cap) solves "synthetic <= cap * (real + synthetic)" for synthetic.
        max_synthetic = int(
            real_train_count * MAX_SYNTHETIC_TRAIN_FRACTION / (1 - MAX_SYNTHETIC_TRAIN_FRACTION)
        )
    if len(synthetic_train) <= max_synthetic:
        return assignments

    drop_ids = {a.turn_id for a in synthetic_train[max_synthetic:]}
    return [a for a in assignments if a.turn_id not in drop_ids]


def assert_no_speaker_leakage(assignments: list[SplitAssignment]) -> None:
    """TASK 5.2c: "Write an assertion that fails the build if any speaker appears in more than
    one split. This is not a warning — it is a build failure." Synthetic turns are exempt: they
    share no real speaker identity to leak (each synthetic-batch id is confined to train by
    construction in split_dataset above, so this would never fire for them anyway, but the
    exemption is stated explicitly rather than relying on that as an accident of the caller).
    """
    speaker_splits: dict[str, set[str]] = defaultdict(set)
    for a in assignments:
        if a.source == "synthetic":
            continue
        speaker_splits[a.speaker_key].add(a.split)
    leaked = {speaker: splits for speaker, splits in speaker_splits.items() if len(splits) > 1}
    if leaked:
        raise SpeakerLeakageError(leaked)


def mark_double_labeled(
    assignments: list[SplitAssignment], double_labeled_turn_ids: set[str]
) -> list[SplitAssignment]:
    """TASK 5.3c: the 200-turn IAA overlap subset. A pure re-tag, kept separate from
    split_dataset so the subset can be (re)chosen after annotation capacity is known without
    re-running the split itself."""
    return [
        replace(a, double_labeled=True) if a.turn_id in double_labeled_turn_ids else a
        for a in assignments
    ]


def compute_dataset_revision_hash(assignments: list[SplitAssignment], label_ids: list[str]) -> str:
    """TASK 5.2d: "Every build produces a content hash over (turn_ids, label_ids, split
    assignment)." Sorted, canonical JSON so the same inputs always hash identically regardless
    of query/iteration order (TASK 5.2d's own acceptance criterion: "reproducible across two
    identical builds").
    """
    canonical = json.dumps(
        {
            "turn_ids": sorted(a.turn_id for a in assignments),
            "label_ids": sorted(label_ids),
            "splits": {a.turn_id: a.split for a in sorted(assignments, key=lambda a: a.turn_id)},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def split_counts(assignments: list[SplitAssignment]) -> dict[str, int]:
    counts = {"train": 0, "validation": 0, "test": 0}
    for a in assignments:
        counts[a.split] += 1
    return counts


def source_breakdown(assignments: list[SplitAssignment]) -> dict[str, int]:
    counts = {"self": 0, "recruited": 0, "synthetic": 0}
    for a in assignments:
        counts[a.source] += 1
    return counts
