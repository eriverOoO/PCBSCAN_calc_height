import json
from pathlib import Path

import numpy as np
from PIL import Image

from pcb_fpp_decoder.debug_tools import (
    generate_scan_debug,
    generate_single_image_pattern_debug,
)
from pcb_fpp_decoder.decoder import DecodeConfig


def _save(path: Path, array: np.ndarray) -> None:
    Image.fromarray(np.clip(array, 0, 255).astype(np.uint8)).save(path)


def _write_synthetic_scan(folder: Path, width: int = 48, height: int = 32) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _y, x = np.indices((height, width))
    stripe_period = 4
    k = (x // stripe_period).astype(np.uint16)
    phi = ((x % stripe_period) / float(stripe_period) * 2.0 * np.pi).astype(np.float32)
    _save(folder / "pattern_000.png", np.full((height, width), 240.0, dtype=np.float32))
    _save(folder / "pattern_001.png", np.full((height, width), 10.0, dtype=np.float32))

    gray = k ^ (k >> 1)
    for bit in range(8):
        bit_on = ((gray >> (7 - bit)) & 1).astype(bool)
        _save(folder / f"pattern_{2 + bit:03d}.png", np.where(bit_on, 220.0, 25.0))

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


def test_single_image_pattern_debug_writes_binary_pattern(tmp_path):
    height, width = 72, 96
    y, x = np.indices((height, width))
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    rgb[:, :, 0] = 80 + (x // 4).astype(np.uint8)
    rgb[:, :, 1] = 45 + (y // 3).astype(np.uint8)
    rgb[:, :, 2] = 70
    rgb[:, 12::16, 2] = 230
    rgb[:, 13::16, 2] = 220
    image_path = tmp_path / "capture.png"
    Image.fromarray(rgb, mode="RGB").save(image_path)

    output_dir = tmp_path / "debug_single"
    steps = generate_single_image_pattern_debug(image_path, output_dir)

    assert (output_dir / "debug_manifest.json").exists()
    assert any(step.title == "Binary UV pattern" for step in steps)
    assert (output_dir / "debug_steps" / "06_binary_uv_pattern.png").exists()
    manifest = json.loads((output_dir / "debug_manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata"]["mode"] == "single-image-pattern-extraction"
    assert manifest["metadata"]["valid_pattern_pixel_ratio"] > 0


def test_scan_debug_writes_height_step_manifest(tmp_path):
    input_dir = tmp_path / "capture" / "deg_0"
    output_dir = tmp_path / "processed" / "debug"
    _write_synthetic_scan(input_dir)

    steps = generate_scan_debug(
        input_dir,
        output_dir,
        DecodeConfig(
            min_signal=20,
            saturation_threshold=250,
            dark_threshold=5,
            modulation_threshold=0.05,
            median_filter=0,
            detrend=False,
        ),
    )

    titles = {step.title for step in steps}
    assert "Decode pipeline overview" in titles
    assert "Height map" in titles
    assert (output_dir / "debug_steps" / "single_15_height_map.png").exists()
    manifest = json.loads((output_dir / "debug_manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata"]["mode"] == "scan-sequence"
    assert manifest["metadata"]["mask_coverage"]["combined_mask_ratio"] > 0.9
