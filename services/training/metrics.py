"""Pure metric functions shared by the annotation IAA report (annotate/iaa.py), the training
loop's early-stopping criterion (train.py), and the eval harness (eval/harness.py). No I/O, no
database — every function here is unit-tested directly in tests/unit/training/test_metrics.py.

docs/phase-5-BUILD.md/-LEARN.md §3: quadratic weighted kappa is the headline metric.
"""

from __future__ import annotations

import math


def quadratic_weighted_kappa(
    y_true: list[int], y_pred: list[int], *, min_rating: int = 1, max_rating: int = 5
) -> float:
    """
            sum(w_ij * O_ij)
    kappa = 1 - ----------------      w_ij = (i - j)^2 / (N - 1)^2
            sum(w_ij * E_ij)

    O is the observed confusion matrix, E the expected one under independence (the outer
    product of the two marginals, scaled to the same total as O). 1.0 is perfect agreement, 0.0
    is chance, negative is worse than chance. Returns 1.0 for the degenerate case of a single
    rating value shared by both raters on every item (perfect trivial agreement — no
    disagreement is possible to measure), matching sklearn's own convention.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    if not y_true:
        raise ValueError("cannot compute kappa over zero items")

    n_ratings = max_rating - min_rating + 1
    observed = [[0] * n_ratings for _ in range(n_ratings)]
    for t, p in zip(y_true, y_pred, strict=True):
        observed[t - min_rating][p - min_rating] += 1

    n = len(y_true)
    true_hist = [sum(row) for row in observed]
    pred_hist = [sum(observed[i][j] for i in range(n_ratings)) for j in range(n_ratings)]

    numerator = 0.0
    denominator = 0.0
    for i in range(n_ratings):
        for j in range(n_ratings):
            weight = ((i - j) ** 2) / ((n_ratings - 1) ** 2) if n_ratings > 1 else 0.0
            expected = (true_hist[i] * pred_hist[j]) / n
            numerator += weight * observed[i][j]
            denominator += weight * expected

    if denominator == 0.0:
        # Every rating identical for both raters (e.g. all 3s) — no disagreement was even
        # possible to express, so by convention this is treated as perfect agreement, not an
        # undefined 0/0.
        return 1.0
    return 1.0 - (numerator / denominator)


def mean_absolute_error(y_true: list[float], y_pred: list[float]) -> float:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    if not y_true:
        raise ValueError("cannot compute MAE over zero items")
    return sum(abs(t - p) for t, p in zip(y_true, y_pred, strict=True)) / len(y_true)


def spearman_correlation(y_true: list[float], y_pred: list[float]) -> float:
    """Rank-based correlation, computed by hand (no scipy dependency needed for this one) so it
    matches this module's no-I/O, dependency-light design. Ties broken by average rank.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    n = len(y_true)
    if n < 2:
        raise ValueError("spearman correlation needs at least 2 items")

    def _average_ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            average_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = average_rank
            i = j + 1
        return ranks

    rank_true = _average_ranks(y_true)
    rank_pred = _average_ranks(y_pred)
    mean_true = sum(rank_true) / n
    mean_pred = sum(rank_pred) / n
    cov = sum(
        (rt - mean_true) * (rp - mean_pred)
        for rt, rp in zip(rank_true, rank_pred, strict=True)
    )
    var_true = sum((rt - mean_true) ** 2 for rt in rank_true)
    var_pred = sum((rp - mean_pred) ** 2 for rp in rank_pred)
    if var_true == 0.0 or var_pred == 0.0:
        return 1.0 if var_true == var_pred else 0.0
    return cov / math.sqrt(var_true * var_pred)


def adjacent_accuracy(y_true: list[float], y_pred: list[float], *, tolerance: float = 1.0) -> float:
    """Task 5.5a: "Fraction within one point — the practical usefulness threshold.\""""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    if not y_true:
        raise ValueError("cannot compute adjacent accuracy over zero items")
    within = sum(1 for t, p in zip(y_true, y_pred, strict=True) if abs(t - p) <= tolerance)
    return within / len(y_true)


def expected_calibration_error(
    confidences: list[float], correct: list[bool], *, n_bins: int = 10
) -> float:
    """Task 5.5a: "Whether stated confidence means anything." Standard binned ECE: within each
    confidence bucket, |mean stated confidence - actual accuracy|, weighted by bucket size.
    """
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must be the same length")
    if not confidences:
        raise ValueError("cannot compute ECE over zero items")

    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for conf, is_correct in zip(confidences, correct, strict=True):
        bin_index = min(int(conf * n_bins), n_bins - 1)
        bins[bin_index].append((conf, is_correct))

    n = len(confidences)
    ece = 0.0
    for bucket in bins:
        if not bucket:
            continue
        bucket_confidence = sum(c for c, _ in bucket) / len(bucket)
        bucket_accuracy = sum(1 for _, correct_flag in bucket if correct_flag) / len(bucket)
        ece += (len(bucket) / n) * abs(bucket_confidence - bucket_accuracy)
    return ece
