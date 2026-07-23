from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from validation_harness.evidence import (
    SCANNER_SIM_SAMPLES,
    analyze_synthetic_sequence,
    linear_image_statistics,
)


def test_linear_image_statistics_are_scale_aware_and_explicitly_non_calibrating() -> None:
    image = np.linspace(0.0, 2.0, 20 * 30, dtype=np.float32).reshape(20, 30)
    stats = linear_image_statistics(image)

    assert stats["shape"] == [20, 30]
    assert stats["finite_fraction"] == 1.0
    assert stats["fraction_above_linear_unity"] == 0.5
    assert stats["normalized_gradient_rms"] > 0.0
    assert "do not interpret as PSF" in stats["identifiability_warning"]


def test_synthetic_sequence_audit_requires_and_hashes_exact_22_frames(
    tmp_path: Path,
) -> None:
    source = tmp_path / "object_0"
    source.mkdir()
    for pattern_id in range(22):
        array = np.full((8, 12), pattern_id * 10, dtype=np.uint8)
        Image.fromarray(array).save(source / f"pattern_{pattern_id:03d}.png")

    report = analyze_synthetic_sequence(tmp_path)

    assert set(report["frames"]) == {"0", "1", "10", "11", "12", "13"}
    assert all(len(item["sha256"]) == 64 for item in report["frames"].values())


def test_scanner_sim_sample_catalog_is_checksum_pinned_by_fetcher() -> None:
    from tools.fetch_external_fpp import CATALOG

    variants = CATALOG["scanner_sim_physical"]["sample_variants"]
    assert {item["key"] for item in variants} == set(SCANNER_SIM_SAMPLES)
    assert all(item["checksum"].startswith("sha256:") for item in variants)
    assert all(len(item["checksum"].split(":", 1)[1]) == 64 for item in variants)
