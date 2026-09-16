"""docs/phase-5-BUILD.md TASK 5.4c: isotonic calibration per criterion, fitted on validation,
evaluated on test, never fitted on test. `CalibrationGuard` makes that last rule a runtime
assertion, not just a docstring — TASK 5.4's own acceptance criterion: "a test asserts test data
is never touched."
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.isotonic import IsotonicRegression


class ForbiddenSplitFitError(Exception):
    pass


@dataclass
class CalibrationGuard:
    """Wrap the one IsotonicRegression.fit() call site with this so fitting on anything tagged
    "test" raises immediately, instead of silently producing an optimistic, invalid metric
    (docs/phase-5-LEARN.md §12's pitfall table: "Fitting calibration on test -> Optimistic,
    invalid -> Fit on validation").
    """

    fit_calls: int = 0

    def guarded_fit(
        self, model: IsotonicRegression, raw: list[float], target: list[float], *, split: str
    ) -> None:
        if split == "test":
            raise ForbiddenSplitFitError(
                "Isotonic calibration must never be fit on the test split "
                "(docs/phase-5-BUILD.md TASK 5.4c)."
            )
        model.fit(raw, target)
        self.fit_calls += 1


def fit_isotonic_per_criterion(
    raw_by_criterion: dict[str, list[float]],
    target_by_criterion: dict[str, list[float]],
    *,
    split: str,
    guard: CalibrationGuard | None = None,
) -> dict[str, IsotonicRegression]:
    guard = guard or CalibrationGuard()
    models: dict[str, IsotonicRegression] = {}
    for criterion, raw in raw_by_criterion.items():
        target = target_by_criterion[criterion]
        model = IsotonicRegression(y_min=1.0, y_max=5.0, out_of_bounds="clip")
        guard.guarded_fit(model, raw, target, split=split)
        models[criterion] = model
    return models


def apply_calibration(
    models: dict[str, IsotonicRegression], raw_by_criterion: dict[str, list[float]]
) -> dict[str, list[float]]:
    return {
        criterion: list(model.predict(raw_by_criterion[criterion]))
        for criterion, model in models.items()
        if criterion in raw_by_criterion
    }
