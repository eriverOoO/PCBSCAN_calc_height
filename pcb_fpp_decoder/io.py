from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


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


def read_image_gray(path: Path) -> np.ndarray:
    """Read an image as grayscale float32, preserving Windows unicode paths."""
    try:
        with Image.open(path) as img:
            arr = np.asarray(img.convert("L"), dtype=np.float32)
        return arr
    except Exception:
        try:
            import cv2  # type: ignore

            raw = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError(f"cv2 could not decode image: {path}")
            return img.astype(np.float32)
        except Exception as exc:
            raise ValueError(f"failed to read image {path}: {exc}") from exc


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
        image = read_image_gray(path)
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
