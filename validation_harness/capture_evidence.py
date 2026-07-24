from __future__ import annotations

"""Descriptive evidence extraction for unordered real camera captures.

The input frames do not need to follow the decoder's 22-frame protocol.  The
statistics in this module are deliberately limited to directly observable
image-domain properties.  They must not be interpreted as optical calibration
or metric ground truth.
"""

import html
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage

from .manifests import sha256_file, write_json


SUPPORTED_SUFFIXES = (".tif", ".tiff", ".png", ".bmp", ".jpg", ".jpeg")
QUANTILE_LEVELS = (0.1, 1.0, 5.0, 50.0, 95.0, 99.0, 99.9)


def _number(value: str | None) -> int | float | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _ximea_metadata(description: Any) -> dict[str, Any] | None:
    if not isinstance(description, str) or "<imageMetadata" not in description:
        return None
    try:
        root = ElementTree.fromstring(description)
    except ElementTree.ParseError:
        return {"parse_error": True}
    api_values: dict[str, str] = {}
    api_context = root.findtext("apiContextList") or ""
    for line in api_context.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            api_values[key.strip()] = value.strip()

    def text(name: str) -> int | float | str | None:
        return _number(root.findtext(name))

    return {
        "metadata_version": root.attrib.get("version"),
        "camera_model": root.findtext("cameraModel"),
        "camera_serial_number": root.findtext("cameraSerialNumber"),
        "black_level_dn": _number(api_values.get("xiApiImg:black_level")),
        "exposure": text("exposure"),
        "gain": text("gain"),
        "auto_exposure": text("autoExposure"),
        "gamma_y": text("gammaY"),
        "sharpness": text("sharpness"),
        "temperature_c": text("temp"),
        "acquisition_datetime": root.findtext("acqDateTime"),
        "sequence_index": text("sequenceIdx"),
        "sequence_length": text("sequenceLength"),
        "binning_horizontal": _number(
            api_values.get("xiApiPar:binning_horizontal")
        ),
        "binning_vertical": _number(api_values.get("xiApiPar:binning_vertical")),
        "decimation_horizontal": _number(
            api_values.get("xiApiPar:decimation_horizontal")
        ),
        "decimation_vertical": _number(
            api_values.get("xiApiPar:decimation_vertical")
        ),
    }


def _as_luminance(
    path: str | Path,
) -> tuple[np.ndarray, dict[str, Any], dict[str, Any] | None]:
    source = Path(path).expanduser().resolve()
    with Image.open(source) as image:
        mode = image.mode
        tags = getattr(image, "tag_v2", {})
        camera_metadata = _ximea_metadata(tags.get(270))
        compression = tags.get(259)
        array = np.asarray(image)
        if array.ndim == 3:
            rgb = array[..., :3].astype(np.float32)
            array = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        elif array.ndim != 2:
            raise ValueError(f"capture must be 2-D or RGB: {source} -> {array.shape}")
    original_dtype = str(array.dtype)
    if np.issubdtype(array.dtype, np.integer):
        code_max = float(np.iinfo(array.dtype).max)
        code_bits = int(np.iinfo(array.dtype).bits)
    else:
        finite = np.asarray(array)[np.isfinite(array)]
        if not finite.size:
            raise ValueError(f"capture contains no finite pixels: {source}")
        code_max = max(float(np.percentile(finite, 99.99)), 1.0)
        code_bits = None
    normalized = np.clip(np.asarray(array, dtype=np.float32) / code_max, 0.0, 1.0)
    return normalized, {
        "mode": mode,
        "dtype": original_dtype,
        "code_bits": code_bits,
        "code_max": code_max,
        "compression": int(compression) if compression is not None else None,
    }, camera_metadata


def capture_image_statistics(path: str | Path) -> dict[str, Any]:
    """Measure observable image-domain descriptors for one capture."""

    source = Path(path).expanduser().resolve()
    image, encoding, camera_metadata = _as_luminance(source)
    if not np.isfinite(image).all():
        raise ValueError(f"capture contains non-finite pixels: {source}")

    stride_y = max(1, image.shape[0] // 768)
    stride_x = max(1, image.shape[1] // 1024)
    reduced = image[::stride_y, ::stride_x]
    quantiles = np.percentile(reduced, QUANTILE_LEVELS)
    smooth_sigma = max(1.0, min(reduced.shape) * 0.035)
    low_frequency = ndimage.gaussian_filter(reduced, smooth_sigma, mode="reflect")
    residual = reduced - low_frequency
    dx = np.diff(reduced, axis=1)
    dy = np.diff(reduced, axis=0)
    gradient_rms = float(np.sqrt(0.5 * (np.mean(dx * dx) + np.mean(dy * dy))))
    low_q = np.percentile(low_frequency, [5.0, 50.0, 95.0])

    return {
        "file": source.name,
        "sha256": sha256_file(source),
        "shape": [int(value) for value in image.shape],
        "encoding": encoding,
        "camera_metadata": camera_metadata,
        "normalized_quantiles": {
            str(level): float(value)
            for level, value in zip(QUANTILE_LEVELS, quantiles, strict=True)
        },
        "fraction_below_2pct": float(np.mean(reduced <= 0.02)),
        "fraction_above_5pct": float(np.mean(reduced >= 0.05)),
        "fraction_above_98pct": float(np.mean(reduced >= 0.98)),
        "fraction_at_sensor_max": float(np.mean(reduced >= 1.0)),
        "normalized_gradient_rms": gradient_rms,
        "low_frequency_p05_p50_p95": [float(value) for value in low_q],
        "low_frequency_span_p95_minus_p05": float(low_q[2] - low_q[0]),
        "multiscale_residual_rms": float(np.sqrt(np.mean(residual * residual))),
        "identifiability_warning": (
            "scene/pattern/pose are uncontrolled; descriptors are not PSF, gamma, "
            "read-noise, distortion, radiometric-response, or height measurements"
        ),
    }


def _aggregate(frames: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = np.asarray([float(frame[key]) for frame in frames], dtype=np.float64)
    return {
        "minimum": float(np.min(values)),
        "median": float(np.median(values)),
        "maximum": float(np.max(values)),
    }


def build_capture_evidence_report(paths: Iterable[str | Path]) -> dict[str, Any]:
    sources = sorted(
        {Path(path).expanduser().resolve() for path in paths},
        key=lambda path: path.name.lower(),
    )
    if not sources:
        raise ValueError("at least one capture image is required")
    frames = [capture_image_statistics(path) for path in sources]
    shapes = {tuple(frame["shape"]) for frame in frames}
    encodings = {
        (frame["encoding"]["dtype"], frame["encoding"]["code_bits"]) for frame in frames
    }
    metadata = [
        frame["camera_metadata"]
        for frame in frames
        if isinstance(frame.get("camera_metadata"), dict)
    ]
    chronological_files = [
        frame["file"]
        for frame in sorted(
            frames,
            key=lambda frame: str(
                (frame.get("camera_metadata") or {}).get(
                    "acquisition_datetime", ""
                )
            ),
        )
    ]
    declared_sequence = bool(metadata) and all(
        int(item.get("sequence_length") or 0) > 0
        and int(item.get("sequence_index") or -1) >= 0
        for item in metadata
    )
    return {
        "schema_version": 1,
        "evidence_class": "unordered_unregistered_real_camera_capture",
        "camera_label": "XIMEA (user-provided capture set)",
        "frame_count": len(frames),
        "common_shape": list(next(iter(shapes))) if len(shapes) == 1 else None,
        "common_encoding": (
            {"dtype": next(iter(encodings))[0], "code_bits": next(iter(encodings))[1]}
            if len(encodings) == 1
            else None
        ),
        "frames": frames,
        "capture_order": {
            "chronological_files": chronological_files,
            "declared_camera_sequence": declared_sequence,
            "warning": (
                "file numbering is not assumed to be pattern order; XIMEA "
                "sequence metadata does not declare a valid sequence"
            ),
        },
        "aggregate": {
            key: _aggregate(frames, key)
            for key in (
                "fraction_below_2pct",
                "fraction_above_5pct",
                "fraction_above_98pct",
                "fraction_at_sensor_max",
                "normalized_gradient_rms",
                "low_frequency_span_p95_minus_p05",
                "multiscale_residual_rms",
            )
        },
        "safe_transfer_scope": [
            "output bit depth",
            "black-floor and saturation occupancy envelope",
            "illumination-footprint occupancy",
            "low-frequency spatial nonuniformity",
            "multiscale scene texture and localized highlight/shadow stress",
        ],
        "excluded_inferences": [
            "pattern identity or order",
            "phase or metric-height ground truth",
            "camera/projector geometry or final rig pose",
            "PSF from uncontrolled scene edges",
            "gamma or camera response without calibrated exposures",
            "read/shot noise without repeated dark and flat frames",
        ],
        "evaluation_policy": (
            "use only to define an evaluation-only held-out nuisance envelope; "
            "never tune decoder thresholds or claim real-rig accuracy"
        ),
        "real_world_accuracy_claim": False,
    }


def _write_contact_sheet(paths: list[Path], output_path: Path) -> None:
    columns = 3
    thumb_size = (484, 304)
    label_height = 26
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("L", (columns * thumb_size[0], rows * (thumb_size[1] + label_height)), 0)
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        with Image.open(path) as image:
            shown = ImageOps.autocontrast(image.convert("L"), cutoff=(0.5, 0.5))
            shown.thumbnail(thumb_size, Image.Resampling.LANCZOS)
        x = (index % columns) * thumb_size[0]
        y = (index // columns) * (thumb_size[1] + label_height)
        sheet.paste(
            shown,
            (x + (thumb_size[0] - shown.width) // 2, y + label_height),
        )
        draw.text((x + 8, y + 7), f"{path.name} (display autocontrast)", fill=255)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, optimize=True)


def write_capture_evidence_report(
    paths: Iterable[str | Path], output_root: str | Path
) -> tuple[Path, Path, Path]:
    sources = sorted(
        {Path(path).expanduser().resolve() for path in paths},
        key=lambda path: path.name.lower(),
    )
    report = build_capture_evidence_report(sources)
    output = Path(output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = write_json(output / "capture_characteristics.json", report)
    contact_sheet = output / "contact_sheet_autocontrast.png"
    _write_contact_sheet(sources, contact_sheet)

    rows = []
    for frame in report["frames"]:
        q = frame["normalized_quantiles"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(frame['file'])}</td>"
            f"<td>{q['1.0']:.4f}</td><td>{q['50.0']:.4f}</td><td>{q['99.0']:.4f}</td>"
            f"<td>{frame['fraction_below_2pct'] * 100:.1f}%</td>"
            f"<td>{frame['fraction_at_sensor_max'] * 100:.1f}%</td>"
            f"<td>{frame['normalized_gradient_rms']:.4f}</td>"
            "</tr>"
        )
    excluded = "".join(
        f"<li>{html.escape(item)}</li>" for item in report["excluded_inferences"]
    )
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>XIMEA capture evidence</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1180px;margin:32px auto;padding:0 20px;color:#17202a}}img{{max-width:100%;background:#111}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd1d1;padding:8px;text-align:right}}th:first-child,td:first-child{{text-align:left}}th{{background:#eef2f3}}.warn{{background:#fff4d6;padding:14px;border-left:5px solid #d68910}}</style></head>
<body><h1>XIMEA 실사 특성 감사</h1>
<p class="warn"><strong>정확도 ground truth가 아닙니다.</strong> 패턴 순서, 카메라 자세, 초점과 실제 높이가 통제되지 않았으므로 관측 가능한 영상 특성만 held-out stress 분포에 사용합니다.</p>
<p><img src="{contact_sheet.name}" alt="9장 XIMEA 캡처 자동 대비 contact sheet"></p>
<table><thead><tr><th>파일</th><th>P1</th><th>P50</th><th>P99</th><th>2% 이하</th><th>sensor max</th><th>gradient RMS</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>이 자료로 추정하지 않은 항목</h2><ul>{excluded}</ul>
<p><a href="{json_path.name}">전체 통계·SHA-256 JSON</a></p></body></html>"""
    html_path = output / "capture_characteristics.html"
    html_path.write_text(page, encoding="utf-8")
    return html_path, json_path, contact_sheet
