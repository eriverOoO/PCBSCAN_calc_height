from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .calibration import (
    Calibration,
    inverse_linear_height,
    load_calibration,
    triangulation_height,
)
from .graycode import decode_gray_bits
from .io import PatternSet, load_pattern_set, save_float01_png
from .phase import (
    TWO_PI,
    compute_modulation,
    compute_wrapped_phase_4step,
    wrapped_to_0_2pi,
)
from .visualization import (
    finite_percentiles,
    normalize_for_preview,
    save_colormap,
    save_mask,
    save_point_cloud_preview,
    save_preview_gray,
    save_wrapped_phase_preview,
    write_ascii_ply,
)


PATTERN_LABELS = {
    0: "white",
    1: "black",
    2: "gray0",
    3: "gray1",
    4: "gray2",
    5: "gray3",
    6: "gray4",
    7: "gray5",
    8: "gray6",
    9: "gray7",
    10: "sine_000",
    11: "sine_090",
    12: "sine_180",
    13: "sine_270",
}


@dataclass
class DecodeConfig:
    projector_width: int = 1280
    gray_bits: int = 8
    min_signal: float = 20.0
    saturation_threshold: float = 250.0
    dark_threshold: float = 5.0
    modulation_threshold: float = 0.05
    gray_threshold_mode: str = "dynamic_raw"
    sine_source: str = "corrected"
    phase_convention: str = "default"
    phase_direction: str = "normal"
    apply_half_period_correction: bool = False
    boundary_margin: float = 0.35
    detrend: bool = False
    median_filter: int = 0
    height_mode: str = "relative"
    reference_phase: Path | None = None
    reference_scan: Path | None = None
    calibration_config: Path | None = None
    height_sign: float = 1.0
    fusion_mode: str = "modulation-weighted"
    fusion_center: tuple[float, float] | None = None
    fusion_transform: Path | None = None
    save_debug: bool = False
    epsilon: float = 1e-6
    max_point_cloud_points: int = 300_000


@dataclass
class CorrectionResult:
    corrected: dict[int, np.ndarray]
    threshold: np.ndarray
    signal: np.ndarray
    valid_signal_mask: np.ndarray
    saturation_mask: np.ndarray
    dark_mask: np.ndarray
    valid_mask: np.ndarray


@dataclass
class GrayDecodeResult:
    gray_bits: np.ndarray
    gray_code_value: np.ndarray
    stripe_order_k: np.ndarray


@dataclass
class PhaseResult:
    wrapped_phase: np.ndarray
    phi_0_2pi: np.ndarray
    modulation: np.ndarray
    modulation_norm: np.ndarray
    modulation_mask: np.ndarray
    valid_mask: np.ndarray


@dataclass
class AbsolutePhaseResult:
    absolute_phase: np.ndarray
    absolute_phase_raw: np.ndarray
    combined_mask: np.ndarray
    correction_mask: np.ndarray
    stripe_order_corrected: np.ndarray
    notes: list[str] = field(default_factory=list)


@dataclass
class HeightResult:
    height: np.ndarray
    mask: np.ndarray
    mode: str
    metric: bool
    filename: str
    message: str
    units: str = "phase"
    stats: dict[str, float] = field(default_factory=dict)


@dataclass
class DecodeResult:
    patterns: PatternSet
    correction: CorrectionResult
    gray: GrayDecodeResult
    phase: PhaseResult
    absolute: AbsolutePhaseResult
    height: HeightResult
    calibration: Calibration | None
    report: dict[str, Any]


@dataclass
class FusionResult:
    deg0: DecodeResult
    deg180: DecodeResult
    height: HeightResult
    confidence: np.ndarray
    source_map: np.ndarray
    aligned_height_180: np.ndarray
    aligned_mask_180: np.ndarray
    aligned_confidence_180: np.ndarray
    transform_matrix: np.ndarray
    transform_kind: str
    report: dict[str, Any]


class PcbFppDecoder:
    def __init__(self, config: DecodeConfig):
        self.config = config

    def load_scan(self, input_dir: Path) -> PatternSet:
        return load_pattern_set(Path(input_dir), expected_count=14)

    def compute_white_black_correction(self, patterns: PatternSet) -> CorrectionResult:
        white = patterns.images[0].astype(np.float32)
        black = patterns.images[1].astype(np.float32)
        signal = white - black
        threshold = (white + black) / 2.0
        safe_signal = np.maximum(signal, self.config.epsilon)

        valid_signal = signal > self.config.min_signal
        saturation_mask = white < self.config.saturation_threshold
        dark_mask = white > self.config.dark_threshold
        valid_mask = valid_signal & saturation_mask & dark_mask

        corrected = {
            pattern_id: np.clip((image - black) / safe_signal, 0.0, 1.0).astype(np.float32)
            for pattern_id, image in patterns.images.items()
        }
        return CorrectionResult(
            corrected=corrected,
            threshold=threshold.astype(np.float32),
            signal=signal.astype(np.float32),
            valid_signal_mask=valid_signal,
            saturation_mask=saturation_mask,
            dark_mask=dark_mask,
            valid_mask=valid_mask,
        )

    def decode_gray_code(
        self, patterns: PatternSet, correction: CorrectionResult
    ) -> GrayDecodeResult:
        mode = self.config.gray_threshold_mode
        bit_planes: list[np.ndarray] = []
        for offset in range(self.config.gray_bits):
            pattern_id = 2 + offset
            if mode == "dynamic_raw":
                bit = patterns.images[pattern_id] > correction.threshold
            elif mode == "normalized_0p5":
                bit = correction.corrected[pattern_id] > 0.5
            else:
                raise ValueError(
                    "gray_threshold_mode must be dynamic_raw or normalized_0p5"
                )
            bit_planes.append(bit)

        bits = np.stack(bit_planes, axis=-1)
        gray_value, binary_value = decode_gray_bits(bits, bits=self.config.gray_bits)
        return GrayDecodeResult(
            gray_bits=bits.astype(np.uint8),
            gray_code_value=gray_value.astype(np.uint16),
            stripe_order_k=binary_value.astype(np.uint16),
        )

    def compute_wrapped_phase(
        self, patterns: PatternSet, correction: CorrectionResult
    ) -> PhaseResult:
        source = self.config.sine_source
        if source == "corrected":
            images = correction.corrected
        elif source == "raw":
            images = patterns.images
        else:
            raise ValueError("sine_source must be corrected or raw")

        i0 = images[10].astype(np.float32)
        i90 = images[11].astype(np.float32)
        i180 = images[12].astype(np.float32)
        i270 = images[13].astype(np.float32)

        wrapped = compute_wrapped_phase_4step(
            i0, i90, i180, i270, convention=self.config.phase_convention
        )
        phi_0_2pi = wrapped_to_0_2pi(wrapped)
        modulation, modulation_norm = compute_modulation(
            i0, i90, i180, i270, epsilon=self.config.epsilon
        )
        modulation_mask = modulation > self.config.modulation_threshold
        return PhaseResult(
            wrapped_phase=wrapped,
            phi_0_2pi=phi_0_2pi,
            modulation=modulation,
            modulation_norm=modulation_norm,
            modulation_mask=modulation_mask,
            valid_mask=correction.valid_mask,
        )

    def unwrap_absolute_phase(
        self, gray: GrayDecodeResult, phase: PhaseResult
    ) -> AbsolutePhaseResult:
        direction = self.config.phase_direction
        k = gray.stripe_order_k.astype(np.int32)
        phi = phase.phi_0_2pi.astype(np.float32)

        if direction == "normal":
            k_for_phase = k.copy()
            phi_for_phase = phi
        elif direction == "reverse":
            max_k = (1 << self.config.gray_bits) - 1
            k_for_phase = max_k - k
            phi_for_phase = np.mod(TWO_PI - phi, TWO_PI).astype(np.float32)
        else:
            raise ValueError("phase_direction must be normal or reverse")

        absolute_raw = (TWO_PI * k_for_phase + phi_for_phase).astype(np.float32)
        combined_mask = phase.valid_mask & phase.modulation_mask & np.isfinite(absolute_raw)

        corrected_k = k_for_phase.copy()
        correction_mask = np.zeros_like(combined_mask, dtype=bool)
        notes: list[str] = []
        absolute = absolute_raw.copy()
        if self.config.apply_half_period_correction:
            absolute, corrected_k, correction_mask = self._heuristic_boundary_correction(
                absolute_raw, k_for_phase, phi_for_phase, combined_mask
            )
            notes.append(
                "implemented heuristic boundary correction, not exact Cai algorithm"
            )

        absolute = np.where(combined_mask, absolute, np.nan).astype(np.float32)
        absolute_raw = np.where(combined_mask, absolute_raw, np.nan).astype(np.float32)
        return AbsolutePhaseResult(
            absolute_phase=absolute,
            absolute_phase_raw=absolute_raw,
            combined_mask=combined_mask,
            correction_mask=correction_mask,
            stripe_order_corrected=corrected_k.astype(np.int32),
            notes=notes,
        )

    def compute_height(
        self, absolute_phase: AbsolutePhaseResult, calibration: Calibration | None
    ) -> HeightResult:
        mode = self.config.height_mode
        phi = absolute_phase.absolute_phase
        mask = absolute_phase.combined_mask.copy()
        metric = False
        units = "phase"
        filename = "height_relative.npy"
        message = "metric calibration missing; output is relative phase-derived preview, not physical height"

        reference = self._load_reference_phase_if_available()
        if mode == "relative" or reference is None:
            height = phi.copy()
        else:
            if reference.shape != phi.shape:
                raise ValueError(
                    f"reference phase shape {reference.shape} does not match object phase {phi.shape}"
                )
            delta_phi = phi - reference.astype(np.float32)
            if mode == "reference":
                height = self.config.height_sign * delta_phi
                filename = "height_relative.npy"
                message = (
                    "reference phase applied; no metric model supplied, so output is delta phase"
                )
            elif mode == "triangulation":
                if calibration is None or not calibration.is_loaded:
                    raise ValueError("triangulation mode requires --calibration-config")
                height, params = triangulation_height(
                    delta_phi,
                    calibration,
                    sign=self.config.height_sign,
                    epsilon=self.config.epsilon,
                )
                metric = True
                units = "calibration_units"
                filename = "height_mm.npy"
                message = f"triangulation height computed with {params}"
            elif mode == "inverse-linear":
                if calibration is None or not calibration.is_loaded:
                    raise ValueError("inverse-linear mode requires --calibration-config")
                height = inverse_linear_height(delta_phi, calibration, epsilon=self.config.epsilon)
                metric = True
                units = "calibration_units"
                filename = "height_mm.npy"
                message = "inverse-linear height computed from calibration parameters"
            else:
                raise ValueError(
                    "height_mode must be relative, reference, triangulation, or inverse-linear"
                )

        height = np.where(mask, height, np.nan).astype(np.float32)
        if self.config.median_filter and self.config.median_filter > 1:
            height = self._median_filter(height, self.config.median_filter, mask)
        if self.config.detrend:
            height = self._detrend_plane(height, mask)
            if not metric:
                message += "; robust plane detrend applied"

        stats = _array_stats(height, mask)
        return HeightResult(
            height=height.astype(np.float32),
            mask=mask,
            mode=mode,
            metric=metric,
            filename=filename,
            message=message,
            units=units,
            stats=stats,
        )

    def _decode_in_memory(self, input_dir: Path) -> DecodeResult:
        patterns = self.load_scan(input_dir)
        correction = self.compute_white_black_correction(patterns)
        gray = self.decode_gray_code(patterns, correction)
        phase = self.compute_wrapped_phase(patterns, correction)
        absolute = self.unwrap_absolute_phase(gray, phase)
        calibration = load_calibration(self.config.calibration_config)
        height = self.compute_height(absolute, calibration)
        report = self._build_report(patterns, correction, gray, phase, absolute, height, calibration)
        return DecodeResult(
            patterns=patterns,
            correction=correction,
            gray=gray,
            phase=phase,
            absolute=absolute,
            height=height,
            calibration=calibration,
            report=report,
        )

    def fuse_decode_results(self, deg0: DecodeResult, deg180: DecodeResult) -> FusionResult:
        h0 = deg0.height.height.astype(np.float32)
        mask0 = deg0.height.mask & np.isfinite(h0)
        confidence0 = _height_confidence(deg0)

        h180 = deg180.height.height.astype(np.float32)
        mask180 = deg180.height.mask & np.isfinite(h180)
        confidence180 = _height_confidence(deg180)

        matrix, kind = self._fusion_transform(deg0.patterns.shape, deg180.patterns.shape)
        aligned_h180, aligned_mask180 = _warp_float_with_mask(
            h180,
            mask180,
            deg0.patterns.shape,
            matrix,
            kind,
        )
        aligned_confidence180, _ = _warp_float_with_mask(
            confidence180,
            mask180,
            deg0.patterns.shape,
            matrix,
            kind,
        )

        fused_height, fused_mask, source_map, fused_confidence = _fuse_height_maps(
            h0,
            mask0,
            confidence0,
            aligned_h180,
            aligned_mask180,
            aligned_confidence180,
            mode=self.config.fusion_mode,
            epsilon=self.config.epsilon,
        )
        message = (
            "0/180 degree scans fused after spatial alignment; "
            f"fusion mode={self.config.fusion_mode}"
        )
        if not deg0.height.metric:
            message += "; source height is non-metric relative phase preview"
        height = HeightResult(
            height=fused_height,
            mask=fused_mask,
            mode=f"fused-{deg0.height.mode}",
            metric=deg0.height.metric and deg180.height.metric,
            filename="height_fused.npy",
            message=message,
            units=deg0.height.units if deg0.height.units == deg180.height.units else "mixed",
            stats=_array_stats(fused_height, fused_mask),
        )
        report = self._build_fusion_report(
            deg0,
            deg180,
            height,
            source_map,
            matrix,
            kind,
        )
        return FusionResult(
            deg0=deg0,
            deg180=deg180,
            height=height,
            confidence=fused_confidence,
            source_map=source_map,
            aligned_height_180=aligned_h180,
            aligned_mask_180=aligned_mask180,
            aligned_confidence_180=aligned_confidence180,
            transform_matrix=matrix,
            transform_kind=kind,
            report=report,
        )

    def decode_fused(
        self,
        input_dir_0: Path,
        input_dir_180: Path,
        output_dir: Path,
    ) -> FusionResult:
        output_dir = Path(output_dir).expanduser().resolve()
        deg0 = self._decode_in_memory(input_dir_0)
        deg180 = self._decode_in_memory(input_dir_180)
        fusion = self.fuse_decode_results(deg0, deg180)
        self.save_outputs(deg0, output_dir / "views" / "deg_0")
        self.save_outputs(deg180, output_dir / "views" / "deg_180")
        self.save_fusion_outputs(fusion, output_dir)
        return fusion

    def save_outputs(self, result: DecodeResult, output_dir: Path) -> None:
        output_dir = Path(output_dir).expanduser().resolve()
        corrected_dir = output_dir / "corrected"
        masks_dir = output_dir / "masks"
        phase_dir = output_dir / "phase"
        gray_dir = output_dir / "gray"
        height_dir = output_dir / "height"
        point_dir = output_dir / "point_cloud"
        for directory in (
            corrected_dir,
            masks_dir,
            phase_dir,
            gray_dir,
            height_dir,
            point_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        for pattern_id in range(14):
            label = PATTERN_LABELS.get(pattern_id, f"pattern_{pattern_id:03d}")
            save_float01_png(
                corrected_dir / f"corrected_{pattern_id:02d}_{label}.png",
                result.correction.corrected[pattern_id],
            )

        save_mask(masks_dir / "valid_mask.png", result.correction.valid_mask)
        save_mask(masks_dir / "modulation_mask.png", result.phase.modulation_mask)
        save_mask(masks_dir / "saturation_mask.png", result.correction.saturation_mask)
        save_mask(masks_dir / "combined_mask.png", result.absolute.combined_mask)

        np.save(phase_dir / "wrapped_phase.npy", result.phase.wrapped_phase)
        save_wrapped_phase_preview(
            phase_dir / "wrapped_phase_preview.png",
            result.phase.wrapped_phase,
            result.absolute.combined_mask,
        )
        np.save(phase_dir / "absolute_phase.npy", result.absolute.absolute_phase)
        np.save(phase_dir / "absolute_phase_raw.npy", result.absolute.absolute_phase_raw)
        save_colormap(
            phase_dir / "absolute_phase_preview.png",
            result.absolute.absolute_phase,
            result.absolute.combined_mask,
            cmap="viridis",
        )
        save_colormap(
            phase_dir / "absolute_phase_before_correction_preview.png",
            result.absolute.absolute_phase_raw,
            result.absolute.combined_mask,
            cmap="viridis",
        )
        save_mask(phase_dir / "boundary_correction_mask.png", result.absolute.correction_mask)

        np.save(gray_dir / "gray_bits.npy", result.gray.gray_bits)
        np.save(gray_dir / "gray_code_value.npy", result.gray.gray_code_value)
        np.save(gray_dir / "stripe_order_k.npy", result.gray.stripe_order_k)
        save_preview_gray(
            gray_dir / "stripe_order_preview.png",
            result.gray.stripe_order_k.astype(np.float32),
            result.absolute.combined_mask,
        )

        np.save(height_dir / result.height.filename, result.height.height)
        if result.height.metric:
            np.save(height_dir / "height.npy", result.height.height)
        else:
            np.save(height_dir / "height.npy", result.height.height)
        save_colormap(
            height_dir / "height_heatmap.png",
            result.height.height,
            result.height.mask,
            cmap="turbo",
            with_colorbar=True,
            title="Height / relative phase",
        )
        save_colormap(
            height_dir / "height_heatmap_colorbar.png",
            result.height.height,
            result.height.mask,
            cmap="turbo",
            with_colorbar=True,
            title="Height / relative phase",
        )
        save_colormap(
            height_dir / "height_relative_preview.png",
            result.height.height,
            result.height.mask,
            cmap="turbo",
        )

        ply_count = write_ascii_ply(
            point_dir / "point_cloud.ply",
            result.height.height,
            result.height.mask,
            max_points=self.config.max_point_cloud_points,
        )
        save_point_cloud_preview(
            point_dir / "point_cloud_preview.png",
            result.height.height,
            result.height.mask,
        )
        result.report["point_cloud"] = {
            "ply_vertices_written": ply_count,
            "max_point_cloud_points": self.config.max_point_cloud_points,
        }

        with (output_dir / "decode_report.json").open("w", encoding="utf-8") as f:
            json.dump(result.report, f, indent=2, ensure_ascii=False)

    def save_fusion_outputs(self, fusion: FusionResult, output_dir: Path) -> None:
        output_dir = Path(output_dir).expanduser().resolve()
        height_dir = output_dir / "height"
        masks_dir = output_dir / "masks"
        fusion_dir = output_dir / "fusion"
        point_dir = output_dir / "point_cloud"
        for directory in (height_dir, masks_dir, fusion_dir, point_dir):
            directory.mkdir(parents=True, exist_ok=True)

        np.save(height_dir / fusion.height.filename, fusion.height.height)
        np.save(height_dir / "height.npy", fusion.height.height)
        save_colormap(
            height_dir / "height_heatmap.png",
            fusion.height.height,
            fusion.height.mask,
            cmap="turbo",
            with_colorbar=True,
            title="Fused height",
        )
        save_colormap(
            height_dir / "height_heatmap_colorbar.png",
            fusion.height.height,
            fusion.height.mask,
            cmap="turbo",
            with_colorbar=True,
            title="Fused height",
        )
        save_colormap(
            height_dir / "height_fused_preview.png",
            fusion.height.height,
            fusion.height.mask,
            cmap="turbo",
        )

        source_map = fusion.source_map
        save_mask(masks_dir / "fused_mask.png", fusion.height.mask)
        save_mask(masks_dir / "source_deg_0_only.png", source_map == 1)
        save_mask(masks_dir / "source_deg_180_only.png", source_map == 2)
        save_mask(masks_dir / "source_overlap.png", source_map == 3)
        save_mask(masks_dir / "source_missing.png", source_map == 0)
        np.save(masks_dir / "source_map.npy", source_map)

        np.save(fusion_dir / "aligned_height_180.npy", fusion.aligned_height_180)
        np.save(fusion_dir / "aligned_mask_180.npy", fusion.aligned_mask_180)
        np.save(fusion_dir / "confidence.npy", fusion.confidence)
        np.save(fusion_dir / "aligned_confidence_180.npy", fusion.aligned_confidence_180)
        np.save(fusion_dir / "transform_matrix.npy", fusion.transform_matrix)
        save_colormap(
            fusion_dir / "aligned_height_180_preview.png",
            fusion.aligned_height_180,
            fusion.aligned_mask_180,
            cmap="turbo",
        )
        save_colormap(
            fusion_dir / "confidence_preview.png",
            fusion.confidence,
            fusion.height.mask,
            cmap="viridis",
        )

        ply_count = write_ascii_ply(
            point_dir / "point_cloud.ply",
            fusion.height.height,
            fusion.height.mask,
            max_points=self.config.max_point_cloud_points,
        )
        save_point_cloud_preview(
            point_dir / "point_cloud_preview.png",
            fusion.height.height,
            fusion.height.mask,
        )
        fusion.report["point_cloud"] = {
            "ply_vertices_written": ply_count,
            "max_point_cloud_points": self.config.max_point_cloud_points,
        }

        with (output_dir / "decode_report.json").open("w", encoding="utf-8") as f:
            json.dump(fusion.report, f, indent=2, ensure_ascii=False)
        with (output_dir / "fusion_report.json").open("w", encoding="utf-8") as f:
            json.dump(fusion.report, f, indent=2, ensure_ascii=False)

    def decode(self, input_dir: Path, output_dir: Path) -> DecodeResult:
        result = self._decode_in_memory(input_dir)
        self.save_outputs(result, output_dir)
        return result

    def _fusion_transform(
        self,
        target_shape: tuple[int, int],
        source_shape: tuple[int, int],
    ) -> tuple[np.ndarray, str]:
        if self.config.fusion_transform is not None:
            matrix = _load_transform_matrix(self.config.fusion_transform)
            if matrix.shape == (2, 3):
                return matrix.astype(np.float32), "affine"
            if matrix.shape == (3, 3):
                return matrix.astype(np.float32), "homography"
            raise ValueError(
                "fusion transform must be a 2x3 affine matrix or 3x3 homography"
            )

        if target_shape != source_shape:
            raise ValueError(
                "0 degree and 180 degree scans must have the same image shape unless "
                "--fusion-transform is provided"
            )
        height, width = target_shape
        if self.config.fusion_center is None:
            cx = (width - 1) / 2.0
            cy = (height - 1) / 2.0
        else:
            cx, cy = self.config.fusion_center
        matrix = np.array([[-1.0, 0.0, 2.0 * cx], [0.0, -1.0, 2.0 * cy]], dtype=np.float32)
        return matrix, "rotation_180"

    def _build_fusion_report(
        self,
        deg0: DecodeResult,
        deg180: DecodeResult,
        height: HeightResult,
        source_map: np.ndarray,
        matrix: np.ndarray,
        transform_kind: str,
    ) -> dict[str, Any]:
        total = int(np.prod(source_map.shape))
        coverage = {
            "deg_0_only_ratio": float(np.count_nonzero(source_map == 1) / total),
            "deg_180_only_ratio": float(np.count_nonzero(source_map == 2) / total),
            "overlap_ratio": float(np.count_nonzero(source_map == 3) / total),
            "fused_valid_ratio": float(np.count_nonzero(source_map != 0) / total),
            "missing_ratio": float(np.count_nonzero(source_map == 0) / total),
        }
        return {
            "input_dir": str(deg0.patterns.input_dir),
            "input_dir_180": str(deg180.patterns.input_dir),
            "image_shape": {"height": source_map.shape[0], "width": source_map.shape[1]},
            "config": _jsonable_config(self.config),
            "fusion": {
                "mode": self.config.fusion_mode,
                "transform_kind": transform_kind,
                "transform_matrix": matrix.tolist(),
                "coverage": coverage,
            },
            "views": {
                "deg_0": {
                    "input_dir": str(deg0.patterns.input_dir),
                    "combined_mask_ratio": deg0.report["mask_coverage"]["combined_mask_ratio"],
                    "height": deg0.report["height"],
                },
                "deg_180": {
                    "input_dir": str(deg180.patterns.input_dir),
                    "combined_mask_ratio": deg180.report["mask_coverage"]["combined_mask_ratio"],
                    "height": deg180.report["height"],
                },
            },
            "height": {
                "mode": height.mode,
                "metric": height.metric,
                "units": height.units,
                "message": height.message,
                "stats": height.stats,
            },
        }

    def _build_report(
        self,
        patterns: PatternSet,
        correction: CorrectionResult,
        gray: GrayDecodeResult,
        phase: PhaseResult,
        absolute: AbsolutePhaseResult,
        height: HeightResult,
        calibration: Calibration | None,
    ) -> dict[str, Any]:
        shape = patterns.shape
        total = int(np.prod(shape))
        mask_stats = {
            "valid_mask_ratio": float(np.count_nonzero(correction.valid_mask) / total),
            "modulation_mask_ratio": float(np.count_nonzero(phase.modulation_mask) / total),
            "combined_mask_ratio": float(np.count_nonzero(absolute.combined_mask) / total),
            "saturation_pass_ratio": float(np.count_nonzero(correction.saturation_mask) / total),
            "correction_pixel_ratio": float(np.count_nonzero(absolute.correction_mask) / total),
        }
        modulation_values = phase.modulation[absolute.combined_mask]
        modulation_norm_values = phase.modulation_norm[absolute.combined_mask]
        report = {
            "input_dir": str(patterns.input_dir),
            "image_shape": {"height": shape[0], "width": shape[1]},
            "input_files": {f"{k:02d}": str(v) for k, v in patterns.files.items()},
            "config": _jsonable_config(self.config),
            "thresholds": {
                "min_signal": self.config.min_signal,
                "saturation_threshold": self.config.saturation_threshold,
                "dark_threshold": self.config.dark_threshold,
                "modulation_threshold": self.config.modulation_threshold,
                "gray_threshold_mode": self.config.gray_threshold_mode,
            },
            "mask_coverage": mask_stats,
            "signal_stats": _array_stats(correction.signal, correction.valid_mask),
            "modulation_stats": _value_stats(modulation_values),
            "modulation_norm_stats": _value_stats(modulation_norm_values),
            "stripe_order": {
                "min": int(np.nanmin(gray.stripe_order_k)),
                "max": int(np.nanmax(gray.stripe_order_k)),
                "gray_bits": self.config.gray_bits,
            },
            "phase": {
                "phase_convention": self.config.phase_convention,
                "phase_direction": self.config.phase_direction,
                "half_period_correction_enabled": self.config.apply_half_period_correction,
                "notes": absolute.notes,
            },
            "height": {
                "mode": height.mode,
                "metric": height.metric,
                "units": height.units,
                "message": height.message,
                "stats": height.stats,
            },
            "calibration": {
                "used": bool(calibration and calibration.is_loaded),
                "path": str(calibration.path) if calibration and calibration.path else None,
            },
        }
        return report

    def _load_reference_phase_if_available(self) -> np.ndarray | None:
        if self.config.reference_phase is not None:
            path = Path(self.config.reference_phase).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"reference phase file does not exist: {path}")
            return np.load(path).astype(np.float32)

        if self.config.reference_scan is not None:
            ref_path = Path(self.config.reference_scan).expanduser().resolve()
            processed_phase = ref_path / "phase" / "absolute_phase.npy"
            if processed_phase.exists():
                return np.load(processed_phase).astype(np.float32)

            ref_patterns = self.load_scan(ref_path)
            ref_correction = self.compute_white_black_correction(ref_patterns)
            ref_gray = self.decode_gray_code(ref_patterns, ref_correction)
            ref_phase = self.compute_wrapped_phase(ref_patterns, ref_correction)
            ref_absolute = self.unwrap_absolute_phase(ref_gray, ref_phase)
            return ref_absolute.absolute_phase.astype(np.float32)

        return None

    def _heuristic_boundary_correction(
        self,
        absolute_raw: np.ndarray,
        k: np.ndarray,
        phi: np.ndarray,
        mask: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        near_phase_boundary = (phi < self.config.boundary_margin) | (
            phi > TWO_PI - self.config.boundary_margin
        )
        k_boundary = _stripe_boundary_mask(k)
        candidates = mask & near_phase_boundary & k_boundary
        if not np.any(candidates):
            return absolute_raw.copy(), k.copy(), np.zeros_like(mask, dtype=bool)

        local_median = self._median_filter(
            np.where(mask, absolute_raw, np.nan), size=3, mask=mask
        )
        local_median = np.where(np.isfinite(local_median), local_median, absolute_raw)

        best_abs = absolute_raw.copy()
        best_k = k.copy()
        best_error = np.abs(absolute_raw - local_median)
        max_k = (1 << self.config.gray_bits) - 1
        for adjustment in (-1, 1):
            candidate_k = k + adjustment
            valid_k = (candidate_k >= 0) & (candidate_k <= max_k)
            candidate_abs = TWO_PI * candidate_k + phi
            error = np.abs(candidate_abs - local_median)
            improve = candidates & valid_k & (error < best_error)
            best_abs = np.where(improve, candidate_abs, best_abs)
            best_k = np.where(improve, candidate_k, best_k)
            best_error = np.where(improve, error, best_error)

        correction_mask = candidates & (best_k != k)
        return best_abs.astype(np.float32), best_k.astype(np.int32), correction_mask

    def _median_filter(self, image: np.ndarray, size: int, mask: np.ndarray) -> np.ndarray:
        if size <= 1:
            return image.astype(np.float32)
        if size % 2 == 0:
            size += 1
        fill = image.copy()
        median_value = np.nanmedian(fill[mask & np.isfinite(fill)])
        if not np.isfinite(median_value):
            median_value = 0.0
        fill = np.where(np.isfinite(fill), fill, median_value)
        try:
            from scipy.ndimage import median_filter

            filtered = median_filter(fill, size=size, mode="nearest")
        except Exception:
            filtered = _numpy_median_filter(fill, size=size)
        return np.where(mask, filtered, np.nan).astype(np.float32)

    def _detrend_plane(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        finite = mask & np.isfinite(image)
        rows, cols = np.nonzero(finite)
        if rows.size < 3:
            return image
        values = image[rows, cols]
        max_samples = 50_000
        if rows.size > max_samples:
            step = int(math.ceil(rows.size / max_samples))
            rows_fit = rows[::step]
            cols_fit = cols[::step]
            values_fit = values[::step]
        else:
            rows_fit, cols_fit, values_fit = rows, cols, values
        design = np.column_stack(
            [cols_fit.astype(np.float64), rows_fit.astype(np.float64), np.ones_like(rows_fit)]
        )
        coeff, *_ = np.linalg.lstsq(design, values_fit.astype(np.float64), rcond=None)
        grid_y, grid_x = np.indices(image.shape)
        plane = coeff[0] * grid_x + coeff[1] * grid_y + coeff[2]
        detrended = image - plane.astype(np.float32)
        return np.where(mask, detrended, np.nan).astype(np.float32)


def _stripe_boundary_mask(k: np.ndarray) -> np.ndarray:
    boundary = np.zeros_like(k, dtype=bool)
    boundary[:, 1:] |= k[:, 1:] != k[:, :-1]
    boundary[:, :-1] |= k[:, 1:] != k[:, :-1]
    boundary[1:, :] |= k[1:, :] != k[:-1, :]
    boundary[:-1, :] |= k[1:, :] != k[:-1, :]
    # One-pixel dilation through shifts keeps the correction local to boundaries.
    dilated = boundary.copy()
    dilated[:, 1:] |= boundary[:, :-1]
    dilated[:, :-1] |= boundary[:, 1:]
    dilated[1:, :] |= boundary[:-1, :]
    dilated[:-1, :] |= boundary[1:, :]
    return dilated


def _numpy_median_filter(image: np.ndarray, size: int) -> np.ndarray:
    pad = size // 2
    padded = np.pad(image, pad_width=pad, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, (size, size))
    return np.median(windows, axis=(-2, -1)).astype(np.float32)


def _value_stats(values: np.ndarray) -> dict[str, float | None]:
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "max": float(np.max(values)),
    }


def _array_stats(image: np.ndarray, mask: np.ndarray) -> dict[str, float | None]:
    return _value_stats(np.asarray(image)[mask])


def _jsonable_config(config: DecodeConfig) -> dict[str, Any]:
    data = asdict(config)
    for key, value in list(data.items()):
        if isinstance(value, Path):
            data[key] = str(value)
    return data


def _height_confidence(result: DecodeResult) -> np.ndarray:
    confidence = np.asarray(result.phase.modulation, dtype=np.float32)
    valid = result.height.mask & np.isfinite(result.height.height) & np.isfinite(confidence)
    return np.where(valid, np.maximum(confidence, 0.0), 0.0).astype(np.float32)


def _fuse_height_maps(
    height0: np.ndarray,
    mask0: np.ndarray,
    confidence0: np.ndarray,
    height180: np.ndarray,
    mask180: np.ndarray,
    confidence180: np.ndarray,
    mode: str,
    epsilon: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    valid0 = mask0 & np.isfinite(height0)
    valid180 = mask180 & np.isfinite(height180)
    only0 = valid0 & ~valid180
    only180 = ~valid0 & valid180
    both = valid0 & valid180

    fused = np.full(height0.shape, np.nan, dtype=np.float32)
    fused[only0] = height0[only0]
    fused[only180] = height180[only180]

    if mode == "average":
        fused[both] = 0.5 * (height0[both] + height180[both])
    elif mode == "modulation-weighted":
        w0 = np.where(both, confidence0, 0.0).astype(np.float32)
        w180 = np.where(both, confidence180, 0.0).astype(np.float32)
        weight_sum = w0 + w180
        weighted = np.divide(
            w0 * height0 + w180 * height180,
            np.maximum(weight_sum, epsilon),
            out=np.full(height0.shape, np.nan, dtype=np.float32),
        )
        fallback = 0.5 * (height0 + height180)
        fused[both] = np.where(weight_sum[both] > epsilon, weighted[both], fallback[both])
    else:
        raise ValueError("fusion_mode must be average or modulation-weighted")

    source_map = np.zeros(height0.shape, dtype=np.uint8)
    source_map[only0] = 1
    source_map[only180] = 2
    source_map[both] = 3

    fused_mask = source_map != 0
    fused_confidence = np.zeros(height0.shape, dtype=np.float32)
    fused_confidence[only0] = confidence0[only0]
    fused_confidence[only180] = confidence180[only180]
    fused_confidence[both] = np.maximum(confidence0[both], confidence180[both])
    return fused.astype(np.float32), fused_mask, source_map, fused_confidence


def _warp_float_with_mask(
    image: np.ndarray,
    mask: np.ndarray,
    target_shape: tuple[int, int],
    matrix: np.ndarray,
    transform_kind: str,
) -> tuple[np.ndarray, np.ndarray]:
    if _is_exact_180_flip(matrix, image.shape, target_shape):
        return np.rot90(image, 2).astype(np.float32), np.rot90(mask, 2).astype(bool)

    valid = mask & np.isfinite(image)
    values = np.where(valid, image, 0.0).astype(np.float32)
    weights = valid.astype(np.float32)
    warped_values = _warp_array(values, target_shape, matrix, transform_kind)
    warped_weights = _warp_array(weights, target_shape, matrix, transform_kind)
    warped_mask = warped_weights > 0.5
    warped = np.divide(
        warped_values,
        np.maximum(warped_weights, 1e-6),
        out=np.zeros(target_shape, dtype=np.float32),
    )
    return np.where(warped_mask, warped, np.nan).astype(np.float32), warped_mask


def _warp_array(
    image: np.ndarray,
    target_shape: tuple[int, int],
    matrix: np.ndarray,
    transform_kind: str,
) -> np.ndarray:
    try:
        import cv2  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "OpenCV is required for custom fusion transforms; install opencv-python"
        ) from exc

    height, width = target_shape
    if transform_kind in ("rotation_180", "affine"):
        return cv2.warpAffine(
            image.astype(np.float32),
            matrix[:2, :].astype(np.float32),
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        ).astype(np.float32)
    if transform_kind == "homography":
        return cv2.warpPerspective(
            image.astype(np.float32),
            matrix.astype(np.float32),
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        ).astype(np.float32)
    raise ValueError(f"unsupported transform kind: {transform_kind}")


def _is_exact_180_flip(
    matrix: np.ndarray,
    source_shape: tuple[int, int],
    target_shape: tuple[int, int],
) -> bool:
    if source_shape != target_shape or matrix.shape != (2, 3):
        return False
    height, width = target_shape
    expected = np.array(
        [[-1.0, 0.0, width - 1.0], [0.0, -1.0, height - 1.0]],
        dtype=np.float32,
    )
    return bool(np.allclose(matrix, expected, atol=1e-6))


def _load_transform_matrix(path: Path) -> np.ndarray:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"fusion transform file does not exist: {path}")

    if path.suffix.lower() == ".npy":
        return np.asarray(np.load(path), dtype=np.float32)
    if path.suffix.lower() == ".npz":
        archive = np.load(path)
        for key in ("matrix", "homography", "affine"):
            if key in archive:
                return np.asarray(archive[key], dtype=np.float32)
        first_key = next(iter(archive.files))
        return np.asarray(archive[first_key], dtype=np.float32)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        for key in ("matrix", "transform", "homography", "affine"):
            if key in data:
                data = data[key]
                break
    return np.asarray(data, dtype=np.float32)
