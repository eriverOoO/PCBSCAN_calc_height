import numpy as np
import pytest

from pcb_fpp_decoder.validation import accuracy_metrics


def test_accuracy_metrics_reports_validity_and_mm_errors():
    estimate = np.array([[0.0, 1.1], [np.nan, 2.8]], dtype=np.float32)
    truth = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)
    region = np.ones((2, 2), dtype=bool)

    report = accuracy_metrics(estimate, truth, region)

    assert report["valid_ratio"] == 0.75
    assert report["bias_mm"] == pytest.approx(-0.1 / 3)
    assert report["mae_mm"] == pytest.approx(0.3 / 3)
    assert report["rmse_mm"] > report["mae_mm"]
