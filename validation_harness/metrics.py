from __future__ import annotations

from typing import Mapping

import numpy as np


def error_statistics(
    prediction: np.ndarray,
    truth: np.ndarray,
    region: np.ndarray,
    valid: np.ndarray | None = None,
) -> dict[str, float | int | None]:
    predicted = np.asarray(prediction, dtype=np.float64)
    expected = np.asarray(truth, dtype=np.float64)
    mask = np.asarray(region, dtype=bool)
    if predicted.shape != expected.shape or mask.shape != expected.shape:
        raise ValueError("prediction, truth, and region masks must have the same shape")
    finite = np.isfinite(predicted) & np.isfinite(expected)
    if valid is not None:
        finite &= np.asarray(valid, dtype=bool)
    selected = mask & finite
    count = int(np.count_nonzero(mask))
    valid_count = int(np.count_nonzero(selected))
    if valid_count == 0:
        return {
            "pixel_count": count,
            "valid_count": 0,
            "valid_ratio": 0.0 if count else None,
            "bias": None,
            "mae": None,
            "rmse": None,
            "median_absolute_error": None,
            "p95_absolute_error": None,
            "p99_absolute_error": None,
            "max_absolute_error": None,
        }
    errors = predicted[selected] - expected[selected]
    absolute = np.abs(errors)
    return {
        "pixel_count": count,
        "valid_count": valid_count,
        "valid_ratio": float(valid_count / count) if count else None,
        "bias": float(np.mean(errors)),
        "mae": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(errors * errors))),
        "median_absolute_error": float(np.median(absolute)),
        "p95_absolute_error": float(np.percentile(absolute, 95)),
        "p99_absolute_error": float(np.percentile(absolute, 99)),
        "max_absolute_error": float(np.max(absolute)),
    }


def detection_statistics(
    detected: np.ndarray,
    expected: np.ndarray,
    region: np.ndarray | None = None,
) -> dict[str, float | int]:
    prediction = np.asarray(detected, dtype=bool)
    truth = np.asarray(expected, dtype=bool)
    if prediction.shape != truth.shape:
        raise ValueError("detection masks must have the same shape")
    scope = np.ones(truth.shape, dtype=bool) if region is None else np.asarray(region, dtype=bool)
    tp = int(np.count_nonzero(scope & prediction & truth))
    fp = int(np.count_nonzero(scope & prediction & ~truth))
    fn = int(np.count_nonzero(scope & ~prediction & truth))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(2 * precision * recall / (precision + recall))
        if precision + recall
        else 0.0,
    }


def evaluate_regions(
    *,
    phase_prediction: np.ndarray | None,
    phase_truth: np.ndarray | None,
    height_prediction: np.ndarray | None,
    height_truth: np.ndarray | None,
    regions: Mapping[str, np.ndarray],
    valid: np.ndarray | None = None,
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    report: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for name, region in regions.items():
        values: dict[str, dict[str, float | int | None]] = {}
        if phase_prediction is not None and phase_truth is not None:
            values["phase_error_rad"] = error_statistics(
                phase_prediction, phase_truth, region, valid
            )
        if height_prediction is not None and height_truth is not None:
            values["metric_height_error_mm"] = error_statistics(
                height_prediction, height_truth, region, valid
            )
        report[name] = values
    return report
