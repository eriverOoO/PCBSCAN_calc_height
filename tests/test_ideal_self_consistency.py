from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder
from pcb_fpp_decoder.phase import compute_wrapped_phase_4step
from validation_harness.manifests import build_l0_manifest, inspect_pattern_sequence
from validation_harness.l0 import run_l0_validation


def _ideal_sequence(folder: Path, width: int = 40, height: int = 24) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _, x = np.indices((height, width))
    stripe = (x // 5).astype(np.uint16)
    gray = stripe ^ (stripe >> 1)
    phase = (x % 5) * (2.0 * np.pi / 5.0)
    frames: dict[int, np.ndarray] = {
        0: np.full((height, width), 240, dtype=np.uint8),
        1: np.full((height, width), 10, dtype=np.uint8),
    }
    for bit in range(8):
        frames[2 + bit] = np.where((gray >> (7 - bit)) & 1, 220, 25).astype(np.uint8)
        frames[14 + bit] = (255 - frames[2 + bit]).astype(np.uint8)
    frames.update(
        {
            10: np.clip(125 + 70 * np.sin(phase), 0, 255).astype(np.uint8),
            11: np.clip(125 - 70 * np.cos(phase), 0, 255).astype(np.uint8),
            12: np.clip(125 - 70 * np.sin(phase), 0, 255).astype(np.uint8),
            13: np.clip(125 + 70 * np.cos(phase), 0, 255).astype(np.uint8),
        }
    )
    for pattern_id, frame in frames.items():
        Image.fromarray(frame).save(folder / f"pattern_{pattern_id:03d}.png")


def test_l0_manifest_is_explicitly_not_real_world_accuracy(tmp_path: Path) -> None:
    pattern_root = tmp_path / "ideal"
    _ideal_sequence(pattern_root)
    manifest = build_l0_manifest(
        pattern_root, seed=17, generator_commit="fixture", generator_hash="fixture-hash"
    )

    assert manifest["validation_level"] == "L0"
    assert manifest["validation_kind"] == "ideal_self_consistency"
    assert manifest["real_world_accuracy_claim"] is False
    assert manifest["report_notice"] == "decoder-generator self consistency only"
    assert manifest["patterns"]["pattern_count"] == 22
    assert all(
        check["is_complement"]
        for check in manifest["patterns"]["gray_inverse_checks"].values()
    )


def test_l0_sine_order_phase_and_reference_algebra(tmp_path: Path) -> None:
    pattern_root = tmp_path / "ideal"
    output_root = tmp_path / "decoded"
    _ideal_sequence(pattern_root)
    inspection = inspect_pattern_sequence(pattern_root)
    frames = [np.asarray(Image.open(pattern_root / f"pattern_{index:03d}.png"), dtype=np.float32) for index in range(10, 14)]
    wrapped = compute_wrapped_phase_4step(*frames)
    result = PcbFppDecoder(DecodeConfig(output_profile="compact")).decode(pattern_root, output_root)

    assert inspection["sine_order"] == [10, 11, 12, 13]
    assert np.all(np.isfinite(wrapped))
    assert np.nanmax(np.abs(result.absolute.absolute_phase - result.absolute.absolute_phase)) == 0
    assert np.array_equal(result.height.mask, result.absolute.combined_mask)


def test_l0_report_leads_with_self_consistency_scope(tmp_path: Path) -> None:
    pattern_root = tmp_path / "ideal"
    output_root = tmp_path / "report"
    _ideal_sequence(pattern_root)
    report = run_l0_validation(
        pattern_root,
        output_root,
        seed=9,
        generator_commit="fixture",
    )
    assert report["report_notice"] == "decoder-generator self consistency only"
    assert report["real_world_accuracy_claim"] is False
    assert (output_root / "summary.json").exists()
    assert (output_root / "summary.csv").exists()
    assert (output_root / "failures.json").exists()


@pytest.mark.integration
def test_full_44_frame_ideal_dataset() -> None:
    root_value = os.environ.get("PCB_FPP_VALIDATION_ROOT")
    if not root_value:
        pytest.skip(
            "Set PCB_FPP_VALIDATION_ROOT to a dataset containing ideal/object_0 and ideal/object_180"
        )
    root = Path(root_value) / "ideal"
    object_0 = root / "object_0"
    object_180 = root / "object_180"
    if not object_0.is_dir() or not object_180.is_dir():
        pytest.skip(
            "Full L0 dataset missing; generate/copy exact 22-frame object_0 and object_180 under validation_data/ideal"
        )
    inspect_pattern_sequence(object_0)
    inspect_pattern_sequence(object_180)
    PcbFppDecoder(DecodeConfig(output_profile="compact")).decode(
        object_0, root / "_integration_result_0"
    )
    PcbFppDecoder(DecodeConfig(output_profile="compact")).decode(
        object_180, root / "_integration_result_180"
    )
