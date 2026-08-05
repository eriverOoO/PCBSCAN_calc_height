import numpy as np
import pytest

from pcb_fpp_decoder.calibration import (
    Calibration,
    metric_rig_compatibility,
    phase_linear_height,
    structured_light_calibration_report,
    triangulation_height,
)


def test_metric_rig_compatibility_accepts_camera_tilt_calibration_provenance():
    calibration = Calibration(
        arrays={
            "rig_layout": np.array("camera_tilt_30_projector_vertical"),
            "camera_tilt_deg": np.array(30.0, dtype=np.float32),
            "projector_tilt_deg": np.array(0.0, dtype=np.float32),
            "calibration_id": np.array("camera_tilt_30_v1"),
        }
    )
    report = metric_rig_compatibility(
        calibration,
        {
            "rig_layout": "camera_tilt_30_projector_vertical",
            "camera_tilt_deg": 30.0,
            "projector_tilt_deg": 0.0,
            "calibration_id": "camera_tilt_30_v1",
        },
    )

    assert report["status"] == "matched"


def test_metric_rig_compatibility_rejects_old_projector_tilt_calibration():
    calibration = Calibration(
        data={
            "rig": {
                "layout": "projector_tilt_30_camera_vertical",
                "camera_tilt_deg": 0.0,
                "projector_tilt_deg": 30.0,
            }
        }
    )

    with pytest.raises(ValueError, match="rig_layout"):
        metric_rig_compatibility(
            calibration,
            {
                "rig_layout": "camera_tilt_30_projector_vertical",
                "camera_tilt_deg": 30.0,
                "projector_tilt_deg": 0.0,
            },
        )


def test_phase_linear_height_uses_nested_calibration_sign_offset_and_scale():
    calibration = Calibration(
        data={
            "phase_linear": {
                "phase_per_mm": 20.0,
                "offset_phase": -0.1,
                "height_sign": -1.0,
            }
        }
    )
    delta = np.array([[-0.1, -20.1, -40.1]], dtype=np.float32)

    height, parameters = phase_linear_height(delta, calibration)

    np.testing.assert_allclose(height, [[0.01, 1.01, 2.01]], atol=1e-6)
    assert parameters == {
        "phase_per_mm": 20.0,
        "offset_phase": -0.1,
        "height_sign": -1.0,
    }


def test_phase_linear_height_accepts_view_specific_position_maps():
    calibration = Calibration(
        arrays={
            "phase_linear_phase_per_mm_0": np.array(
                [[10.0, np.nan], [20.0, 40.0]], dtype=np.float32
            ),
            "phase_linear_offset_phase_0": np.array(
                [[0.0, np.nan], [2.0, 4.0]], dtype=np.float32
            ),
            "phase_linear_height_sign_0": np.array(-1.0, dtype=np.float32),
        }
    )
    delta = np.array([[-10.0, -10.0], [-22.0, -44.0]], dtype=np.float32)

    height, parameters = phase_linear_height(delta, calibration, view_angle=0)

    np.testing.assert_allclose(height, [[1.0, np.nan], [1.0, 1.0]], equal_nan=True)
    assert parameters["phase_per_mm"]["kind"] == "map"
    assert parameters["phase_per_mm"]["shape"] == [2, 2]
    assert parameters["height_sign"] == -1.0


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


def test_structured_light_calibration_report_accepts_nominal_moreno_taubin_setup():
    calibration = Calibration(
        data={
            "structured_light_calibration": {
                "method": "moreno_taubin_local_homography",
                "capture": {
                    "pose_count": 12,
                    "full_white_required": True,
                    "gray_code_axes": ["x", "y"],
                    "board_locked_during_sequence": True,
                },
                "local_homography": {
                    "patch_size_px": 47,
                    "min_decoded_points": 1200,
                },
                "reprojection_error": {
                    "camera_rms_px": 0.12,
                    "projector_rms_px": 0.18,
                    "stereo_rms_px": 0.22,
                    "target_max_px": 0.35,
                },
            }
        }
    )

    report = structured_light_calibration_report(calibration)

    assert report["available"] is True
    assert report["capture"]["pose_count_ok"] is True
    assert report["local_homography"]["patch_size_ok"] is True
    assert report["reprojection_error"]["passed"] is True
    assert report["warnings"] == []


def test_structured_light_calibration_report_warns_on_risky_setup():
    calibration = Calibration(
        data={
            "structured_light_calibration": {
                "capture": {
                    "pose_count": 3,
                    "full_white_required": False,
                    "board_locked_during_sequence": False,
                },
                "local_homography": {"patch_size_px": 31},
                "reprojection_error": {
                    "projector_rms_px": 0.51,
                    "target_max_px": 0.35,
                },
            }
        }
    )

    report = structured_light_calibration_report(calibration)

    assert report["capture"]["pose_count_ok"] is False
    assert report["local_homography"]["patch_size_ok"] is False
    assert report["reprojection_error"]["passed"] is False
    assert len(report["warnings"]) == 5
