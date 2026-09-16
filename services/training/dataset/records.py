"""Pure data shapes for dataset construction (docs/phase-5-BUILD.md TASK 5.2). Deliberately
free of any DB/ORM import — services/training is its own uv workspace member (docs/decisions/
0003's reasoning applies here too), and split.py's logic is exercised by unit tests with no
database at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SOURCES = ("self", "recruited", "synthetic")
SPLITS = ("train", "validation", "test")

# Task 5.2b: "Cap synthetic at <= 35% of the training split, and 0% of the evaluation split."
MAX_SYNTHETIC_TRAIN_FRACTION = 0.35
TARGET_SPLIT_FRACTIONS = {"train": 0.70, "validation": 0.15, "test": 0.15}


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """One candidate turn for the dataset, already filtered to `speaker="user"` and
    `training_excluded=False` by the caller (services/training/dataset/build.py) — this module
    never re-derives eligibility, it only splits and hashes what it's handed.
    """

    turn_id: str
    session_id: str
    # `sessions.user_id` as text for real turns; a synthetic-batch id (e.g.
    # "synthetic:batch-<n>") for generated turns, which have no real speaker. This is exactly
    # the field the leakage assertion checks — never the session_id, which is 1:1 with a turn's
    # own session and would make the assertion vacuous.
    speaker_key: str
    source: str  # one of SOURCES
    # Existing human/annotator scores for this turn, if any, keyed by criterion — used only to
    # report stratification span, never to decide inclusion.
    scores: dict[str, float] = field(default_factory=dict)
    synthetic_quality_level: int | None = None

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(f"Unknown source {self.source!r}, expected one of {SOURCES}")


@dataclass(frozen=True, slots=True)
class SplitAssignment:
    turn_id: str
    session_id: str
    speaker_key: str
    source: str
    split: str
    double_labeled: bool = False


class SpeakerLeakageError(Exception):
    """Task 5.2c: "Write an assertion that fails the build if any speaker appears in more than
    one split. This is not a warning — it is a build failure." Raised with every offending
    speaker and the splits they leaked into, so the failure is debuggable, not just a bare
    assert.
    """

    def __init__(self, leaks: dict[str, set[str]]) -> None:
        detail = "; ".join(f"{speaker} in {sorted(splits)}" for speaker, splits in leaks.items())
        super().__init__(f"Speaker leakage across splits: {detail}")
        self.leaks = leaks
