"""docs/phase-5-BUILD.md TASK 5.5d — the pure sampling decision behind shadow mode."""

from __future__ import annotations

from services.coach.app.report.build import should_run_shadow_scoring


def test_zero_rate_never_runs() -> None:
    assert all(not should_run_shadow_scoring(0.0) for _ in range(50))


def test_rate_of_one_always_runs() -> None:
    assert all(should_run_shadow_scoring(1.0) for _ in range(50))


def test_negative_rate_never_runs() -> None:
    assert should_run_shadow_scoring(-0.5) is False


def test_rate_above_one_always_runs() -> None:
    assert should_run_shadow_scoring(1.5) is True


def test_roughly_matches_the_configured_rate_over_many_trials() -> None:
    n = 5000
    rate = 0.10
    hits = sum(1 for _ in range(n) if should_run_shadow_scoring(rate))
    observed_rate = hits / n
    assert abs(observed_rate - rate) < 0.03  # generous tolerance, not a flaky statistical test
