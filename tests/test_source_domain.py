from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from validation_harness.source_domain import (
    build_empirical_gain_map,
    source_domain_from_profile,
)
from validation_harness.stress import StressSynthesizer


def test_empirical_gain_map_is_bounded_and_auditable(tmp_path: Path) -> None:
    yy, xx = np.indices((20, 30), dtype=np.float32)
    source = 20.0 + 3.0 * xx + 2.0 * yy
    path = tmp_path / "background.png"
    Image.fromarray(np.rint(source * 100).astype(np.uint16)).save(path)

    gain, metadata = build_empirical_gain_map(
        path, (12, 16), blur_sigma_fraction=0.2, gain_min=0.8, gain_max=1.2
    )

    assert gain.shape == (12, 16)
    assert float(gain.min()) >= 0.8
    assert float(gain.max()) <= 1.2 + 1e-6
    assert len(metadata["source_sha256"]) == 64
    assert metadata["role"].startswith("physical_background")
    assert "not a measurement of PSF" in metadata["identifiability_warning"]


def test_source_domain_disabled_has_no_effect() -> None:
    gain, metadata = source_domain_from_profile({}, (8, 10))
    assert gain is None
    assert metadata["enabled"] is False


def test_stress_synthesizer_applies_source_proxy_and_records_manifest(tmp_path: Path) -> None:
    source = np.linspace(1.0, 2.0, 24 * 32, dtype=np.float32).reshape(24, 32)
    path = tmp_path / "background.npy"
    np.save(path, source, allow_pickle=False)
    profile = {
        "source_domain": {
            "enabled": True,
            "background_path": str(path),
            "blur_sigma_fraction": 0.2,
            "gain_min": 0.8,
            "gain_max": 1.2,
        },
        "noise": {"quantization_bits": 16},
    }
    images = {index: np.full((12, 16), 32768, dtype=np.uint16) for index in range(22)}
    result = StressSynthesizer(profile, seed=17).synthesize(images, view_name="object_0")
    source_manifest = result.manifest["source_domain"]
    assert source_manifest["enabled"] is True
    assert len(source_manifest["source_sha256"]) == 64
    assert source_manifest["apply_to"].startswith("all_linear_radiance")
    assert np.ptp(result.images[10]) > 0
