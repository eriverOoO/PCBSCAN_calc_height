"""Discovery and validation for PRO4500's precomputed stage alignment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .io import map_patterns_by_filename


STAGE_PRECALIBRATION_FILENAME = "stage_precalibration.json"
_ANGLE_FOLDER_RE = re.compile(r"(?:angle|deg)_\d{1,3}$", re.IGNORECASE)


@dataclass(frozen=True)
class StagePrecalibration:
    path: Path
    scan_root: Path
    matrix: np.ndarray
    transform_kind: str
    marker_ids: tuple[int, ...]
    rmse_px: float | None
    actual_rotation_magnitude_deg: float | None
    metadata: dict[str, Any]

    def report(self) -> dict[str, Any]:
        return {
            "source": "precomputed_stage_precalibration",
            "path": str(self.path),
            "scan_root": str(self.scan_root),
            "transform_kind": self.transform_kind,
            "marker_ids": list(self.marker_ids),
            "rmse_px": self.rmse_px,
            "actual_rotation_magnitude_deg": self.actual_rotation_magnitude_deg,
            "direction": _direction_from_metadata(self.metadata),
        }


def scan_root_for_input(input_dir: Path) -> Path:
    """Return the capture root for a scan root or one of its angle folders."""
    path = Path(input_dir).expanduser().resolve()
    return path.parent if _ANGLE_FOLDER_RE.fullmatch(path.name) else path


def find_stage_precalibration(input_dir_0: Path, input_dir_180: Path) -> StagePrecalibration | None:
    """Find a precomputed 180° -> 0° transform shared by the two input views."""
    root_0 = scan_root_for_input(input_dir_0)
    root_180 = scan_root_for_input(input_dir_180)
    if root_0 != root_180:
        return None
    path = root_0 / STAGE_PRECALIBRATION_FILENAME
    return load_stage_precalibration(path, scan_root=root_0) if path.is_file() else None


def load_stage_precalibration(path: Path, *, scan_root: Path | None = None) -> StagePrecalibration:
    path = Path(path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("stage_precalibration.json must contain an object")

    kind = str(data.get("transform_kind", "")).lower()
    if kind not in {"homography", "affine"}:
        raise ValueError("stage_precalibration transform_kind must be homography or affine")
    matrix_value = data.get("matrix", data.get("homography", data.get("affine")))
    if matrix_value is None:
        raise ValueError("stage_precalibration requires matrix, homography, or affine")
    matrix = np.asarray(matrix_value, dtype=np.float32)
    expected_shape = (3, 3) if kind == "homography" else (2, 3)
    if matrix.shape != expected_shape or not np.all(np.isfinite(matrix)):
        raise ValueError(
            f"stage_precalibration {kind} matrix must be finite {expected_shape[0]}x{expected_shape[1]}"
        )
    direction = _direction_from_metadata(data)
    if direction is not None and _direction_is_180_to_0(direction) is False:
        raise ValueError(
            "stage_precalibration direction must map 180-degree pixels to 0-degree pixels: "
            f"{direction}"
        )

    aruco = data.get("aruco")
    marker_values = aruco.get("marker_ids", ()) if isinstance(aruco, dict) else ()
    try:
        marker_ids = tuple(int(value) for value in marker_values)
    except (TypeError, ValueError) as exc:
        raise ValueError("stage_precalibration aruco.marker_ids must be integer IDs") from exc

    return StagePrecalibration(
        path=path,
        scan_root=(scan_root or path.parent).expanduser().resolve(),
        matrix=matrix,
        transform_kind=kind,
        marker_ids=marker_ids,
        rmse_px=_optional_number(data, "rmse_px", "reprojection_rmse_px", "rmse"),
        actual_rotation_magnitude_deg=_optional_number(
            data, "actual_rotation_magnitude_deg", "rotation_magnitude_deg"
        ),
        metadata=data,
    )


def validate_phone_fusion_patterns(input_dir: Path) -> list[int]:
    """Return missing IDs from the 22-image PRO4500 final-input contract."""
    found = map_patterns_by_filename(Path(input_dir))
    return [pattern_id for pattern_id in range(22) if pattern_id not in found]


def validate_stage_precalibration_direction(precalibration: StagePrecalibration) -> str:
    direction = _direction_from_metadata(precalibration.metadata)
    if direction is None:
        return "metadata does not explicitly state 180° -> 0° direction"
    if _direction_is_180_to_0(direction) is False:
        return f"transform direction is not 180° -> 0°: {direction}"
    if _direction_is_180_to_0(direction) is None:
        return f"unrecognized transform direction metadata: {direction}"
    return ""


def _optional_number(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _direction_from_metadata(data: dict[str, Any]) -> str | None:
    for key in ("direction", "transform_direction", "mapping_direction", "source_to_target"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _direction_is_180_to_0(direction: str) -> bool | None:
    normalized = re.sub(r"\s+", "", direction.lower()).replace("degree", "")
    normalized = normalized.replace("°", "")
    if re.search(r"180(?:[_-]?to|[_=→>-])[_-]?0", normalized):
        return True
    if re.search(r"0(?:[_-]?to|[_=→>-])[_-]?180", normalized):
        return False
    return None
