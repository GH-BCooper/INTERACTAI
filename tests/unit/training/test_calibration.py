"""docs/phase-5-BUILD.md TASK 5.4's acceptance criterion, verbatim: "Calibration fitted on
validation only (a test asserts test data is never touched)." This is that test.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "training"))

import pytest  # noqa: E402
from calibration import (  # noqa: E402
    CalibrationGuard,
    ForbiddenSplitFitError,
    apply_calibration,
    fit_isotonic_per_criterion,
)
from sklearn.isotonic import IsotonicRegression  # noqa: E402


def test_fitting_on_validation_succeeds() -> None:
    guard = CalibrationGuard()
    model = IsotonicRegression()
    guard.guarded_fit(model, [1.0, 2.0, 3.0], [1.5, 2.5, 3.5], split="validation")
    assert guard.fit_calls == 1


def test_fitting_on_test_raises() -> None:
    guard = CalibrationGuard()
    model = IsotonicRegression()
    with pytest.raises(ForbiddenSplitFitError):
        guard.guarded_fit(model, [1.0, 2.0, 3.0], [1.5, 2.5, 3.5], split="test")
    assert guard.fit_calls == 0


def test_fitting_on_test_raises_even_with_valid_train_data_alongside() -> None:
    """Guards against a caller looping over splits and forgetting to skip test — the guard must
    fire per-call, not just be bypassable by calling fit() directly on later criteria."""
    guard = CalibrationGuard()
    fit_isotonic_per_criterion(
        {"structure": [1.0, 2.0, 3.0]}, {"structure": [1.0, 2.0, 3.0]},
        split="validation", guard=guard,
    )
    with pytest.raises(ForbiddenSplitFitError):
        fit_isotonic_per_criterion(
            {"structure": [4.0, 5.0]}, {"structure": [4.0, 5.0]}, split="test", guard=guard
        )


def test_apply_calibration_maps_raw_onto_the_rubric_scale() -> None:
    models = fit_isotonic_per_criterion(
        {"structure": [1.0, 2.0, 3.0, 4.0, 5.0]},
        {"structure": [1.5, 2.5, 3.0, 4.5, 4.8]},
        split="validation",
    )
    calibrated = apply_calibration(models, {"structure": [1.0, 3.0, 5.0]})
    assert len(calibrated["structure"]) == 3
    assert all(1.0 <= v <= 5.0 for v in calibrated["structure"])
