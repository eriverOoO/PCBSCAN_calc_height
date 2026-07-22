from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

CalibrationValue = float | np.ndarray

MORENO_TAUBIN_RECOMMENDED_PATCH_SIZE_PX = 47
MORENO_TAUBIN_MIN_POSE_COUNT = 6
PCB_REPROJECTION_TARGET_MAX_PX = 0.35


@dataclass
class Calibration:
    path: Path | None = None
    data: dict[str, Any] = field(default_factory=dict)
    arrays: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def is_loaded(self) -> bool:
        return bool(self.data or self.arrays)

    def get_float(self, *names: str) -> float | None:
        for name in names:
            value = _deep_get(self.data, name)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        return None

    def get_value(self, *names: str) -> CalibrationValue | None:
        for name in names:
            value = _array_get(self.arrays, name)
            if value is not None:
                return value

        for name in names:
            value = _deep_get(self.data, name)
            if value is None:
                continue
            try:
                array = np.asarray(value, dtype=np.float32)
            except (TypeError, ValueError):
                continue
            if array.ndim == 0:
                return float(array)
            return array
        return None


def _deep_get(data: dict[str, Any], dotted_name: str) -> Any:
    current: Any = data
    for part in dotted_name.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _array_get(arrays: dict[str, np.ndarray], dotted_name: str) -> np.ndarray | None:
    candidates = (dotted_name, dotted_name.replace(".", "_"))
    for candidate in candidates:
        if candidate in arrays:
            return np.asarray(arrays[candidate], dtype=np.float32)
    return None


def load_calibration(path: Path | None) -> Calibration | None:
    if path is None:
        return None
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"calibration file does not exist: {path}")

    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            return Calibration(path=path, data=json.load(f))

    if path.suffix.lower() == ".npz":
        with np.load(path) as npz:
            arrays = {key: np.asarray(npz[key]) for key in npz.files}
        return Calibration(path=path, arrays=arrays)

    raise ValueError("calibration file must be .json or .npz")


def triangulation_height(
    delta_phi: np.ndarray,
    calibration: Calibration,
    sign: float = 1.0,
    epsilon: float = 1e-6,
) -> tuple[np.ndarray, dict[str, Any]]:
    d = calibration.get_value("d", "distance_d", "geometry.d", "geometry.distance_d")
    l = calibration.get_value("l", "baseline_l", "geometry.l", "geometry.baseline_l")
    p = calibration.get_value(
        "p", "pattern_period_p", "pattern_period", "geometry.p", "geometry.pattern_period_p"
    )
    if d is None or l is None or p is None:
        raise ValueError(
            "triangulation mode requires d, l, and p in calibration JSON or NPZ"
        )

    d = _as_broadcastable_parameter(d, delta_phi.shape, "d")
    l = _as_broadcastable_parameter(l, delta_phi.shape, "l")
    p = _as_broadcastable_parameter(p, delta_phi.shape, "p")
    numerator = delta_phi * p * d
    denominator = delta_phi * p + 2.0 * np.pi * l
    height = sign * numerator / np.where(np.abs(denominator) < epsilon, np.nan, denominator)
    return height.astype(np.float32), {
        "d": _parameter_summary(d),
        "l": _parameter_summary(l),
        "p": _parameter_summary(p),
    }


def inverse_linear_height(
    delta_phi: np.ndarray,
    calibration: Calibration,
    epsilon: float = 1e-6,
) -> np.ndarray:
    if calibration.arrays:
        try:
            u = calibration.arrays["u"]
            v = calibration.arrays["v"]
            w = calibration.arrays["w"]
        except KeyError as exc:
            raise ValueError("inverse-linear calibration .npz requires u, v, and w arrays") from exc
    else:
        u_val = calibration.get_float("u", "inverse_linear.u")
        v_val = calibration.get_float("v", "inverse_linear.v")
        w_val = calibration.get_float("w", "inverse_linear.w")
        if u_val is None or v_val is None or w_val is None:
            raise ValueError(
                "inverse-linear mode requires u, v, w scalars in JSON or arrays in .npz"
            )
        u, v, w = u_val, v_val, w_val

    safe_delta = np.where(np.abs(delta_phi) < epsilon, np.nan, delta_phi)
    inv_h = u + v / safe_delta + w / (safe_delta * safe_delta)
    height = 1.0 / np.where(np.abs(inv_h) < epsilon, np.nan, inv_h)
    return height.astype(np.float32)


def phase_linear_height(
    delta_phi: np.ndarray,
    calibration: Calibration,
    fallback_sign: float = 1.0,
) -> tuple[np.ndarray, dict[str, float]]:
    """Convert reference-subtracted absolute phase to millimeters."""
    phase_per_mm = calibration.get_float(
        "phase_linear.phase_per_mm", "phase_per_mm"
    )
    offset_phase = calibration.get_float(
        "phase_linear.offset_phase", "offset_phase"
    )
    height_sign = calibration.get_float(
        "phase_linear.height_sign", "height_sign"
    )
    if phase_per_mm is None or offset_phase is None:
        raise ValueError(
            "phase_linear mode requires phase_per_mm and offset_phase in calibration JSON"
        )
    if not np.isfinite(phase_per_mm) or phase_per_mm <= 0:
        raise ValueError("phase_per_mm must be a finite positive value")
    if height_sign is None:
        height_sign = float(fallback_sign)
    if not np.isfinite(height_sign) or height_sign == 0:
        raise ValueError("height_sign must be a finite non-zero value")
    signed_delta = float(height_sign) * np.asarray(delta_phi, dtype=np.float32)
    height = (signed_delta - float(offset_phase)) / float(phase_per_mm)
    return height.astype(np.float32), {
        "phase_per_mm": float(phase_per_mm),
        "offset_phase": float(offset_phase),
        "height_sign": float(height_sign),
    }


def structured_light_calibration_report(calibration: Calibration | None) -> dict[str, Any]:
    if calibration is None or not calibration.data:
        return {"available": False, "method": None}

    section = _first_dict(
        calibration.data,
        "structured_light_calibration",
        "moreno_taubin",
        "projector_calibration",
    )
    if section is None:
        return {"available": False, "method": None}

    method = str(section.get("method", "moreno_taubin_local_homography"))
    warnings: list[str] = []
    capture = _capture_report(section, warnings)
    local_homography = _local_homography_report(section, warnings)
    reprojection_error = _reprojection_error_report(section, warnings)

    return {
        "available": True,
        "method": method,
        "pipeline": [
            "data_acquisition",
            "camera_intrinsics",
            "gray_code_decoding",
            "corner_local_homography",
            "projector_corner_estimation",
            "projector_intrinsics",
            "stereo_extrinsics",
        ],
        "capture": capture,
        "local_homography": local_homography,
        "reprojection_error": reprojection_error,
        "pcb_reflection_tuning": section.get("pcb_reflection_tuning", {}),
        "warnings": warnings,
    }


def _as_broadcastable_parameter(
    value: CalibrationValue,
    target_shape: tuple[int, ...],
    name: str,
) -> CalibrationValue:
    array = np.asarray(value, dtype=np.float32)
    if array.ndim == 0:
        return float(array)
    try:
        np.broadcast_shapes(array.shape, target_shape)
    except ValueError as exc:
        raise ValueError(
            f"calibration parameter {name!r} shape {array.shape} cannot broadcast "
            f"to phase shape {target_shape}"
        ) from exc
    return array


def _parameter_summary(value: CalibrationValue) -> dict[str, Any]:
    array = np.asarray(value, dtype=np.float32)
    if array.ndim == 0:
        return {"kind": "scalar", "value": float(array)}
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return {"kind": "map", "shape": list(array.shape), "min": None, "max": None}
    return {
        "kind": "map",
        "shape": list(array.shape),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
    }


def _first_dict(data: dict[str, Any], *names: str) -> dict[str, Any] | None:
    for name in names:
        value = _deep_get(data, name)
        if isinstance(value, dict):
            return value
    return None


def _optional_float(data: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = _deep_get(data, name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _optional_bool(data: dict[str, Any], *names: str) -> bool | None:
    for name in names:
        value = _deep_get(data, name)
        if isinstance(value, bool):
            return value
    return None


def _capture_report(section: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    pose_count = _optional_float(section, "capture.pose_count", "pose_count")
    board_locked = _optional_bool(
        section,
        "capture.board_locked_during_sequence",
        "board_locked_during_sequence",
    )
    full_white_required = _optional_bool(
        section,
        "capture.full_white_required",
        "full_white_required",
    )
    gray_code_axes = _deep_get(section, "capture.gray_code_axes")

    pose_count_ok = None
    if pose_count is not None:
        pose_count_ok = pose_count >= MORENO_TAUBIN_MIN_POSE_COUNT
        if not pose_count_ok:
            warnings.append(
                "capture.pose_count is below the recommended minimum for stable calibration"
            )

    if board_locked is False:
        warnings.append("capture.board_locked_during_sequence should be true")
    if full_white_required is False:
        warnings.append("capture.full_white_required should be true")

    return {
        "pose_count": int(pose_count) if pose_count is not None else None,
        "minimum_pose_count": MORENO_TAUBIN_MIN_POSE_COUNT,
        "pose_count_ok": pose_count_ok,
        "board_locked_during_sequence": board_locked,
        "full_white_required": full_white_required,
        "gray_code_axes": gray_code_axes,
    }


def _local_homography_report(section: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    patch_size = _optional_float(
        section,
        "local_homography.patch_size_px",
        "local_homography.patch_size",
        "patch_size_px",
    )
    min_decoded_points = _optional_float(
        section,
        "local_homography.min_decoded_points",
        "min_decoded_points",
    )

    patch_size_ok = None
    if patch_size is not None:
        patch_size_ok = int(patch_size) == MORENO_TAUBIN_RECOMMENDED_PATCH_SIZE_PX
        if not patch_size_ok:
            warnings.append("local_homography.patch_size_px differs from the 47 px default")

    return {
        "patch_size_px": int(patch_size) if patch_size is not None else None,
        "recommended_patch_size_px": MORENO_TAUBIN_RECOMMENDED_PATCH_SIZE_PX,
        "patch_size_ok": patch_size_ok,
        "min_decoded_points": (
            int(min_decoded_points) if min_decoded_points is not None else None
        ),
    }


def _reprojection_error_report(section: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    error_section = _first_dict(section, "reprojection_error") or {}
    target = _optional_float(
        error_section,
        "target_max_px",
        "pcb_target_max_px",
        "max_px",
    )
    if target is None:
        target = PCB_REPROJECTION_TARGET_MAX_PX

    values = {
        "camera_rms_px": _optional_float(error_section, "camera_rms_px", "camera_px"),
        "projector_rms_px": _optional_float(
            error_section,
            "projector_rms_px",
            "projector_px",
        ),
        "stereo_rms_px": _optional_float(error_section, "stereo_rms_px", "stereo_px"),
    }
    measured = {key: value for key, value in values.items() if value is not None}
    passed = None
    if measured:
        passed = all(value <= target for value in measured.values())
        if not passed:
            warnings.append("one or more reprojection RMS values exceed target_max_px")

    return {
        **values,
        "target_max_px": target,
        "passed": passed,
    }
