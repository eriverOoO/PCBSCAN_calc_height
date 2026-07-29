from pathlib import Path

import numpy as np

from pcb_fpp_decoder.decoder import DecodeConfig, PcbFppDecoder
from pcb_fpp_decoder.reference_surface import (
    reference_phase_path,
    store_validated_reference_surface,
    validate_reference_surface,
)


def test_flat_reference_is_accepted_and_stored(tmp_path: Path) -> None:
    rows, cols = np.indices((30, 40), dtype=np.float32)
    phase = 0.03 * cols - 0.02 * rows
    mask = np.ones_like(phase, dtype=bool)
    validation = validate_reference_surface(phase, mask)

    assert validation.valid
    path = store_validated_reference_surface(
        tmp_path, phase, mask, validation, view_angle=0, source_scan=tmp_path / "capture"
    )
    assert path == reference_phase_path(tmp_path, 0)
    np.testing.assert_allclose(np.load(path), phase)
    assert path.with_name("validation.json").exists()


def test_nonflat_reference_does_not_pass() -> None:
    phase = np.zeros((20, 20), dtype=np.float32)
    phase[5:15, 5:15] = 2.0
    validation = validate_reference_surface(phase, np.ones_like(phase, dtype=bool))

    assert not validation.valid


def test_decoder_uses_validated_cache_when_no_explicit_reference(tmp_path: Path) -> None:
    phase = np.full((4, 5), 1.25, dtype=np.float32)
    validation = validate_reference_surface(phase, np.ones_like(phase, dtype=bool))
    store_validated_reference_surface(
        tmp_path, phase, np.ones_like(phase, dtype=bool), validation,
        view_angle=0, source_scan=tmp_path / "capture",
    )

    decoder = PcbFppDecoder(DecodeConfig(reference_surface_store=tmp_path))
    np.testing.assert_allclose(decoder._load_reference_phase_if_available(), phase)
