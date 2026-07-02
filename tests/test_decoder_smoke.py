from pathlib import Path

import numpy as np
from PIL import Image

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder


def _save(path: Path, array: np.ndarray) -> None:
    Image.fromarray(np.clip(array, 0, 255).astype(np.uint8)).save(path)


def _write_synthetic_scan(folder: Path, width: int = 80, height: int = 48) -> None:
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
        image = np.where(mask, 220.0, 25.0)
        _save(folder / f"pattern_{2 + bit:03d}.png", image)

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
