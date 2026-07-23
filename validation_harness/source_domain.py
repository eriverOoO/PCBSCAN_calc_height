from __future__ import annotations

"""Measured image-domain evidence adapters.

This module deliberately keeps a hard boundary between measured image-domain
evidence and optical calibration.  A scanner-sim background frame can be used
as a low-frequency illumination/vignetting *proxy* when generating a stress
case, but it cannot identify a camera PSF, gamma curve, read noise, or lens
distortion on its own.
"""

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image
from scipy import ndimage

from .manifests import sha256_file


def read_luminance(path: str | Path) -> np.ndarray:
    """Read a 2-D luminance/radiance array from a supported external file."""

    source = Path(path).expanduser().resolve()
    suffix = source.suffix.lower()
    if suffix == ".exr":
        try:
            import OpenEXR  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError(
                "OpenEXR is required for scanner-sim calibration/background data"
            ) from exc
        channels = OpenEXR.File(str(source)).channels()
        if "RGB" in channels:
            rgb = np.asarray(channels["RGB"].pixels, dtype=np.float32)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                raise ValueError(f"unexpected RGB EXR shape: {rgb.shape}")
            return (
                0.2126 * rgb[..., 0]
                + 0.7152 * rgb[..., 1]
                + 0.0722 * rgb[..., 2]
            ).astype(np.float32)
        for name in ("Y", "R", "G", "B"):
            if name in channels:
                return np.asarray(channels[name].pixels, dtype=np.float32)
        raise ValueError(f"EXR has no supported luminance/RGB channels: {source}")
    if suffix == ".npy":
        array = np.load(source, allow_pickle=False)
    elif suffix == ".npz":
        with np.load(source, allow_pickle=False) as archive:
            candidates = [name for name in archive.files if name in {"gain", "vignette", "image", "Y"}]
            key = candidates[0] if candidates else (archive.files[0] if archive.files else None)
            if key is None:
                raise ValueError(f"NPZ has no arrays: {source}")
            array = archive[key]
    else:
        with Image.open(source) as image:
            array = np.asarray(image.convert("F"))
    result = np.asarray(array, dtype=np.float32)
    if result.ndim != 2:
        raise ValueError(f"source image must be 2-D luminance: {source} -> {result.shape}")
    if not np.isfinite(result).any():
        raise ValueError(f"source image has no finite values: {source}")
    return result


def _resize(array: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if tuple(array.shape) == tuple(shape):
        return array.astype(np.float32, copy=True)
    zoom = (shape[0] / array.shape[0], shape[1] / array.shape[1])
    return ndimage.zoom(array, zoom, order=1, mode="nearest", prefilter=False).astype(np.float32)


def build_empirical_gain_map(
    source_path: str | Path,
    shape: tuple[int, int],
    *,
    blur_sigma_fraction: float = 0.08,
    gain_min: float = 0.75,
    gain_max: float = 1.25,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Create a bounded low-frequency gain map from a measured background.

    The broad blur intentionally removes setup/object edges from the physical
    background.  The map is a reproducible domain-randomization input, not a
    fitted optical parameter.  The manifest records the source hash and all
    normalization choices so the resulting case is auditable.
    """

    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"source-domain image not found: {source}")
    if not 0.0 < gain_min <= 1.0 <= gain_max:
        raise ValueError("source-domain gain bounds must satisfy gain_min <= 1 <= gain_max")
    if blur_sigma_fraction <= 0:
        raise ValueError("blur_sigma_fraction must be positive")
    image = read_luminance(source)
    finite = image[np.isfinite(image)]
    positive = finite[finite > 0]
    if positive.size == 0:
        raise ValueError(f"source-domain image has no positive samples: {source}")
    # Remove absolute exposure and use only the broad spatial field.
    baseline = float(np.percentile(positive, 50.0))
    normalized = np.nan_to_num(image / max(baseline, 1e-12), nan=1.0, posinf=1.0, neginf=1.0)
    resized = _resize(normalized, shape)
    sigma = max(1.0, min(shape) * float(blur_sigma_fraction))
    smooth = ndimage.gaussian_filter(resized, sigma=sigma, mode="nearest")
    center = float(np.median(smooth[np.isfinite(smooth)]))
    gain = np.clip(smooth / max(center, 1e-12), gain_min, gain_max).astype(np.float32)
    quantiles = np.percentile(gain, [1.0, 5.0, 50.0, 95.0, 99.0])
    metadata = {
        "enabled": True,
        "source_file": str(source),
        "source_sha256": sha256_file(source),
        "source_shape": [int(value) for value in image.shape],
        "target_shape": [int(value) for value in shape],
        "blur_sigma_fraction": float(blur_sigma_fraction),
        "blur_sigma_px_after_resize": float(sigma),
        "gain_bounds": [float(gain_min), float(gain_max)],
        "gain_quantiles": {
            str(level): float(value)
            for level, value in zip((1, 5, 50, 95, 99), quantiles, strict=True)
        },
        "role": "physical_background_low_frequency_illumination_proxy",
        "identifiability_warning": (
            "proxy applied in image domain; not a measurement of PSF, gamma, "
            "read noise, saturation, or geometric distortion"
        ),
    }
    return gain, metadata


def source_domain_from_profile(
    profile: Mapping[str, Any], shape: tuple[int, int]
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Resolve an optional measured source-domain map from a stress profile."""

    section = profile.get("source_domain", {})
    if not isinstance(section, Mapping) or not bool(section.get("enabled", False)):
        return None, {"enabled": False, "role": "disabled"}
    path = section.get("background_path") or section.get("gain_map_path")
    if not path:
        raise ValueError("source_domain.enabled requires background_path or gain_map_path")
    gain, metadata = build_empirical_gain_map(
        path,
        shape,
        blur_sigma_fraction=float(section.get("blur_sigma_fraction", 0.08)),
        gain_min=float(section.get("gain_min", 0.75)),
        gain_max=float(section.get("gain_max", 1.25)),
    )
    metadata["configured_source"] = str(path)
    metadata["apply_to"] = "all_linear_radiance_frames_before_sensor_noise"
    return gain, metadata


def write_source_domain_metadata(path: str | Path, metadata: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(metadata), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
