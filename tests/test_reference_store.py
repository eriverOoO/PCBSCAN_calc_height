from pathlib import Path

import numpy as np

from pcb_fpp_decoder.reference_store import ReferenceStore, validate_flat_stage


def test_flat_stage_validation_accepts_linear_phase_plane() -> None:
    y, x = np.indices((80, 100))
    phase = 3.0 * x - 0.2 * y + 7.0
    report = validate_flat_stage(phase, np.ones_like(phase, dtype=bool))
    assert report.valid


def test_flat_stage_validation_accepts_projective_phase_of_a_flat_stage() -> None:
    y, x = np.indices((120, 160))
    phase = (2.8 * x - 0.35 * y + 40.0) / (1.0 + 0.0008 * x - 0.0005 * y)
    report = validate_flat_stage(phase, np.ones_like(phase, dtype=bool))
    assert report.valid


def test_flat_stage_validation_rejects_object_on_stage() -> None:
    y, x = np.indices((100, 120))
    phase = 2.0 * x + 0.1 * y
    phase[30:70, 40:80] += 100.0
    report = validate_flat_stage(phase, np.ones_like(phase, dtype=bool))
    assert not report.valid
    assert "not sufficiently planar" in report.reason


def test_reference_store_replaces_active_reference_pair(tmp_path: Path) -> None:
    phase = np.indices((40, 50))[1].astype(np.float32)
    report = validate_flat_stage(phase, np.ones_like(phase, dtype=bool))
    store = ReferenceStore(tmp_path / "reference")
    store.save(phase, phase + 2, report, report, tmp_path / "raw0", tmp_path / "raw180")
    assert store.is_available()
    assert np.allclose(np.load(store.phase_0_path), phase)
    assert np.allclose(np.load(store.phase_180_path), phase + 2)
