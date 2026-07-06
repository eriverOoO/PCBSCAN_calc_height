from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .decoder import DecodeConfig, DecodeResult, PcbFppDecoder
from .io import save_uint8_image
from .phase import TWO_PI
from .visualization import save_colormap, save_mask, save_preview_gray


@dataclass
class SyntheticPcbConfig:
    width: int = 320
    height: int = 200
    gray_bits: int = 8
    stripe_width_px: float = 5.0
    phase_offset_cycles: float = 2.0
    keystone_x_per_y: float = 0.04
    board_margin: int = 12
    height_scale: float = 1.0
    trace_height: float = 0.20
    pad_height: float = 0.45
    component_height: float = 0.90
    plane_tilt_x: float = 0.0
    plane_tilt_y: float = 0.0
    calibration_d: float = 300.0
    calibration_l: float = 120.0
    calibration_p: float = 5.0
    height_sign: float = 1.0
    include_inverted_gray: bool = True
    add_defects: bool = False
    noise_sigma: float = 0.0
    blur_sigma: float = 0.0
    random_seed: int = 7
    black_level: float = 10.0
    white_level: float = 240.0
    sine_mean: float = 0.5
    sine_amplitude: float = 0.42
    gray_low: float = 0.08
    gray_high: float = 0.92
    min_signal: float = 20.0
    saturation_threshold: float = 250.0
    dark_threshold: float = 5.0
    modulation_threshold: float = 0.05
    gray_pair_min_contrast: float = 0.05
    apply_half_period_correction: bool = False
    median_filter: int = 0
    detrend: bool = False
    max_point_cloud_points: int = 300_000


@dataclass
class SyntheticScene:
    board_mask: np.ndarray
    truth_mask: np.ndarray
    reference_absolute_phase: np.ndarray
    object_absolute_phase: np.ndarray
    delta_phase: np.ndarray
    reference_u: np.ndarray
    object_u: np.ndarray
    stripe_order_k: np.ndarray
    height: np.ndarray
    reflectance: np.ndarray
    black: np.ndarray
    signal: np.ndarray
    shadow_mask: np.ndarray
    saturation_mask: np.ndarray


@dataclass
class SimulationResult:
    scene: SyntheticScene
    decode_result: DecodeResult
    output_root: Path
    object_scan_dir: Path
    reference_scan_dir: Path
    processed_object_dir: Path
    processed_reference_dir: Path
    truth_dir: Path
    report: dict[str, Any]


class PcbFppSimulator:
    def __init__(self, config: SyntheticPcbConfig | None = None):
        self.config = config or SyntheticPcbConfig()

    def run(self, output_root: Path) -> SimulationResult:
        output_root = Path(output_root).expanduser().resolve()
        object_scan_dir = output_root / "captures" / "virtual_pcb" / "deg_0"
        reference_scan_dir = output_root / "captures" / "reference_plane" / "deg_0"
        processed_reference_dir = output_root / "processed" / "reference_plane"
        processed_object_dir = output_root / "processed" / "virtual_pcb"
        truth_dir = output_root / "truth"

        for directory in (
            object_scan_dir,
            reference_scan_dir,
            processed_reference_dir,
            processed_object_dir,
            truth_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        scene = self.generate_scene()
        rng = np.random.default_rng(self.config.random_seed)
        self.write_scan(reference_scan_dir, scene.reference_absolute_phase, scene, rng)
        self.write_scan(object_scan_dir, scene.object_absolute_phase, scene, rng)
        self.save_truth(scene, truth_dir)

        calibration_path = output_root / "calibration.json"
        self.write_calibration(calibration_path)

        reference_config = self._decode_config(height_mode="relative")
        PcbFppDecoder(reference_config).decode(reference_scan_dir, processed_reference_dir)

        reference_phase = processed_reference_dir / "phase" / "absolute_phase.npy"
        object_config = self._decode_config(
            height_mode="triangulation",
            reference_phase=reference_phase,
            calibration_config=calibration_path,
        )
        decode_result = PcbFppDecoder(object_config).decode(
            object_scan_dir,
            processed_object_dir,
        )

        report = self.evaluate(
            scene,
            decode_result,
            output_root,
            object_scan_dir,
            reference_scan_dir,
            processed_object_dir,
            processed_reference_dir,
            truth_dir,
        )
        with (output_root / "simulation_report.json").open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return SimulationResult(
            scene=scene,
            decode_result=decode_result,
            output_root=output_root,
            object_scan_dir=object_scan_dir,
            reference_scan_dir=reference_scan_dir,
            processed_object_dir=processed_object_dir,
            processed_reference_dir=processed_reference_dir,
            truth_dir=truth_dir,
            report=report,
        )

    def generate_scene(self) -> SyntheticScene:
        cfg = self.config
        if cfg.width <= 8 or cfg.height <= 8:
            raise ValueError("width and height must be larger than 8 pixels")
        if cfg.stripe_width_px <= 0:
            raise ValueError("stripe_width_px must be positive")
        if cfg.calibration_d <= 0 or cfg.calibration_l <= 0 or cfg.calibration_p <= 0:
            raise ValueError("calibration d, l, and p must be positive")
        if cfg.height_sign not in (-1.0, 1.0):
            raise ValueError("height_sign must be 1.0 or -1.0")

        rows, cols = np.indices((cfg.height, cfg.width), dtype=np.float32)
        board_mask = _board_mask(cfg.height, cfg.width, cfg.board_margin)
        height, feature_masks = _virtual_height_map(cfg, rows, cols, board_mask)
        height = np.where(board_mask, height, np.nan).astype(np.float32)

        delta_phase = _height_to_delta_phase(height, cfg)
        cy = (cfg.height - 1.0) / 2.0
        reference_u = (
            cfg.phase_offset_cycles
            + (cols + cfg.keystone_x_per_y * (rows - cy)) / cfg.stripe_width_px
        ).astype(np.float32)
        reference_absolute = (TWO_PI * reference_u).astype(np.float32)
        object_absolute = (reference_absolute + delta_phase).astype(np.float32)
        object_u = (object_absolute / TWO_PI).astype(np.float32)

        max_k = (1 << cfg.gray_bits) - 1
        in_gray_range = (object_u >= 0.0) & (object_u < float(max_k + 1))
        stripe_order = np.floor(np.where(in_gray_range, object_u, 0.0)).astype(np.uint16)

        reflectance = _reflectance_map(cfg, rows, cols, board_mask, feature_masks)
        shadow_mask = np.zeros((cfg.height, cfg.width), dtype=bool)
        saturation_mask = np.zeros((cfg.height, cfg.width), dtype=bool)
        if cfg.add_defects:
            shadow_mask, saturation_mask = _defect_masks(cfg, rows, cols, board_mask)

        signal_span = max(cfg.white_level - cfg.black_level, 1.0)
        signal = signal_span * reflectance
        signal = np.where(board_mask, signal, 0.0).astype(np.float32)
        signal = np.where(shadow_mask, signal * 0.05, signal).astype(np.float32)
        signal = np.where(saturation_mask, max(255.0 - cfg.black_level, signal_span), signal)
        black = np.full((cfg.height, cfg.width), cfg.black_level, dtype=np.float32)

        white = black + signal
        truth_mask = (
            board_mask
            & in_gray_range
            & np.isfinite(height)
            & (signal > cfg.min_signal)
            & (white < cfg.saturation_threshold)
            & (white > cfg.dark_threshold)
            & ~shadow_mask
            & ~saturation_mask
        )

        return SyntheticScene(
            board_mask=board_mask,
            truth_mask=truth_mask,
            reference_absolute_phase=reference_absolute,
            object_absolute_phase=object_absolute,
            delta_phase=delta_phase.astype(np.float32),
            reference_u=reference_u,
            object_u=object_u,
            stripe_order_k=stripe_order,
            height=height,
            reflectance=reflectance.astype(np.float32),
            black=black,
            signal=signal.astype(np.float32),
            shadow_mask=shadow_mask,
            saturation_mask=saturation_mask,
        )

    def write_scan(
        self,
        scan_dir: Path,
        absolute_phase: np.ndarray,
        scene: SyntheticScene,
        rng: np.random.Generator,
    ) -> None:
        scan_dir.mkdir(parents=True, exist_ok=True)
        _clear_pattern_files(scan_dir)

        white = scene.black + scene.signal
        black = scene.black
        _save_sensor_image(scan_dir / "pattern_000.png", white, self.config, rng)
        _save_sensor_image(scan_dir / "pattern_001.png", black, self.config, rng)

        k, phi = _phase_components(absolute_phase, self.config.gray_bits)
        gray = np.bitwise_xor(k, np.right_shift(k, 1)).astype(np.uint16)
        for bit in range(self.config.gray_bits):
            bit_value = ((gray >> (self.config.gray_bits - 1 - bit)) & 1).astype(bool)
            normalized = np.where(bit_value, self.config.gray_high, self.config.gray_low)
            _save_sensor_image(
                scan_dir / f"pattern_{2 + bit:03d}.png",
                _apply_pattern(scene, normalized),
                self.config,
                rng,
            )
            if self.config.include_inverted_gray:
                inverted = 1.0 - normalized
                _save_sensor_image(
                    scan_dir / f"pattern_{14 + bit:03d}.png",
                    _apply_pattern(scene, inverted),
                    self.config,
                    rng,
                )

        sine_patterns = {
            10: self.config.sine_mean + self.config.sine_amplitude * np.sin(phi),
            11: self.config.sine_mean - self.config.sine_amplitude * np.cos(phi),
            12: self.config.sine_mean - self.config.sine_amplitude * np.sin(phi),
            13: self.config.sine_mean + self.config.sine_amplitude * np.cos(phi),
        }
        for pattern_id, normalized in sine_patterns.items():
            _save_sensor_image(
                scan_dir / f"pattern_{pattern_id:03d}.png",
                _apply_pattern(scene, normalized),
                self.config,
                rng,
            )

        scan_log = {
            "description": "Synthetic PCB FPP scan generated by PcbFppSimulator",
            "patterns": [
                {"pattern_id": int(path.stem.split("_")[-1]), "file": path.name}
                for path in sorted(scan_dir.glob("pattern_*.png"))
            ],
        }
        with (scan_dir / "scan_log.json").open("w", encoding="utf-8") as f:
            json.dump(scan_log, f, indent=2)

    def save_truth(self, scene: SyntheticScene, truth_dir: Path) -> None:
        truth_dir.mkdir(parents=True, exist_ok=True)
        np.save(truth_dir / "height_true.npy", scene.height)
        np.save(truth_dir / "delta_phase_true.npy", scene.delta_phase)
        np.save(truth_dir / "absolute_phase_true.npy", scene.object_absolute_phase)
        np.save(truth_dir / "reference_phase_true.npy", scene.reference_absolute_phase)
        np.save(truth_dir / "uv_reference.npy", scene.reference_u)
        np.save(truth_dir / "uv_object.npy", scene.object_u)
        np.save(truth_dir / "stripe_order_true.npy", scene.stripe_order_k)
        np.save(truth_dir / "truth_mask.npy", scene.truth_mask)

        save_mask(truth_dir / "truth_mask.png", scene.truth_mask)
        save_mask(truth_dir / "board_mask.png", scene.board_mask)
        save_mask(truth_dir / "shadow_mask.png", scene.shadow_mask)
        save_mask(truth_dir / "saturation_mask.png", scene.saturation_mask)
        save_colormap(
            truth_dir / "height_true.png",
            scene.height,
            scene.truth_mask,
            cmap="turbo",
            with_colorbar=True,
            title="Synthetic true height",
        )
        save_colormap(
            truth_dir / "delta_phase_true.png",
            scene.delta_phase,
            scene.truth_mask,
            cmap="coolwarm",
            with_colorbar=True,
            title="Synthetic true delta phase",
        )
        save_preview_gray(truth_dir / "reflectance_preview.png", scene.reflectance, scene.board_mask)
        save_preview_gray(
            truth_dir / "stripe_order_true_preview.png",
            scene.stripe_order_k.astype(np.float32),
            scene.truth_mask,
        )

    def write_calibration(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "geometry": {
                "d": self.config.calibration_d,
                "l": self.config.calibration_l,
                "p": self.config.calibration_p,
            },
            "projector": {"tilt_degrees": None},
            "synthetic": True,
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def evaluate(
        self,
        scene: SyntheticScene,
        decode_result: DecodeResult,
        output_root: Path,
        object_scan_dir: Path,
        reference_scan_dir: Path,
        processed_object_dir: Path,
        processed_reference_dir: Path,
        truth_dir: Path,
    ) -> dict[str, Any]:
        accuracy_dir = output_root / "accuracy"
        accuracy_dir.mkdir(parents=True, exist_ok=True)

        decoded_height = decode_result.height.height.astype(np.float32)
        decoded_abs = decode_result.absolute.absolute_phase.astype(np.float32)
        decoded_delta = decode_result.height.delta_phase
        if decoded_delta is None:
            decoded_delta = np.full_like(scene.delta_phase, np.nan, dtype=np.float32)

        common_mask = (
            scene.truth_mask
            & decode_result.height.mask
            & np.isfinite(decoded_height)
            & np.isfinite(scene.height)
        )
        height_error = np.where(common_mask, decoded_height - scene.height, np.nan)
        phase_mask = (
            scene.truth_mask
            & decode_result.absolute.combined_mask
            & np.isfinite(decoded_abs)
            & np.isfinite(scene.object_absolute_phase)
        )
        phase_error = np.where(
            phase_mask,
            decoded_abs - scene.object_absolute_phase,
            np.nan,
        )
        delta_mask = (
            scene.truth_mask
            & decode_result.height.mask
            & np.isfinite(decoded_delta)
            & np.isfinite(scene.delta_phase)
        )
        delta_error = np.where(delta_mask, decoded_delta - scene.delta_phase, np.nan)
        stripe_error = (
            decode_result.gray.stripe_order_k.astype(np.int32)
            - scene.stripe_order_k.astype(np.int32)
        )
        stripe_mask = scene.truth_mask & decode_result.absolute.combined_mask
        stripe_error_masked = np.where(stripe_mask, stripe_error, 0)

        np.save(accuracy_dir / "height_error.npy", height_error.astype(np.float32))
        np.save(accuracy_dir / "absolute_phase_error.npy", phase_error.astype(np.float32))
        np.save(accuracy_dir / "delta_phase_error.npy", delta_error.astype(np.float32))
        np.save(accuracy_dir / "stripe_order_error.npy", stripe_error_masked.astype(np.int32))
        save_colormap(
            accuracy_dir / "height_error.png",
            height_error,
            common_mask,
            cmap="coolwarm",
            with_colorbar=True,
            title="Decoded height error",
        )
        save_colormap(
            accuracy_dir / "absolute_phase_error.png",
            phase_error,
            phase_mask,
            cmap="coolwarm",
            with_colorbar=True,
            title="Absolute phase error",
        )
        save_colormap(
            accuracy_dir / "delta_phase_error.png",
            delta_error,
            delta_mask,
            cmap="coolwarm",
            with_colorbar=True,
            title="Delta phase error",
        )
        save_preview_gray(
            accuracy_dir / "stripe_order_error_preview.png",
            np.abs(stripe_error_masked).astype(np.float32),
            stripe_mask,
        )

        total_truth = int(np.count_nonzero(scene.truth_mask))
        decoded_valid = int(np.count_nonzero(common_mask))
        stripe_exact = int(np.count_nonzero((stripe_error == 0) & stripe_mask))
        stripe_total = int(np.count_nonzero(stripe_mask))
        report = {
            "simulation_config": asdict(self.config),
            "paths": {
                "output_root": str(output_root),
                "object_scan_dir": str(object_scan_dir),
                "reference_scan_dir": str(reference_scan_dir),
                "processed_object_dir": str(processed_object_dir),
                "processed_reference_dir": str(processed_reference_dir),
                "truth_dir": str(truth_dir),
                "accuracy_dir": str(accuracy_dir),
            },
            "coverage": {
                "truth_valid_pixels": total_truth,
                "decoded_valid_pixels": decoded_valid,
                "decoded_over_truth_ratio": _safe_ratio(decoded_valid, total_truth),
                "decoder_combined_mask_ratio": decode_result.report["mask_coverage"][
                    "combined_mask_ratio"
                ],
            },
            "metrics": {
                "height": _error_metrics(height_error, common_mask),
                "absolute_phase": _error_metrics(phase_error, phase_mask),
                "delta_phase": _error_metrics(delta_error, delta_mask),
                "stripe_order": {
                    "checked_pixels": stripe_total,
                    "exact_pixels": stripe_exact,
                    "exact_ratio": _safe_ratio(stripe_exact, stripe_total),
                    "max_abs_error": int(np.max(np.abs(stripe_error[stripe_mask])))
                    if stripe_total
                    else None,
                },
            },
            "decoder_height": decode_result.report["height"],
            "decoder_mask_coverage": decode_result.report["mask_coverage"],
        }
        return report

    def _decode_config(
        self,
        height_mode: str,
        reference_phase: Path | None = None,
        calibration_config: Path | None = None,
    ) -> DecodeConfig:
        return DecodeConfig(
            gray_bits=self.config.gray_bits,
            min_signal=self.config.min_signal,
            saturation_threshold=self.config.saturation_threshold,
            dark_threshold=self.config.dark_threshold,
            modulation_threshold=self.config.modulation_threshold,
            gray_decode_mode="auto",
            gray_threshold_mode="dynamic_raw",
            gray_pair_min_contrast=self.config.gray_pair_min_contrast,
            phase_convention="default",
            phase_direction="normal",
            apply_half_period_correction=self.config.apply_half_period_correction,
            detrend=self.config.detrend,
            median_filter=self.config.median_filter,
            height_mode=height_mode,
            reference_phase=reference_phase,
            calibration_config=calibration_config,
            height_sign=self.config.height_sign,
            max_point_cloud_points=self.config.max_point_cloud_points,
        )


def _board_mask(height: int, width: int, requested_margin: int) -> np.ndarray:
    margin = min(max(1, requested_margin), max(1, min(height, width) // 5))
    mask = np.zeros((height, width), dtype=bool)
    mask[margin : height - margin, margin : width - margin] = True
    return mask


def _virtual_height_map(
    cfg: SyntheticPcbConfig,
    rows: np.ndarray,
    cols: np.ndarray,
    board_mask: np.ndarray,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    height = np.zeros((cfg.height, cfg.width), dtype=np.float32)
    cx = (cfg.width - 1.0) / 2.0
    cy = (cfg.height - 1.0) / 2.0
    norm_x = (cols - cx) / max(cfg.width, 1)
    norm_y = (rows - cy) / max(cfg.height, 1)
    height += cfg.plane_tilt_x * norm_x + cfg.plane_tilt_y * norm_y

    trace_mask = np.zeros_like(board_mask)
    pad_mask = np.zeros_like(board_mask)
    component_mask = np.zeros_like(board_mask)

    trace_specs = (
        (0.16, 0.30, 0.72, 0.34),
        (0.20, 0.58, 0.80, 0.62),
        (0.46, 0.18, 0.50, 0.78),
        (0.68, 0.22, 0.72, 0.70),
    )
    for x0, y0, x1, y1 in trace_specs:
        trace_mask |= _rect_fraction_mask(rows, cols, cfg.width, cfg.height, x0, y0, x1, y1)

    for fx, fy, radius in (
        (0.22, 0.30, 0.045),
        (0.72, 0.34, 0.045),
        (0.24, 0.58, 0.050),
        (0.78, 0.62, 0.050),
        (0.50, 0.20, 0.040),
        (0.50, 0.78, 0.040),
    ):
        pad_mask |= _disk_fraction_mask(rows, cols, cfg.width, cfg.height, fx, fy, radius)

    component_mask |= _rect_fraction_mask(rows, cols, cfg.width, cfg.height, 0.38, 0.40, 0.62, 0.56)
    component_mask |= _rect_fraction_mask(rows, cols, cfg.width, cfg.height, 0.30, 0.68, 0.43, 0.80)

    height = np.where(trace_mask, height + cfg.trace_height * cfg.height_scale, height)
    height = np.where(pad_mask, height + cfg.pad_height * cfg.height_scale, height)
    height = np.where(
        component_mask,
        height + cfg.component_height * cfg.height_scale,
        height,
    )
    height = np.where(board_mask, height, np.nan).astype(np.float32)
    return height, {
        "trace": trace_mask & board_mask,
        "pad": pad_mask & board_mask,
        "component": component_mask & board_mask,
    }


def _reflectance_map(
    cfg: SyntheticPcbConfig,
    rows: np.ndarray,
    cols: np.ndarray,
    board_mask: np.ndarray,
    feature_masks: dict[str, np.ndarray],
) -> np.ndarray:
    texture = (
        0.03 * np.sin(cols / max(cfg.width, 1) * 8.0 * math.pi)
        + 0.02 * np.cos(rows / max(cfg.height, 1) * 6.0 * math.pi)
    )
    reflectance = 0.72 + texture
    reflectance = np.where(feature_masks["trace"], 0.86, reflectance)
    reflectance = np.where(feature_masks["pad"], 0.96, reflectance)
    reflectance = np.where(feature_masks["component"], 0.48, reflectance)
    reflectance = np.where(board_mask, reflectance, 0.0)
    return np.clip(reflectance, 0.0, 1.0).astype(np.float32)


def _defect_masks(
    cfg: SyntheticPcbConfig,
    rows: np.ndarray,
    cols: np.ndarray,
    board_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    shadow = _rect_fraction_mask(rows, cols, cfg.width, cfg.height, 0.74, 0.12, 0.88, 0.86)
    specular = _disk_fraction_mask(rows, cols, cfg.width, cfg.height, 0.34, 0.28, 0.07)
    return shadow & board_mask, specular & board_mask


def _height_to_delta_phase(height: np.ndarray, cfg: SyntheticPcbConfig) -> np.ndarray:
    signed_height = height / cfg.height_sign
    denominator = cfg.calibration_p * (cfg.calibration_d - signed_height)
    delta = signed_height * TWO_PI * cfg.calibration_l / denominator
    return np.where(np.isfinite(height), delta, np.nan).astype(np.float32)


def _phase_components(absolute_phase: np.ndarray, gray_bits: int) -> tuple[np.ndarray, np.ndarray]:
    u = np.asarray(absolute_phase, dtype=np.float32) / TWO_PI
    max_k = (1 << gray_bits) - 1
    k = np.floor(np.where(np.isfinite(u), u, 0.0)).astype(np.int32)
    k = np.clip(k, 0, max_k).astype(np.uint16)
    phi = np.mod(np.where(np.isfinite(absolute_phase), absolute_phase, 0.0), TWO_PI)
    return k, phi.astype(np.float32)


def _apply_pattern(scene: SyntheticScene, normalized: np.ndarray) -> np.ndarray:
    normalized = np.clip(np.asarray(normalized, dtype=np.float32), 0.0, 1.0)
    image = scene.black + scene.signal * normalized
    image = np.where(scene.saturation_mask, 255.0, image)
    return image.astype(np.float32)


def _save_sensor_image(
    path: Path,
    image: np.ndarray,
    cfg: SyntheticPcbConfig,
    rng: np.random.Generator,
) -> None:
    work = np.asarray(image, dtype=np.float32)
    if cfg.blur_sigma > 0:
        try:
            from scipy.ndimage import gaussian_filter

            work = gaussian_filter(work, sigma=cfg.blur_sigma, mode="nearest")
        except Exception:
            pass
    if cfg.noise_sigma > 0:
        work = work + rng.normal(0.0, cfg.noise_sigma, size=work.shape).astype(np.float32)
    save_uint8_image(path, np.clip(work, 0.0, 255.0))


def _clear_pattern_files(scan_dir: Path) -> None:
    for path in scan_dir.glob("pattern_*.png"):
        path.unlink()
    scan_log = scan_dir / "scan_log.json"
    if scan_log.exists():
        scan_log.unlink()


def _rect_fraction_mask(
    rows: np.ndarray,
    cols: np.ndarray,
    width: int,
    height: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> np.ndarray:
    return (
        (cols >= x0 * width)
        & (cols <= x1 * width)
        & (rows >= y0 * height)
        & (rows <= y1 * height)
    )


def _disk_fraction_mask(
    rows: np.ndarray,
    cols: np.ndarray,
    width: int,
    height: int,
    fx: float,
    fy: float,
    radius: float,
) -> np.ndarray:
    cx = fx * width
    cy = fy * height
    radius_px = radius * min(width, height)
    return (cols - cx) * (cols - cx) + (rows - cy) * (rows - cy) <= radius_px * radius_px


def _error_metrics(error: np.ndarray, mask: np.ndarray) -> dict[str, float | int | None]:
    values = np.asarray(error, dtype=np.float64)[mask]
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {
            "count": 0,
            "mean": None,
            "mae": None,
            "rmse": None,
            "p95_abs": None,
            "max_abs": None,
        }
    abs_values = np.abs(values)
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "mae": float(np.mean(abs_values)),
        "rmse": float(np.sqrt(np.mean(values * values))),
        "p95_abs": float(np.percentile(abs_values, 95.0)),
        "max_abs": float(np.max(abs_values)),
    }


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)
