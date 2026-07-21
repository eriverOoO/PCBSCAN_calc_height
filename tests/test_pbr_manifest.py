from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from validation_harness.pbr import (
    BlenderCyclesBackend,
    build_scene_manifest,
    prepare_exact_22_patterns,
)
from validation_harness.external import build_external_adapter_manifest


def _patterns(folder: Path) -> None:
    folder.mkdir(parents=True)
    for pattern_id in range(14):
        array = np.full((8, 12), pattern_id * 11, dtype=np.uint8)
        Image.fromarray(array).save(folder / f"pattern_{pattern_id:03d}.bmp")


def test_pbr_manifest_preserves_actual_14_plus_exact_8_inverse_mapping(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _patterns(source)
    pattern_manifest = prepare_exact_22_patterns(source, tmp_path / "assembled")
    manifest = build_scene_manifest(pattern_manifest=pattern_manifest, seed=3000)

    assert pattern_manifest["pattern_order"] == list(range(22))
    assert all(pattern_manifest["mapping"][str(index)]["origin"] == "actual_pattern" for index in range(14))
    assert all(pattern_manifest["mapping"][str(index)]["origin"] == "exact_gray_inverse" for index in range(14, 22))
    assert manifest["camera"]["resolution_px"] == [1936, 1216]
    assert manifest["camera"]["pixel_pitch_um"] == 5.86
    assert manifest["views"]["reference_0"]["pcb_present"] is False
    assert manifest["output"]["decoder_frames"] == "mono 16-bit PNG"
    assert manifest["backend_status"].startswith("scaffold_requires")


def test_external_sequences_cannot_masquerade_as_production_22_frames(tmp_path: Path) -> None:
    for dataset in ("pbrt_zenodo", "fpp_ml_bench"):
        manifest = build_external_adapter_manifest(dataset, tmp_path / dataset)
        assert manifest["sequence_adapter"] == "submodule_only"
        assert manifest["production_22_frame_compatible"] is False
        assert manifest["rename_as_production_22_frame_sequence"] is False


@pytest.mark.pbr
def test_blender_backend_is_explicitly_skipped_when_unavailable() -> None:
    backend = BlenderCyclesBackend()
    if not backend.available():
        pytest.skip(
            "Install Blender 4.x and set BLENDER_EXECUTABLE, or pass --blender to tools/render_pbr_cases.py"
        )
    assert backend.available()
