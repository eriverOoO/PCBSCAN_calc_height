from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from validation_harness.capture_evidence import (
    build_capture_evidence_report,
    capture_image_statistics,
    write_capture_evidence_report,
)
from validation_harness.manifests import load_config
from validation_harness.stress import StressSynthesizer


ROOT = Path(__file__).resolve().parents[1]


def _frames(shape: tuple[int, int] = (36, 54)) -> dict[int, np.ndarray]:
    _, xx = np.indices(shape)
    frames: dict[int, np.ndarray] = {}
    for pattern_id in range(22):
        if pattern_id == 0:
            frame = np.full(shape, 232, dtype=np.uint8)
        elif pattern_id == 1:
            frame = np.full(shape, 12, dtype=np.uint8)
        elif pattern_id < 10:
            frame = np.where(((xx // 3) >> (pattern_id - 2)) & 1, 220, 24).astype(
                np.uint8
            )
        elif pattern_id < 14:
            frame = np.clip(
                126 + 76 * np.sin(xx / 3.0 + pattern_id), 0, 255
            ).astype(np.uint8)
        else:
            frame = 255 - frames[pattern_id - 12]
        frames[pattern_id] = frame
    return frames


def test_capture_statistics_record_observable_8bit_occupancy(tmp_path: Path) -> None:
    image = np.zeros((30, 40), dtype=np.uint8)
    image[:, 20:] = 255
    path = tmp_path / "capture.tif"
    Image.fromarray(image).save(path)

    stats = capture_image_statistics(path)

    assert stats["encoding"]["code_bits"] == 8
    assert stats["shape"] == [30, 40]
    assert stats["fraction_at_sensor_max"] == 0.5
    assert stats["fraction_below_2pct"] == 0.5
    assert len(stats["sha256"]) == 64
    assert "not PSF" in stats["identifiability_warning"]


def test_unordered_capture_report_forbids_gt_and_calibration_inferences(
    tmp_path: Path,
) -> None:
    paths = []
    for index, value in enumerate((8, 180, 255), start=1):
        path = tmp_path / f"{index}.tif"
        Image.fromarray(np.full((24, 32), value, dtype=np.uint8)).save(path)
        paths.append(path)

    report = build_capture_evidence_report(paths)
    html_path, json_path, contact_sheet = write_capture_evidence_report(
        paths, tmp_path / "report"
    )

    assert report["frame_count"] == 3
    assert report["common_encoding"]["code_bits"] == 8
    assert report["real_world_accuracy_claim"] is False
    assert report["capture_order"]["declared_camera_sequence"] is False
    assert "phase or metric-height ground truth" in report["excluded_inferences"]
    assert html_path.exists() and json_path.exists() and contact_sheet.exists()


def test_ximea_observed_randomization_is_reproducible_and_auditable() -> None:
    profile = load_config(ROOT / "configs" / "validation_l1_ximea_observed.yaml")
    first = StressSynthesizer(profile, 2040).synthesize(
        _frames(), view_name="object_0"
    )
    second = StressSynthesizer(profile, 2040).synthesize(
        _frames(), view_name="object_0"
    )

    assert first.manifest == second.manifest
    assert first.images[10].tobytes() == second.images[10].tobytes()
    assert {"capture_projection_dark", "capture_shadow", "capture_glare"} <= set(
        first.masks
    )
    capture = first.manifest["capture_randomization"]
    assert capture["enabled"] is True
    assert capture["role"] == "held_out_image_domain_nuisance_randomization"
    assert "not fitted" in capture["identifiability_warning"]
    assert len(capture["sampled"]["frame_exposure_scales"]) == 22
    assert len(set(capture["sampled"]["frame_exposure_scales"].values())) == 1
    assert max(np.unique(image).size for image in first.images.values()) <= 256


def test_ximea_profile_is_hash_pinned_and_does_not_claim_read_noise() -> None:
    profile = load_config(ROOT / "configs" / "validation_l1_ximea_observed.yaml")

    assert profile["noise"]["quantization_bits"] == 8
    assert profile["noise"]["poisson_electrons"] == 0.0
    assert profile["noise"]["read_sigma"] == 0.0
    assert profile["registration"]["translation_px"] == [0.0, 0.0]
    assert profile["evidence"]["camera_metadata"]["sequence_length"] == 0
    assert len(profile["evidence"]["source_sha256"]) == 9
    assert all(
        len(value) == 64 for value in profile["evidence"]["source_sha256"].values()
    )
    assert "metric height" in profile["capture_randomization"]["not_identified"]
