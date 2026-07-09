from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
COLOR_INPUT_MODES = (
    "smartphone_uv_blue",
    "blue",
    "green",
    "red",
    "luminance",
    "max_rgb",
)
_CHANNEL_INDEX = {"red": 0, "green": 1, "blue": 2}


@dataclass
class PatternSet:
    input_dir: Path
    images: dict[int, np.ndarray]
    files: dict[int, Path]
    shape: tuple[int, int]

    @property
    def height(self) -> int:
        return self.shape[0]

    @property
    def width(self) -> int:
        return self.shape[1]


def read_image_gray(
    path: Path,
    color_mode: str = "smartphone_uv_blue",
    crosstalk_matrix: Sequence[Sequence[float]] | None = None,
) -> np.ndarray:
    """Read an image as single-channel float32, preserving Windows unicode paths."""
    try:
        with Image.open(path) as img:
            if _effective_color_mode(color_mode) == "luminance" and crosstalk_matrix is None:
                arr = np.asarray(img.convert("L"), dtype=np.float32)
            else:
                arr = rgb_to_intensity(
                    np.asarray(img.convert("RGB")),
                    color_mode=color_mode,
                    crosstalk_matrix=crosstalk_matrix,
                )
        return arr
    except Exception:
        try:
            import cv2  # type: ignore

            raw = np.fromfile(str(path), dtype=np.uint8)
            read_flag = (
                cv2.IMREAD_GRAYSCALE
                if _effective_color_mode(color_mode) == "luminance"
                and crosstalk_matrix is None
                else cv2.IMREAD_UNCHANGED
            )
            img = cv2.imdecode(raw, read_flag)
            if img is None:
                raise ValueError(f"cv2 could not decode image: {path}")
            if img.ndim == 2:
                return img.astype(np.float32)
            if img.ndim == 3:
                channels = img.shape[2]
                if channels < 3:
                    raise ValueError(f"expected at least 3 color channels: {path}")
                rgb = img[:, :, :3][:, :, ::-1]
                return rgb_to_intensity(
                    rgb,
                    color_mode=color_mode,
                    crosstalk_matrix=crosstalk_matrix,
                )
            raise ValueError(f"unsupported image shape {img.shape}: {path}")
        except Exception as exc:
            raise ValueError(f"failed to read image {path}: {exc}") from exc


def rgb_to_intensity(
    image: np.ndarray,
    color_mode: str = "smartphone_uv_blue",
    crosstalk_matrix: Sequence[Sequence[float]] | None = None,
) -> np.ndarray:
    """Convert an RGB image to the intensity channel used by FPP decoding."""
    mode = _effective_color_mode(color_mode)
    arr = np.asarray(image)
    if arr.ndim == 2:
        return arr.astype(np.float32)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError("expected a grayscale or RGB-like image array")

    rgb = arr[:, :, :3].astype(np.float32)
    if crosstalk_matrix is not None:
        rgb = apply_crosstalk_decoupling(rgb, crosstalk_matrix)

    if mode in _CHANNEL_INDEX:
        return rgb[:, :, _CHANNEL_INDEX[mode]].astype(np.float32)
    if mode == "luminance":
        r = rgb[:, :, 0]
        g = rgb[:, :, 1]
        b = rgb[:, :, 2]
        return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)
    if mode == "max_rgb":
        return np.max(rgb, axis=2).astype(np.float32)
    raise ValueError(f"unsupported input color mode: {color_mode}")


def apply_crosstalk_decoupling(
    rgb: np.ndarray,
    crosstalk_matrix: Sequence[Sequence[float]],
) -> np.ndarray:
    """Apply inv(kappa) to RGB pixels where captured_rgb = kappa * true_rgb."""
    matrix = _as_crosstalk_matrix(crosstalk_matrix)
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError("color crosstalk matrix must be invertible") from exc

    flat = np.asarray(rgb, dtype=np.float32).reshape(-1, 3)
    corrected = flat @ inverse.T
    corrected = corrected.reshape(rgb.shape)
    return np.clip(corrected, 0.0, None).astype(np.float32)


def parse_crosstalk_matrix(text: str | None) -> tuple[tuple[float, float, float], ...] | None:
    if text is None or not str(text).strip():
        return None
    rows = [row.strip() for row in re.split(r"[;|]", str(text).strip()) if row.strip()]
    if len(rows) == 1:
        values = _parse_float_row(rows[0])
        if len(values) != 9:
            raise ValueError(
                "color crosstalk matrix must contain 9 values, or 3 rows separated by ';'"
            )
        rows_values = [values[0:3], values[3:6], values[6:9]]
    elif len(rows) == 3:
        rows_values = [_parse_float_row(row) for row in rows]
        if any(len(row) != 3 for row in rows_values):
            raise ValueError("each color crosstalk matrix row must contain 3 values")
    else:
        raise ValueError("color crosstalk matrix must have 3 rows")

    matrix = tuple(tuple(float(v) for v in row) for row in rows_values)
    _as_crosstalk_matrix(matrix)
    return matrix


def _effective_color_mode(color_mode: str) -> str:
    mode = str(color_mode).strip().lower()
    if mode == "smartphone_uv_blue":
        return "blue"
    if mode not in COLOR_INPUT_MODES:
        raise ValueError(
            "input color mode must be one of: " + ", ".join(COLOR_INPUT_MODES)
        )
    return mode


def _parse_float_row(text: str) -> list[float]:
    tokens = [token for token in re.split(r"[\s,]+", text.strip()) if token]
    try:
        return [float(token) for token in tokens]
    except ValueError as exc:
        raise ValueError("color crosstalk matrix values must be numeric") from exc


def _as_crosstalk_matrix(
    matrix: Sequence[Sequence[float]],
) -> np.ndarray:
    arr = np.asarray(matrix, dtype=np.float32)
    if arr.shape != (3, 3):
        raise ValueError("color crosstalk matrix must be 3x3")
    if not np.all(np.isfinite(arr)):
        raise ValueError("color crosstalk matrix must contain finite values")
    return arr


def save_uint8_image(path: Path, image: np.ndarray) -> None:
    """Save a uint8-compatible image through Pillow with unicode path support."""
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(image)
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(path)


def save_float01_png(path: Path, image: np.ndarray) -> None:
    save_uint8_image(path, np.clip(image, 0.0, 1.0) * 255.0)


def find_image_files(input_dir: Path) -> list[Path]:
    return sorted(
        p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def extract_pattern_id(filename: str) -> int | None:
    stem = Path(filename).stem
    patterns = [
        r"pattern[_-]?(\d{1,3})",
        r"^(\d{1,3})(?:[_\-.]|$)",
        r"(?:^|[_-])(\d{3})(?:[_-]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem, flags=re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if 0 <= value <= 999:
                return value
    return None


def _flatten_scan_log_entries(data: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if any(k in data for k in ("pattern_id", "patternId", "id", "index")) and any(
            k in data for k in ("file", "filename", "path", "image")
        ):
            entries.append(data)
        for value in data.values():
            entries.extend(_flatten_scan_log_entries(value))
    elif isinstance(data, list):
        for item in data:
            entries.extend(_flatten_scan_log_entries(item))
    return entries


def _entry_pattern_id(entry: dict[str, Any]) -> int | None:
    for key in ("pattern_id", "patternId", "pattern", "id", "index"):
        if key in entry:
            try:
                value = int(entry[key])
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 999:
                return value
    return None


def _entry_file(entry: dict[str, Any]) -> str | None:
    for key in ("file", "filename", "path", "image", "image_path"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def map_patterns_from_scan_log(input_dir: Path) -> dict[int, Path]:
    log_path = input_dir / "scan_log.json"
    if not log_path.exists():
        return {}

    with log_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    mapping: dict[int, Path] = {}
    for entry in _flatten_scan_log_entries(data):
        pattern_id = _entry_pattern_id(entry)
        file_value = _entry_file(entry)
        if pattern_id is None or file_value is None:
            continue

        candidate = Path(file_value)
        if not candidate.is_absolute():
            candidate = input_dir / candidate
        if candidate.exists() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
            mapping[pattern_id] = candidate
    return mapping


def map_patterns_by_filename(input_dir: Path) -> dict[int, Path]:
    mapping: dict[int, Path] = {}
    for image_path in find_image_files(input_dir):
        pattern_id = extract_pattern_id(image_path.name)
        if pattern_id is None:
            continue
        mapping.setdefault(pattern_id, image_path)
    return mapping


def load_pattern_set(
    input_dir: Path,
    expected_count: int = 14,
    required_ids: list[int] | range | None = None,
    optional_ids: list[int] | range | None = None,
    color_mode: str = "smartphone_uv_blue",
    crosstalk_matrix: Sequence[Sequence[float]] | None = None,
) -> PatternSet:
    input_dir = input_dir.expanduser().resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"input folder does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"input path is not a folder: {input_dir}")

    required = list(required_ids) if required_ids is not None else list(range(expected_count))
    optional = list(optional_ids) if optional_ids is not None else []
    load_ids = sorted(set(required + optional))

    fallback = map_patterns_by_filename(input_dir)
    mapping = dict(fallback)
    mapping.update(map_patterns_from_scan_log(input_dir))

    missing = [i for i in required if i not in mapping]
    if missing:
        available = sorted(mapping)
        raise FileNotFoundError(
            "missing required pattern image(s): "
            f"{missing}. Available pattern ids: {available}. "
            "Expected required ids from scan_log.json or filenames such as pattern_000.png."
        )

    images: dict[int, np.ndarray] = {}
    files: dict[int, Path] = {}
    shape: tuple[int, int] | None = None
    for pattern_id in load_ids:
        if pattern_id not in mapping:
            continue
        path = mapping[pattern_id]
        image = read_image_gray(
            path,
            color_mode=color_mode,
            crosstalk_matrix=crosstalk_matrix,
        )
        if image.ndim != 2:
            raise ValueError(f"pattern {pattern_id} did not load as grayscale: {path}")
        current_shape = image.shape
        if shape is None:
            shape = current_shape
        elif current_shape != shape:
            raise ValueError(
                f"image size mismatch for pattern {pattern_id}: {path} has "
                f"{current_shape}, expected {shape}"
            )
        images[pattern_id] = image.astype(np.float32, copy=False)
        files[pattern_id] = path

    assert shape is not None
    return PatternSet(input_dir=input_dir, images=images, files=files, shape=shape)
