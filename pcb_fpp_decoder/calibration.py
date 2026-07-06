from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

CalibrationValue = float | np.ndarray


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
