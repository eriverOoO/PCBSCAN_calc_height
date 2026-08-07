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


def test_reference_store_saves_all_four_cardinal_views(tmp_path: Path) -> None:
    phase = np.indices((40, 50))[1].astype(np.float32)
    report = validate_flat_stage(phase, np.ones_like(phase, dtype=bool))
    store = ReferenceStore(tmp_path / "reference_four")
    angles = (0, 90, 180, 270)

    store.save_multiview(
        {angle: phase + index for index, angle in enumerate(angles)},
        {angle: report for angle in angles},
        {angle: tmp_path / f"raw{angle}" for angle in angles},
    )

    assert store.is_four_view_available()
    assert np.allclose(np.load(store.phase_270_path), phase + 3)
    assert store.metadata()["view_angles_deg"] == [0, 90, 180, 270]


def test_reference_store_saves_gray_order_baselines_with_phase_reference(tmp_path: Path) -> None:
    phase = np.indices((40, 50))[1].astype(np.float32)
    report = validate_flat_stage(phase, np.ones_like(phase, dtype=bool))
    store = ReferenceStore(tmp_path / "reference_gray")
    gray_orders = {0: np.full(phase.shape, 20, dtype=np.int32), 180: np.full(phase.shape, 21, dtype=np.int32)}

    store.save_multiview(
        {0: phase, 180: phase + 2},
        {0: report, 180: report},
        {0: tmp_path / "raw0", 180: tmp_path / "raw180"},
        gray_orders,
    )

    assert store.is_gray_order_available()
    assert np.array_equal(np.load(store.gray_order_0_path), gray_orders[0])
    assert store.metadata()["gray_order_reference"] is True


def test_pair_metadata_does_not_reuse_stale_four_view_files(tmp_path: Path) -> None:
    phase = np.indices((40, 50))[1].astype(np.float32)
    report = validate_flat_stage(phase, np.ones_like(phase, dtype=bool))
    store = ReferenceStore(tmp_path / "reference_replace")
    angles = (0, 90, 180, 270)
    store.save_multiview(
        {angle: phase for angle in angles},
        {angle: report for angle in angles},
        {angle: tmp_path / f"raw{angle}" for angle in angles},
    )

    store.save(phase, phase, report, report, tmp_path / "new0", tmp_path / "new180")

    assert store.is_available()
    assert not store.is_four_view_available()
