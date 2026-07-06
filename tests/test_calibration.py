import numpy as np
import pytest

from pcb_fpp_decoder.calibration import Calibration, triangulation_height


def test_triangulation_accepts_position_dependent_npz_maps():
    delta_phi = np.full((2, 3), 0.25, dtype=np.float32)
    p_map = np.array([[4.0, 5.0, 6.0], [7.0, 8.0, 9.0]], dtype=np.float32)
    calibration = Calibration(
        arrays={
            "d": np.array(300.0, dtype=np.float32),
            "l": np.array(120.0, dtype=np.float32),
            "p": p_map,
        }
    )

    height, params = triangulation_height(delta_phi, calibration)

    expected = (delta_phi * p_map * 300.0) / (delta_phi * p_map + 2.0 * np.pi * 120.0)
    np.testing.assert_allclose(height, expected.astype(np.float32))
    assert params["p"]["kind"] == "map"
    assert params["p"]["shape"] == [2, 3]


def test_triangulation_rejects_unbroadcastable_maps():
    delta_phi = np.full((2, 3), 0.25, dtype=np.float32)
    calibration = Calibration(
        arrays={
            "d": np.array(300.0, dtype=np.float32),
            "l": np.array(120.0, dtype=np.float32),
            "p": np.ones((4, 4), dtype=np.float32),
        }
    )

    with pytest.raises(ValueError, match="cannot broadcast"):
        triangulation_height(delta_phi, calibration)
