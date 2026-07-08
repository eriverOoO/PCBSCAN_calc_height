from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from pcb_fpp_decoder.aruco_alignment import estimate_aruco_transform
from pcb_fpp_decoder.aruco_marker import generate_marker_image


def test_estimate_aruco_transform_from_white_pattern(tmp_path):
    cv2 = pytest.importorskip("cv2")
    if not hasattr(cv2, "aruco"):
        pytest.skip("OpenCV ArUco module is not available")

    target = Image.new("L", (600, 600), 255)
    for marker_id, xy in ((0, (110, 110)), (1, (390, 390))):
        marker, _marker_pixels, _quiet_pixels = generate_marker_image(
            marker_id,
            "DICT_4X4_50",
            marker_size_mm=8.0,
            quiet_zone_mm=2.0,
            dpi=254,
            label=False,
        )
        target.paste(marker, xy)

    target_array = np.asarray(target)
    target_to_source = cv2.getRotationMatrix2D((300.0, 300.0), 178.7, 1.0)
    source_array = cv2.warpAffine(
        target_array,
        target_to_source,
        (600, 600),
        flags=cv2.INTER_NEAREST,
        borderValue=255,
    )

    input_dir = tmp_path / "deg_0"
    input_180_dir = tmp_path / "deg_180"
    input_dir.mkdir()
    input_180_dir.mkdir()
    Image.fromarray(target_array).save(input_dir / "pattern_000.png")
    Image.fromarray(source_array).save(input_180_dir / "pattern_000.png")

    result = estimate_aruco_transform(
        input_dir,
        input_180_dir,
        dictionary_name="DICT_4X4_50",
        marker_ids=[0, 1],
        method="homography",
    )

    assert result.transform_kind == "homography"
    assert result.marker_ids == [0, 1]
    assert result.reprojection_rmse_px < 0.5
    assert result.deviation_from_180_deg == pytest.approx(1.3, abs=0.3)
