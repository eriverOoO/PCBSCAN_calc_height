from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder
from validation_harness.ideal import (
    BOARD_PROFILE_METADATA,
    IdealDatasetConfig,
    generate_ideal_dataset,
)
from validation_harness.manifests import inspect_pattern_sequence, sha256_file


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_procedural_ideal_dataset_is_complete_and_reproducible(tmp_path: Path) -> None:
    config = IdealDatasetConfig(width=96, height=64, seed=23, projector_period_px=12.0)
    first = generate_ideal_dataset(tmp_path / "first", config)
    second = generate_ideal_dataset(tmp_path / "second", config)

    assert _file_hashes(first) == _file_hashes(second)
    for view in ("object_0", "object_180", "reference_0", "reference_180"):
        inspection = inspect_pattern_sequence(first / view)
        assert inspection["pattern_count"] == 22
        assert inspection["dtype"] in {"uint16", "int32"}
        assert all(
            check["is_complement"]
            for check in inspection["gray_inverse_checks"].values()
        )

    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["real_world_accuracy_claim"] is False
    assert manifest["capture_reference_policy"][
        "reference_photo_used_as_geometry_or_calibration"
    ] is False
    assert manifest["ground_truth_policy"].startswith("evaluation only")
    assert (first / "previews" / "object_0" / "pattern_010_preview.png").exists()
    assert (first / "previews" / "object_0" / "height_mm_preview.png").exists()


def test_generated_object_and_reference_decode_with_production_defaults(tmp_path: Path) -> None:
    dataset = generate_ideal_dataset(
        tmp_path / "dataset",
        IdealDatasetConfig(width=96, height=64, projector_period_px=12.0),
    )
    decoder = PcbFppDecoder(DecodeConfig(output_profile="compact"))
    reference = decoder.decode(dataset / "reference_0", tmp_path / "decoded_reference")
    object_result = decoder.decode(dataset / "object_0", tmp_path / "decoded_object")

    assert reference.report["mask_coverage"]["combined_mask_ratio"] > 0.99
    assert object_result.report["mask_coverage"]["combined_mask_ratio"] > 0.99
    assert int(object_result.gray.stripe_order_k.max()) > 1


def test_open_hardware_board_profiles_have_distinct_source_informed_geometry(
    tmp_path: Path,
) -> None:
    profiles = ("adafruit_bme280", "soldered_simple_light", "soldered_w5500")
    signatures: set[tuple[int, float, int]] = set()
    for profile in profiles:
        dataset = generate_ideal_dataset(
            tmp_path / profile,
            IdealDatasetConfig(
                width=128,
                height=96,
                board_profile=profile,
                projector_period_px=12.0,
                projector_radial_k1=-0.018,
                projector_optical_axis_offset_px=(2.0, -1.0),
            ),
        )
        manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
        object_mask = np.load(dataset / "gt" / "object_0" / "object_mask.npy")
        height_mm = np.load(dataset / "gt" / "object_0" / "height_mm.npy")
        material_id = np.load(dataset / "gt" / "object_0" / "material_id.npy")
        assert manifest["board_model"] == BOARD_PROFILE_METADATA[profile]
        assert manifest["scanner_model"]["ground_truth_is_decoder_input"] is False
        assert manifest["scanner_model"]["projector"]["radial_k1"] == -0.018
        assert np.count_nonzero(object_mask) > 100
        assert np.nanmax(height_mm) > 1.0
        signatures.add(
            (
                int(np.count_nonzero(object_mask)),
                float(np.nanmax(height_mm)),
                int(material_id.sum()),
            )
        )
    assert len(signatures) == len(profiles)
