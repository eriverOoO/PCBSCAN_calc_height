from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from validation_harness.manifests import (
    CALIBRATION_SEED_RANGE,
    HELD_OUT_SEED_RANGE,
    load_config,
    sha256_file,
)
from validation_harness.stress import StressSynthesizer, generate_stress_case
from validation_harness.runner import ValidationRunner
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def _frames(shape: tuple[int, int] = (18, 30)) -> dict[int, np.ndarray]:
    _, x = np.indices(shape)
    frames: dict[int, np.ndarray] = {}
    for pattern_id in range(22):
        if pattern_id == 0:
            array = np.full(shape, 240, dtype=np.uint8)
        elif pattern_id == 1:
            array = np.full(shape, 10, dtype=np.uint8)
        elif pattern_id < 10:
            array = np.where(((x // 3) >> (pattern_id - 2)) & 1, 220, 25).astype(np.uint8)
        elif pattern_id < 14:
            array = np.clip(125 + 70 * np.sin(x / 3 + pattern_id), 0, 255).astype(np.uint8)
        else:
            array = 255 - frames[pattern_id - 12]
        frames[pattern_id] = array
    return frames


def test_l1_is_byte_reproducible_and_records_all_masks() -> None:
    profile = load_config(ROOT / "configs" / "validation_l1_hard.yaml")
    first = StressSynthesizer(profile, 2000).synthesize(_frames(), view_name="object_0")
    second = StressSynthesizer(profile, 2000).synthesize(_frames(), view_name="object_0")

    assert first.manifest == second.manifest
    for pattern_id in range(22):
        assert first.images[pattern_id].dtype == np.uint16
        assert first.images[pattern_id].tobytes() == second.images[pattern_id].tobytes()
    assert set(first.masks) == {
        "hot_pixel",
        "bit_flip",
        "cycle_slip",
        "half_cycle_slip",
        "whole_cycle_slip",
        "saturation",
        "shadow",
        "gray_boundary",
        "registration_error",
    }
    assert first.manifest["approximation"]["registration_gray_and_cycle_slip"] == "image_domain"
    assert len(first.manifest["frame_gains"]) == 22


def test_profiles_are_monotonic_and_seed_partitions_do_not_overlap() -> None:
    names = ("clean", "normal", "hard", "extreme")
    profiles = [load_config(ROOT / "configs" / f"validation_l1_{name}.yaml") for name in names]
    gains = [profile["radiometric"]["pattern_gain_max_fraction"] for profile in profiles]
    assert gains == [0.0, 0.03, 0.07, 0.10]
    assert set(CALIBRATION_SEED_RANGE).isdisjoint(HELD_OUT_SEED_RANGE)
    assert all(len(profile["quick_seeds"]) == 2 for profile in profiles)
    assert all(len(profile["nightly_seeds"]) >= 10 for profile in profiles)


def test_cs126mu_profile_uses_only_published_sensor_bounds() -> None:
    profile = load_config(ROOT / "configs" / "validation_l1_cs126mu.yaml")
    sensor = profile["evidence"]["measured_or_bounded"]
    policy = profile["evidence"]["assumption_policy"]

    assert sensor["resolution_px"] == [4096, 3000]
    assert sensor["adc_bits"] == 12
    assert sensor["full_well_electrons_min"] == 10650.0
    assert sensor["read_noise_electrons_rms_max"] == 2.5
    assert profile["noise"]["quantization_bits"] == 12
    assert profile["noise"]["read_sigma"] == pytest.approx(2.5 / 10650.0)
    assert profile["optics"]["camera_psf_sigma_px"] == 0.0
    assert policy["gamma"].endswith("disabled")
    assert policy["psf"].endswith("disabled")
    assert policy["distortion"].endswith("disabled")


def test_cs126mu_adc_quantization_limits_output_to_4096_levels() -> None:
    profile = load_config(ROOT / "configs" / "validation_l1_cs126mu.yaml")
    result = StressSynthesizer(profile, 2020).synthesize(
        _frames((72, 96)), view_name="object_0"
    )

    assert all(image.dtype == np.uint16 for image in result.images.values())
    assert max(np.unique(image).size for image in result.images.values()) <= 4096
    assert result.manifest["impairments"]["noise"]["quantization_bits"] == 12


def test_same_cli_inputs_produce_identical_files(tmp_path: Path) -> None:
    ideal = tmp_path / "ideal"
    ideal.mkdir()
    for pattern_id, frame in _frames().items():
        Image.fromarray(frame).save(ideal / f"pattern_{pattern_id:03d}.png")
    first = generate_stress_case(
        input_root=ideal,
        output_root=tmp_path / "first",
        profile_path=ROOT / "configs" / "validation_l1_normal.yaml",
        seed=2000,
        partition="held_out",
    )
    second = generate_stress_case(
        input_root=ideal,
        output_root=tmp_path / "second",
        profile_path=ROOT / "configs" / "validation_l1_normal.yaml",
        seed=2000,
        partition="held_out",
    )
    first_files = {
        path.relative_to(first).as_posix(): sha256_file(path)
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second).as_posix(): sha256_file(path)
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_l1_clean_quick_case_decodes_without_gt_leakage(tmp_path: Path) -> None:
    ideal = tmp_path / "ideal"
    ideal.mkdir()
    for pattern_id, frame in _frames((24, 40)).items():
        Image.fromarray(frame).save(ideal / f"pattern_{pattern_id:03d}.png")
    case = generate_stress_case(
        input_root=ideal,
        output_root=tmp_path / "cases",
        profile_path=ROOT / "configs" / "validation_l1_clean.yaml",
        seed=2000,
        partition="held_out",
    )
    summary = ValidationRunner().run_case(case, tmp_path / "results")
    assert summary["validation_level"] == "L1"
    assert summary["real_world_accuracy_claim"] is False
    assert set(summary["views"]) == {"deg_0", "deg_180", "fused"}
    assert (tmp_path / "results" / "summary.json").exists()
    assert (tmp_path / "results" / "failures.json").exists()


@pytest.mark.slow
def test_each_profile_has_ten_reproducible_nightly_seeds() -> None:
    frames = _frames((12, 18))
    for name in ("clean", "normal", "hard", "extreme"):
        profile = load_config(ROOT / "configs" / f"validation_l1_{name}.yaml")
        hashes: list[int] = []
        for seed in profile["nightly_seeds"]:
            result = StressSynthesizer(profile, seed).synthesize(frames, view_name="object_0")
            hashes.append(hash(result.images[10].tobytes()))
        assert len(hashes) == 10
