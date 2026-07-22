from __future__ import annotations

import atexit
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw

from .decoder import DecodeConfig, DecodeResult, FusionResult, PcbFppDecoder
from .fusion_registration import estimate_and_save_fusion_transform
from .io import COLOR_INPUT_MODES, rgb_to_intensity, save_float01_png, save_uint8_image
from .visualization import (
    normalize_for_preview,
    save_colormap,
    save_mask,
    save_preview_gray,
    save_wrapped_phase_preview,
)


_SESSION_PREVIEW_DIRS: list[Path] = []


@dataclass(frozen=True)
class DebugStep:
    title: str
    path: Path
    group: str
    note: str = ""


@dataclass(frozen=True)
class FusionDebugSettings:
    registration: str = "aruco"
    aruco_ids: tuple[int, ...] = (0, 1, 2, 3)
    aruco_dictionary: str = "DICT_4X4_50"
    aruco_method: str = "homography"
    registration_image: str = "pattern_000.png"


def generate_single_image_pattern_debug(
    image_path: Path,
    output_dir: Path,
    *,
    color_mode: str = "smartphone_uv_blue",
    background_sigma: float = 25.0,
    min_component_area: int | None = None,
) -> list[DebugStep]:
    image_path = Path(image_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    _prepare_compact_debug_output(output_dir)

    if color_mode not in COLOR_INPUT_MODES:
        raise ValueError("input color mode must be one of: " + ", ".join(COLOR_INPUT_MODES))
    if not image_path.exists():
        raise FileNotFoundError(f"image file does not exist: {image_path}")

    with Image.open(image_path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)

    intensity = rgb_to_intensity(rgb, color_mode=color_mode)
    background = _gaussian_blur(intensity, sigma=max(float(background_sigma), 0.0))
    pattern_signal = np.clip(intensity - background, 0.0, None).astype(np.float32)
    normalized = normalize_for_preview(pattern_signal, low=0.5, high=99.5)
    threshold = _otsu_threshold(normalized)
    mask = normalized >= threshold
    min_area = min_component_area
    if min_area is None:
        min_area = max(16, int(mask.size * 0.00002))
    mask = _remove_small_components(mask, min_area=min_area)
    overlay = _overlay_mask(rgb, mask)

    overview_path = output_dir / "debug_overview.png"
    final_path = output_dir / "final_result.png"
    preview_dir = _make_session_preview_dir()
    original_step = preview_dir / "single_01_original.png"
    intensity_step = preview_dir / "single_02_uv_channel.png"
    signal_step = preview_dir / "single_03_background_removed.png"
    mask_step = preview_dir / "single_04_binary_pattern.png"
    overlay_step = preview_dir / "single_05_final_overlay.png"
    save_uint8_image(original_step, rgb)
    save_preview_gray(intensity_step, intensity)
    save_preview_gray(signal_step, pattern_signal)
    save_mask(mask_step, mask)
    save_uint8_image(overlay_step, overlay)
    _save_contact_sheet(
        overview_path,
        [
            ("Original", original_step),
            ("UV channel", intensity_step),
            ("Background removed", signal_step),
            ("Binary pattern", mask_step),
            ("Final overlay", overlay_step),
        ],
    )
    save_uint8_image(final_path, overlay)
    steps = [
        DebugStep("Debug overview", overview_path, "overview"),
        DebugStep("Original capture", original_step, "input"),
        DebugStep("UV intensity channel", intensity_step, "input"),
        DebugStep("Background removed signal", signal_step, "pattern-extraction"),
        DebugStep("Binary pattern mask", mask_step, "pattern-extraction"),
        DebugStep("Pattern overlay preview", overlay_step, "final"),
        DebugStep("Final pattern overlay", final_path, "final", f"threshold={threshold:.4f}"),
    ]

    return steps


def generate_scan_debug(
    input_dir: Path,
    output_dir: Path,
    config: DecodeConfig,
    *,
    input_180_dir: Path | None = None,
    fusion_settings: FusionDebugSettings | None = None,
) -> list[DebugStep]:
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    _prepare_compact_debug_output(output_dir)

    config = _copy_config(config)
    fusion_settings = fusion_settings or FusionDebugSettings()
    estimated_transform_summary: str | None = None

    temp_dir = _make_session_preview_dir()
    if input_180_dir is None:
        result = PcbFppDecoder(config)._decode_in_memory(input_dir)
        preview_steps = _save_result_debug_steps(result, temp_dir, "single")
        overview_source = temp_dir / "single_00_pipeline_overview.png"
        final_source = temp_dir / "single_15_height_map.png"
    else:
        input_180_dir = Path(input_180_dir).expanduser().resolve()
        if fusion_settings.registration != "rotation-180":
            if config.fusion_transform is not None:
                raise ValueError(
                    "Fusion transform file cannot be combined with automatic fusion registration."
                )
            estimated_transform = estimate_and_save_fusion_transform(
                fusion_settings.registration,
                input_dir,
                input_180_dir,
                temp_dir,
                aruco_dictionary=fusion_settings.aruco_dictionary,
                aruco_ids=fusion_settings.aruco_ids,
                aruco_image=fusion_settings.registration_image,
                aruco_method=fusion_settings.aruco_method,
                phase_correlation_image=fusion_settings.registration_image,
            )
            if estimated_transform is not None:
                config.fusion_transform = estimated_transform.path
                estimated_transform_summary = estimated_transform.summary

        decoder = PcbFppDecoder(config)
        fusion = decoder.fuse_decode_results(
            decoder._decode_in_memory(input_dir),
            decoder._decode_in_memory(input_180_dir),
        )
        preview_steps = _save_fusion_debug_steps(fusion, temp_dir)
        overview_source = temp_dir / "fusion_00_overview.png"
        final_source = temp_dir / "fusion_05_fused_height_map.png"

    overview_path = output_dir / "debug_overview.png"
    final_path = output_dir / "final_result.png"
    shutil.copy2(overview_source, overview_path)
    shutil.copy2(final_source, final_path)

    steps = [
        DebugStep("Debug overview", overview_path, "overview"),
        *[
            step
            for step in preview_steps
            if step.path != overview_source
        ],
        DebugStep("Final result", final_path, "final"),
    ]
    return steps


def _make_session_preview_dir() -> Path:
    path = Path(tempfile.mkdtemp(prefix="pcb_fpp_debug_preview_"))
    _SESSION_PREVIEW_DIRS.append(path)
    return path


def _cleanup_session_preview_dirs() -> None:
    for path in list(_SESSION_PREVIEW_DIRS):
        shutil.rmtree(path, ignore_errors=True)
    _SESSION_PREVIEW_DIRS.clear()


atexit.register(_cleanup_session_preview_dirs)


def load_debug_manifest(output_dir: Path) -> list[DebugStep]:
    output_dir = Path(output_dir)
    manifest_path = output_dir / "analysis_report.json"
    if not manifest_path.exists():
        manifest_path = output_dir / "debug_manifest.json"
    if not manifest_path.exists():
        steps = []
        for title, group, filename in (
            ("Debug overview", "overview", "debug_overview.png"),
            ("Final result", "final", "final_result.png"),
        ):
            path = output_dir / filename
            if path.exists():
                steps.append(DebugStep(title=title, path=path, group=group))
        return steps
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    steps = []
    for title, group, key in (
        ("Debug overview", "overview", "debug_overview"),
        ("Final result", "final", "final_result"),
    ):
        item_path = data.get("artifacts", {}).get(key)
        if item_path:
            steps.append(DebugStep(title=title, path=Path(item_path), group=group))
    if steps:
        return steps
    for item in data.get("steps", []):
        steps.append(
            DebugStep(
                title=str(item.get("title", "")),
                path=Path(item.get("path", "")),
                group=str(item.get("group", "")),
                note=str(item.get("note", "")),
            )
        )
    return steps


def _save_result_debug_steps(
    result: DecodeResult,
    debug_dir: Path,
    prefix: str,
) -> list[DebugStep]:
    debug_dir.mkdir(parents=True, exist_ok=True)
    steps: list[DebugStep] = []

    def add(title: str, filename: str, group: str, note: str = "") -> Path:
        path = debug_dir / f"{prefix}_{filename}"
        steps.append(DebugStep(title, path, group, note))
        return path

    raw_white = add("Raw white frame", "01_raw_white.png", "input")
    save_preview_gray(raw_white, result.patterns.images[0])
    raw_black = add("Raw black frame", "02_raw_black.png", "input")
    save_preview_gray(raw_black, result.patterns.images[1])

    signal = add("White minus black signal", "03_white_black_signal.png", "pattern-extraction")
    save_preview_gray(signal, result.correction.signal)
    threshold = add("Dynamic threshold", "04_dynamic_threshold.png", "pattern-extraction")
    save_preview_gray(threshold, result.correction.threshold)
    valid_mask = add("Valid capture mask", "05_valid_capture_mask.png", "pattern-extraction")
    save_mask(valid_mask, result.correction.valid_mask)

    corrected_gray = add("Corrected Gray frame", "06_corrected_gray0.png", "pattern-extraction")
    save_float01_png(corrected_gray, result.correction.corrected[2])
    corrected_sine = add("Corrected sine frame", "07_corrected_sine000.png", "pattern-extraction")
    save_float01_png(corrected_sine, result.correction.corrected[10])

    modulation = add("Sine modulation", "08_sine_modulation.png", "phase")
    save_preview_gray(modulation, result.phase.modulation, result.correction.valid_mask)
    modulation_mask = add("Modulation mask", "09_modulation_mask.png", "phase")
    save_mask(modulation_mask, result.phase.modulation_mask)

    gray_confidence = add("Gray confidence", "10_gray_confidence.png", "gray")
    save_preview_gray(gray_confidence, result.gray.confidence, result.gray.valid_mask)
    stripe_order = add("Decoded stripe order", "11_stripe_order.png", "gray")
    save_preview_gray(
        stripe_order,
        result.gray.stripe_order_k.astype(np.float32),
        result.absolute.combined_mask,
    )

    wrapped = add("Wrapped phase", "12_wrapped_phase.png", "phase")
    save_wrapped_phase_preview(wrapped, result.phase.wrapped_phase, result.absolute.combined_mask)
    absolute = add("Absolute phase", "13_absolute_phase.png", "phase")
    save_colormap(
        absolute,
        result.absolute.absolute_phase,
        result.absolute.combined_mask,
        cmap="viridis",
    )
    combined = add("Combined decode mask", "14_combined_mask.png", "mask")
    save_mask(combined, result.absolute.combined_mask)
    height = add("Height map", "15_height_map.png", "height")
    height_title = (
        "Metric height (mm)"
        if result.height.metric
        else "Relative phase (phase units)"
    )
    save_colormap(
        height,
        result.height.height,
        result.height.mask,
        cmap="turbo",
        with_colorbar=True,
        title=height_title,
        colorbar_label=result.height.units,
    )

    overview = debug_dir / f"{prefix}_00_pipeline_overview.png"
    _save_contact_sheet(
        overview,
        [
            ("Raw white", raw_white),
            ("Signal", signal),
            ("Binary/mask", combined),
            ("Stripe order", stripe_order),
            ("Phase", absolute),
            ("Height", height),
        ],
    )
    steps.insert(0, DebugStep("Decode pipeline overview", overview, "overview"))
    return steps


def _save_fusion_debug_steps(fusion: FusionResult, debug_dir: Path) -> list[DebugStep]:
    debug_dir.mkdir(parents=True, exist_ok=True)
    steps: list[DebugStep] = []

    steps.extend(_save_result_debug_steps(fusion.deg0, debug_dir, "deg0"))
    steps.extend(_save_result_debug_steps(fusion.deg180, debug_dir, "deg180"))

    aligned_path = debug_dir / "fusion_01_aligned_height_180.png"
    save_colormap(
        aligned_path,
        fusion.aligned_height_180,
        fusion.aligned_mask_180,
        cmap="turbo",
    )
    steps.append(DebugStep("Aligned 180 height", aligned_path, "fusion"))

    overlay_path = debug_dir / "fusion_02_alignment_mask_overlay.png"
    save_uint8_image(
        overlay_path,
        _mask_overlay(fusion.deg0.height.mask, fusion.aligned_mask_180),
    )
    steps.append(DebugStep("0/180 alignment overlay", overlay_path, "fusion"))

    source_path = debug_dir / "fusion_03_source_map.png"
    save_uint8_image(source_path, _source_map_preview(fusion.source_map))
    steps.append(DebugStep("Fusion source map", source_path, "fusion"))

    confidence_path = debug_dir / "fusion_04_fused_confidence.png"
    save_preview_gray(confidence_path, fusion.confidence, fusion.height.mask)
    steps.append(DebugStep("Fused confidence", confidence_path, "fusion"))

    height_path = debug_dir / "fusion_05_fused_height_map.png"
    height_title = (
        "Fused metric height (mm)"
        if fusion.height.metric
        else "Fused relative phase (phase units)"
    )
    save_colormap(
        height_path,
        fusion.height.height,
        fusion.height.mask,
        cmap="turbo",
        with_colorbar=True,
        title=height_title,
        colorbar_label=fusion.height.units,
    )
    steps.append(DebugStep("Fused height map", height_path, "height"))

    overview_path = debug_dir / "fusion_00_overview.png"
    _save_contact_sheet(
        overview_path,
        [
            ("0 deg height", debug_dir / "deg0_15_height_map.png"),
            ("180 deg height", debug_dir / "deg180_15_height_map.png"),
            ("Aligned 180", aligned_path),
            ("Mask overlay", overlay_path),
            ("Source map", source_path),
            ("Fused height", height_path),
        ],
    )
    steps.insert(0, DebugStep("Fusion overview", overview_path, "overview"))
    return steps


def _prepare_compact_debug_output(output_dir: Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "debug_steps",
        "views",
        "corrected",
        "masks",
        "phase",
        "gray",
        "height",
        "fusion",
        "point_cloud",
    ):
        path = output_dir / name
        if path.is_dir():
            shutil.rmtree(path)
    for name in (
        "debug_manifest.json",
        "decode_report.json",
        "fusion_report.json",
        "analysis_report.json",
        "debug_overview.png",
        "final_result.png",
    ):
        path = output_dir / name
        if path.is_file():
            path.unlink()


def _write_analysis_report(
    output_dir: Path,
    metadata: dict[str, Any],
    *,
    analysis: dict[str, Any] | None = None,
    artifacts: dict[str, Path],
) -> None:
    output_dir = Path(output_dir)
    data = {
        "metadata": _jsonable(metadata),
        "analysis": _jsonable(analysis or {}),
        "artifacts": {key: str(path.resolve()) for key, path in artifacts.items()},
    }
    with (output_dir / "analysis_report.json").open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _copy_config(config: DecodeConfig) -> DecodeConfig:
    data = asdict(config)
    for key in (
        "reference_phase",
        "reference_scan",
        "reference_phase_0",
        "reference_phase_180",
        "reference_scan_0",
        "reference_scan_180",
        "calibration_config",
        "fusion_transform",
    ):
        if data.get(key) is not None:
            data[key] = Path(data[key])
    return DecodeConfig(**data)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _gaussian_blur(image: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return np.zeros_like(image, dtype=np.float32)
    try:
        from scipy.ndimage import gaussian_filter

        return gaussian_filter(image.astype(np.float32), sigma=sigma).astype(np.float32)
    except Exception:
        return _box_blur(image.astype(np.float32), radius=max(1, int(round(sigma))))


def _box_blur(image: np.ndarray, radius: int) -> np.ndarray:
    pad = int(max(radius, 1))
    padded = np.pad(image, pad_width=pad, mode="edge")
    integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    size = 2 * pad + 1
    total = (
        integral[size:, size:]
        - integral[:-size, size:]
        - integral[size:, :-size]
        + integral[:-size, :-size]
    )
    return (total / float(size * size)).astype(np.float32)


def _otsu_threshold(image01: np.ndarray) -> float:
    values = np.asarray(image01, dtype=np.float32)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0.5
    hist, edges = np.histogram(np.clip(values, 0.0, 1.0), bins=256, range=(0.0, 1.0))
    total = float(values.size)
    if total <= 0:
        return 0.5
    centers = (edges[:-1] + edges[1:]) * 0.5
    weight_bg = np.cumsum(hist).astype(np.float64)
    weight_fg = total - weight_bg
    mean_bg = np.cumsum(hist * centers) / np.maximum(weight_bg, 1.0)
    mean_fg = (np.sum(hist * centers) - np.cumsum(hist * centers)) / np.maximum(weight_fg, 1.0)
    between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    index = int(np.nanargmax(between))
    threshold = float(centers[index])
    return float(np.clip(threshold, 0.05, 0.95))


def _remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    mask = np.asarray(mask, dtype=bool)
    if min_area <= 1 or not np.any(mask):
        return mask
    try:
        import cv2  # type: ignore

        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
            mask.astype(np.uint8),
            connectivity=8,
        )
        keep = np.zeros(count, dtype=bool)
        keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= int(min_area)
        return keep[labels]
    except Exception:
        return mask


def _overlay_mask(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.asarray(rgb, dtype=np.float32).copy()
    color = np.array([0.0, 255.0, 255.0], dtype=np.float32)
    out[mask] = 0.35 * out[mask] + 0.65 * color
    return np.clip(out, 0, 255).astype(np.uint8)


def _mask_overlay(mask0: np.ndarray, mask180: np.ndarray) -> np.ndarray:
    mask0 = np.asarray(mask0, dtype=bool)
    mask180 = np.asarray(mask180, dtype=bool)
    out = np.zeros(mask0.shape + (3,), dtype=np.uint8)
    out[mask0 & ~mask180] = (255, 80, 80)
    out[~mask0 & mask180] = (60, 190, 255)
    out[mask0 & mask180] = (255, 255, 255)
    return out


def _source_map_preview(source_map: np.ndarray) -> np.ndarray:
    colors = np.array(
        [
            [0, 0, 0],
            [255, 80, 80],
            [60, 190, 255],
            [255, 230, 80],
        ],
        dtype=np.uint8,
    )
    clipped = np.clip(np.asarray(source_map, dtype=np.uint8), 0, 3)
    return colors[clipped]


def _save_single_image_compact_overview(
    overview_path: Path,
    rgb: np.ndarray,
    intensity: np.ndarray,
    pattern_signal: np.ndarray,
    mask: np.ndarray,
    overlay: np.ndarray,
) -> None:
    """Build one contact sheet without retaining intermediate image files."""
    with tempfile.TemporaryDirectory(prefix="pcb_fpp_debug_overview_") as temp:
        temp_dir = Path(temp)
        original_path = temp_dir / "original.png"
        intensity_path = temp_dir / "intensity.png"
        signal_path = temp_dir / "signal.png"
        mask_path = temp_dir / "mask.png"
        overlay_path = temp_dir / "overlay.png"
        save_uint8_image(original_path, rgb)
        save_preview_gray(intensity_path, intensity)
        save_preview_gray(signal_path, pattern_signal)
        save_mask(mask_path, mask)
        save_uint8_image(overlay_path, overlay)
        _save_contact_sheet(
            overview_path,
            [
                ("Original", original_path),
                ("UV channel", intensity_path),
                ("Background removed", signal_path),
                ("Binary pattern", mask_path),
                ("Final overlay", overlay_path),
            ],
        )


def _save_contact_sheet(path: Path, items: Sequence[tuple[str, Path]]) -> None:
    thumbs: list[tuple[str, Image.Image]] = []
    thumb_w, thumb_h = 320, 240
    for title, item_path in items:
        if not Path(item_path).exists():
            continue
        with Image.open(item_path) as image:
            image = image.convert("RGB")
            image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (thumb_w, thumb_h), (18, 22, 28))
            x = (thumb_w - image.width) // 2
            y = (thumb_h - image.height) // 2
            canvas.paste(image, (x, y))
            thumbs.append((title, canvas))

    if not thumbs:
        return

    cols = min(3, len(thumbs))
    rows = int(np.ceil(len(thumbs) / cols))
    title_h = 26
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + title_h)), (12, 15, 20))
    draw = ImageDraw.Draw(sheet)
    for index, (title, thumb) in enumerate(thumbs):
        row = index // cols
        col = index % cols
        x = col * thumb_w
        y = row * (thumb_h + title_h)
        draw.text((x + 8, y + 6), title, fill=(235, 238, 242))
        sheet.paste(thumb, (x, y + title_h))

    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
