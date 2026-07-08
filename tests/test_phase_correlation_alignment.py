from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from pcb_fpp_decoder.phase_correlation_alignment import (
    estimate_phase_correlation_transform,
    save_alignment_json,
)


def test_estimate_phase_correlation_transform_refines_180_rotation(tmp_path):
    cv2 = pytest.importorskip("cv2")

    height, width = 96, 128
    rng = np.random.default_rng(2026)
    target = rng.normal(size=(height, width)).astype(np.float32)
    target = cv2.GaussianBlur(target, (0, 0), 2.0)
    target = cv2.normalize(target, None, 20, 235, cv2.NORM_MINMAX).astype(np.uint8)

    expected = np.array(
        [[-1.0, 0.0, width - 1.0 + 3.4], [0.0, -1.0, height - 1.0 - 2.7]],
        dtype=np.float32,
    )
    target_to_source = cv2.invertAffineTransform(expected)
    source = cv2.warpAffine(
        target,
        target_to_source,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    input_dir = tmp_path / "deg_0"
    input_180_dir = tmp_path / "deg_180"
    input_dir.mkdir()
    input_180_dir.mkdir()
    Image.fromarray(target).save(input_dir / "pattern_000.png")
    Image.fromarray(source).save(input_180_dir / "pattern_000.png")

    result = estimate_phase_correlation_transform(input_dir, input_180_dir)

    assert result.transform_kind == "affine"
    assert result.response > 0.5
    np.testing.assert_allclose(np.asarray(result.matrix), expected, atol=0.35)


def test_save_phase_correlation_alignment_json(tmp_path):
    cv2 = pytest.importorskip("cv2")

    height, width = 64, 64
    target = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(target, (20, 23), 8, 210, -1)
    cv2.rectangle(target, (36, 35), (52, 50), 120, -1)
    source = np.rot90(target, 2).astype(np.uint8)

    input_dir = tmp_path / "deg_0"
    input_180_dir = tmp_path / "deg_180"
    output_path = tmp_path / "phase_transform.json"
    input_dir.mkdir()
    input_180_dir.mkdir()
    Image.fromarray(target).save(input_dir / "pattern_000.png")
    Image.fromarray(source).save(input_180_dir / "pattern_000.png")

    result = estimate_phase_correlation_transform(input_dir, input_180_dir)
    save_alignment_json(
        output_path,
        result,
        input_dir=input_dir,
        input_180_dir=input_180_dir,
        image_name="pattern_000.png",
        use_hann_window=True,
    )

    assert output_path.exists()
    payload = output_path.read_text(encoding="utf-8")
    assert '"phase_correlation"' in payload
    assert '"affine"' in payload
