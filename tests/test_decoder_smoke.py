from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder


def _save(path: Path, array: np.ndarray) -> None:
    Image.fromarray(np.clip(array, 0, 255).astype(np.uint8)).save(path)


def _write_synthetic_scan(
    folder: Path,
    width: int = 80,
    height: int = 48,
    inverted_gray: bool = False,
    low_gray_for_pair: bool = False,
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    y, x = np.indices((height, width))
    k = (x // 5).astype(np.uint16)
    phi = ((x % 5) / 5.0 * 2.0 * np.pi).astype(np.float32)
    white = np.full((height, width), 240.0, dtype=np.float32)
    black = np.full((height, width), 10.0, dtype=np.float32)
    _save(folder / "pattern_000.png", white)
    _save(folder / "pattern_001.png", black)

    gray = k ^ (k >> 1)
    for bit in range(8):
        mask = ((gray >> (7 - bit)) & 1).astype(bool)
        if low_gray_for_pair:
            image = np.where(mask, 120.0, 40.0)
        else:
            image = np.where(mask, 220.0, 25.0)
        _save(folder / f"pattern_{2 + bit:03d}.png", image)
        if inverted_gray:
            inverted = np.where(mask, 40.0, 120.0) if low_gray_for_pair else 255.0 - image
            _save(folder / f"pattern_{14 + bit:03d}.png", inverted)

    mean = 125.0
    amp = 70.0
    sine_images = {
        10: mean + amp * np.sin(phi),
        11: mean - amp * np.cos(phi),
        12: mean - amp * np.sin(phi),
        13: mean + amp * np.cos(phi),
    }
    for pattern_id, image in sine_images.items():
        _save(folder / f"pattern_{pattern_id:03d}.png", image)


def _copy_rotated_scan(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.glob("*.png"):
        image = np.asarray(Image.open(path))
        Image.fromarray(np.rot90(image, 2).astype(np.uint8)).save(target / path.name)


def _invalidate_columns(folder: Path, start_col: int) -> None:
    for path in folder.glob("*.png"):
        image = np.asarray(Image.open(path)).copy()
        image[:, start_col:] = 10
        Image.fromarray(image.astype(np.uint8)).save(path)


def test_synthetic_scan_end_to_end(tmp_path):
    input_dir = tmp_path / "captures" / "scan_001" / "deg_0"
    output_dir = tmp_path / "processed" / "scan_001" / "deg_0"
    _write_synthetic_scan(input_dir)

    config = DecodeConfig(
        min_signal=20,
        saturation_threshold=250,
        dark_threshold=5,
        modulation_threshold=0.05,
        apply_half_period_correction=True,
        detrend=True,
        median_filter=3,
    )
    result = PcbFppDecoder(config).decode(input_dir, output_dir)

    assert (output_dir / "decode_report.json").exists()
    assert (output_dir / "phase" / "absolute_phase.npy").exists()
    assert (output_dir / "height" / "height_relative.npy").exists()
    assert (output_dir / "point_cloud" / "point_cloud.ply").exists()
    assert result.gray.stripe_order_k.shape == (48, 80)
    assert result.report["mask_coverage"]["combined_mask_ratio"] > 0.95
    assert int(result.gray.stripe_order_k.max()) == 15


def test_reference_phase_subtraction_cancels_flat_projector_keystone(tmp_path):
    input_dir = tmp_path / "captures" / "scan_ref" / "deg_0"
    ref_output = tmp_path / "processed" / "reference"
    output_dir = tmp_path / "processed" / "object"
    _write_synthetic_scan(input_dir)

    PcbFppDecoder(DecodeConfig()).decode(input_dir, ref_output)
    reference_phase = ref_output / "phase" / "absolute_phase.npy"
    config = DecodeConfig(
        height_mode="reference",
        reference_phase=reference_phase,
        median_filter=0,
        detrend=False,
    )
    result = PcbFppDecoder(config).decode(input_dir, output_dir)

    assert result.height.reference_used
    assert (output_dir / "height" / "delta_phase.npy").exists()
    finite_height = result.height.height[result.height.mask]
    assert np.nanmax(np.abs(finite_height)) < 1e-6
    assert result.report["optical_setup"]["keystone_compensation"]["active"] is True


def test_inverted_gray_pair_decodes_low_contrast_gray_patterns(tmp_path):
    input_dir = tmp_path / "captures" / "scan_inv_gray" / "deg_0"
    output_dir = tmp_path / "processed" / "scan_inv_gray" / "deg_0"
    _write_synthetic_scan(input_dir, inverted_gray=True, low_gray_for_pair=True)

    config = DecodeConfig(
        gray_decode_mode="inverted_pair",
        gray_pair_min_contrast=0.05,
        min_signal=20,
        saturation_threshold=250,
        dark_threshold=5,
        modulation_threshold=0.05,
        median_filter=0,
    )
    result = PcbFppDecoder(config).decode(input_dir, output_dir)

    assert result.gray.mode == "inverted_pair"
    assert (output_dir / "gray" / "gray_valid_mask.png").exists()
    assert (output_dir / "gray" / "gray_confidence.npy").exists()
    assert result.report["stripe_order"]["decode_mode"] == "inverted_pair"
    assert result.report["mask_coverage"]["gray_valid_mask_ratio"] > 0.95
    assert result.report["mask_coverage"]["combined_mask_ratio"] > 0.95
    assert int(result.gray.stripe_order_k.max()) == 15


def test_metric_height_mode_requires_reference_phase(tmp_path):
    input_dir = tmp_path / "captures" / "scan_no_ref" / "deg_0"
    output_dir = tmp_path / "processed" / "scan_no_ref"
    calibration_path = tmp_path / "calibration.json"
    _write_synthetic_scan(input_dir)
    calibration_path.write_text(
        '{"geometry": {"d": 300.0, "l": 120.0, "p": 5.0}}',
        encoding="utf-8",
    )

    config = DecodeConfig(
        height_mode="triangulation",
        calibration_config=calibration_path,
    )
    with pytest.raises(ValueError, match="requires --reference-phase"):
        PcbFppDecoder(config).decode(input_dir, output_dir)


def test_fused_0_180_scan_fills_shadow_region(tmp_path):
    full_scan = tmp_path / "captures" / "scan_002" / "full"
    input_0 = tmp_path / "captures" / "scan_002" / "deg_0"
    input_180 = tmp_path / "captures" / "scan_002" / "deg_180"
    output_dir = tmp_path / "processed" / "scan_002"
    _write_synthetic_scan(full_scan)
    _write_synthetic_scan(input_0)
    _invalidate_columns(input_0, start_col=60)
    _copy_rotated_scan(full_scan, input_180)

    config = DecodeConfig(
        min_signal=20,
        saturation_threshold=250,
        dark_threshold=5,
        modulation_threshold=0.05,
        median_filter=0,
        fusion_mode="modulation-weighted",
    )
    result = PcbFppDecoder(config).decode_fused(input_0, input_180, output_dir)

    assert (output_dir / "height" / "height_fused.npy").exists()
    assert (output_dir / "views" / "deg_0" / "decode_report.json").exists()
    assert (output_dir / "views" / "deg_180" / "decode_report.json").exists()
    assert np.count_nonzero(result.source_map == 2) > 0
    assert result.report["fusion"]["coverage"]["fused_valid_ratio"] > (
        result.deg0.report["mask_coverage"]["combined_mask_ratio"]
    )
