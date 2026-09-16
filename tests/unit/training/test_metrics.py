"""docs/phase-5-BUILD.md TASK 5.3c/5.5a — QWK is the headline metric this whole phase reports
beside the human ceiling, so it earns real correctness tests, not just a call-it-and-hope smoke
check. Cross-checked against sklearn's cohen_kappa_score(weights="quadratic") for the general
case, plus hand-computed edge cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import sklearn.metrics as sklearn_metrics

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services" / "training"))

from metrics import (  # noqa: E402
    adjacent_accuracy,
    expected_calibration_error,
    mean_absolute_error,
    quadratic_weighted_kappa,
    spearman_correlation,
)


def test_perfect_agreement_is_kappa_one() -> None:
    y = [1, 2, 3, 4, 5, 3, 2, 1]
    assert quadratic_weighted_kappa(y, y) == 1.0


def test_all_identical_ratings_both_sides_is_kappa_one_not_undefined() -> None:
    assert quadratic_weighted_kappa([3, 3, 3, 3], [3, 3, 3, 3]) == 1.0


def test_matches_sklearn_on_a_known_case() -> None:
    y_true = [1, 2, 3, 4, 5, 1, 3, 5, 2, 4]
    y_pred = [1, 2, 2, 4, 5, 2, 3, 4, 2, 5]
    expected = sklearn_metrics.cohen_kappa_score(y_true, y_pred, weights="quadratic")
    actual = quadratic_weighted_kappa(y_true, y_pred)
    assert abs(actual - expected) < 1e-9


def test_near_miss_penalised_far_less_than_gross_error() -> None:
    """docs/phase-5-LEARN.md §3: "predicting 4 when the truth is 5 costs 1/16th of predicting
    1." Verified via two small confusion patterns rather than asserting the raw fraction, since
    kappa also depends on the marginal distributions - the point is the *ordering*: near misses
    hurt less than gross ones on the same underlying rating distribution.
    """
    y_true = [5, 5, 5, 5, 1, 1, 1, 1]
    near_miss_pred = [4, 4, 4, 4, 1, 1, 1, 1]  # off by one on half the items
    gross_error_pred = [1, 1, 1, 1, 1, 1, 1, 1]  # off by four on half the items

    kappa_near = quadratic_weighted_kappa(y_true, near_miss_pred)
    kappa_gross = quadratic_weighted_kappa(y_true, gross_error_pred)
    assert kappa_near > kappa_gross


def test_worse_than_chance_is_negative() -> None:
    y_true = [1, 1, 1, 1, 5, 5, 5, 5]
    y_pred = [5, 5, 5, 5, 1, 1, 1, 1]  # perfectly inverted
    assert quadratic_weighted_kappa(y_true, y_pred) < 0


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError):
        quadratic_weighted_kappa([1, 2], [1])


def test_mean_absolute_error_basic() -> None:
    assert mean_absolute_error([1, 2, 3], [1, 2, 3]) == 0.0
    assert mean_absolute_error([1, 2, 3], [2, 2, 2]) == pytest.approx(2 / 3)


def test_spearman_perfect_monotonic() -> None:
    assert abs(spearman_correlation([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9


def test_spearman_perfect_inverse() -> None:
    assert abs(spearman_correlation([1, 2, 3, 4], [40, 30, 20, 10]) - (-1.0)) < 1e-9


def test_spearman_handles_ties() -> None:
    result = spearman_correlation([1, 1, 2, 2], [1, 2, 3, 4])
    assert -1.0 <= result <= 1.0


def test_adjacent_accuracy_within_one_point() -> None:
    y_true = [3, 3, 3, 3]
    y_pred = [3, 4, 2, 5]  # 3 within 1 point, 1 (the 5) is not
    assert adjacent_accuracy(y_true, y_pred) == 0.75


def test_ece_zero_for_perfectly_calibrated_confidence() -> None:
    # 10 items at confidence 0.9, exactly 9 correct - matches its own stated confidence exactly.
    confidences = [0.9] * 10
    correct = [True] * 9 + [False]
    assert expected_calibration_error(confidences, correct) < 0.05


def test_ece_high_for_overconfident_predictions() -> None:
    confidences = [0.95] * 10
    correct = [False] * 8 + [True] * 2  # claims 95% confidence, actually 20% accurate
    ece = expected_calibration_error(confidences, correct)
    assert ece > 0.5
