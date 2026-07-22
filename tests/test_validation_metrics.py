from __future__ import annotations

import numpy as np

from validation_harness.metrics import detection_statistics, error_statistics, evaluate_regions
from validation_harness.regions import build_region_masks


def test_error_metrics_are_region_scoped_and_keep_phase_separate_from_height() -> None:
    truth = np.zeros((2, 3), dtype=float)
    prediction = np.array([[1.0, -1.0, np.nan], [2.0, 0.0, 4.0]])
    region = np.array([[1, 1, 1], [0, 0, 0]], dtype=bool)
    stats = error_statistics(prediction, truth, region)

    assert stats["pixel_count"] == 3
    assert stats["valid_count"] == 2
    assert stats["bias"] == 0.0
    assert stats["mae"] == 1.0
    report = evaluate_regions(
        phase_prediction=prediction,
        phase_truth=truth,
        height_prediction=prediction * 0.5,
        height_truth=truth,
        regions={"pcb_all": region},
    )
    assert set(report["pcb_all"]) == {"phase_error_rad", "metric_height_error_mm"}


def test_detection_precision_recall_and_region_taxonomy() -> None:
    expected = np.array([[1, 1], [0, 0]], dtype=bool)
    detected = np.array([[1, 0], [1, 0]], dtype=bool)
    stats = detection_statistics(detected, expected)
    assert stats["precision"] == 0.5
    assert stats["recall"] == 0.5
    assert stats["f1"] == 0.5

    masks = build_region_masks(
        (2, 2),
        object_mask=np.ones((2, 2), bool),
        height_gt=np.array([[0.0, 1.0], [2.0, 0.0]]),
        material_id=np.array([[0, 4], [2, 3]], dtype=np.uint8),
        impairment_masks={"shadow": expected, "saturation": detected},
        view_valid_masks=(expected, detected),
    )
    assert masks["components_ge_1mm"].sum() == 2
    assert masks["view_overlap"].sum() == 1
    assert masks["single_view"].sum() == 2
