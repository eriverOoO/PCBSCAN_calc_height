from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def build_capture_diagnosis(result: Any) -> dict[str, Any]:
    """Summarize capture quality using arrays already produced by the decoder."""
    scope = _analysis_scope(result)
    scope_count = int(np.count_nonzero(scope))
    config = result.report["config"]

    white = np.asarray(result.patterns.images[0], dtype=np.float32)
    black = np.asarray(result.patterns.images[1], dtype=np.float32)
    signal = np.asarray(result.correction.signal, dtype=np.float32)
    gray_confidence = np.asarray(result.gray.confidence, dtype=np.float32)
    modulation = np.asarray(result.phase.modulation, dtype=np.float32)

    metrics = {
        "analysis_pixels": scope_count,
        "white_mean": _masked_mean(white, scope),
        "black_mean": _masked_mean(black, scope),
        "signal_mean": _masked_mean(signal, scope),
        "signal_p10": _masked_percentile(signal, scope, 10.0),
        "signal_valid_ratio": _ratio(result.correction.valid_signal_mask, scope),
        "overexposed_ratio": _ratio(~result.correction.saturation_mask, scope),
        "dark_ratio": _ratio(~result.correction.dark_mask, scope),
        "gray_valid_ratio": _ratio(result.gray.valid_mask, scope),
        "gray_confidence_median": _masked_percentile(gray_confidence, scope, 50.0),
        "modulation_valid_ratio": _ratio(result.phase.modulation_mask, scope),
        "modulation_median": _masked_percentile(modulation, scope, 50.0),
        "combined_valid_ratio": _ratio(result.absolute.combined_mask, scope),
    }
    status, recommendations = _evaluate(metrics)
    return {
        "status": status,
        "metrics": metrics,
        "thresholds": {
            "min_signal": float(config["min_signal"]),
            "saturation_threshold": float(config["saturation_threshold"]),
            "dark_threshold": float(config["dark_threshold"]),
            "gray_pair_min_contrast": float(config["gray_pair_min_contrast"]),
            "modulation_threshold": float(config["modulation_threshold"]),
        },
        "gray_decode_mode": result.gray.mode,
        "recommendations": recommendations,
    }


def write_capture_diagnosis(result: Any, output_dir: Path) -> Path:
    diagnosis = build_capture_diagnosis(result)
    path = Path(output_dir) / "capture_diagnosis.txt"
    path.write_text(_format_capture_diagnosis(diagnosis), encoding="utf-8-sig")
    return path


def write_feedback_packet(result: Any, output_dir: Path, *, fusion: bool = False) -> Path:
    """Write a compact Markdown packet intended to be pasted into a support chat."""
    report = result.report
    config = report.get("config", {})
    lines = [
        "# FPP feedback packet",
        "",
        "Paste this entire file when requesting analysis of this decode result.",
        "",
        "## Run",
        f"- kind: {'0/180 fused' if fusion else 'single view'}",
        f"- input: {report.get('input_dir', report.get('input_dir_0', 'unknown'))}",
        f"- image size: {_image_size_text(report)}",
        f"- height mode: {report.get('height', {}).get('mode', 'unknown')}",
        f"- metric output: {report.get('height', {}).get('metric', False)}",
        f"- units: {report.get('height', {}).get('units', 'unknown')}",
        "",
        "## Decoder settings",
        f"- input color mode: {config.get('input_color_mode')}",
        f"- phase convention: {config.get('phase_convention')}",
        f"- phase direction: {config.get('phase_direction')}",
        f"- min signal / modulation / Gray-pair contrast: "
        f"{config.get('min_signal')} / {config.get('modulation_threshold')} / "
        f"{config.get('gray_pair_min_contrast')}",
        f"- analysis ROI: {config.get('analysis_roi_mode')}",
        "",
    ]
    lines.extend(_fusion_feedback_lines(report, config) if fusion else _view_feedback_lines(report, "view"))
    lines.extend(
        [
            "",
            "## Reference and calibration",
            f"- reference used: {report.get('height', {}).get('reference_used', False)}",
            f"- reference scan 0: {config.get('reference_scan_0')}",
            f"- reference scan 180: {config.get('reference_scan_180')}",
            f"- reference phase 0: {config.get('reference_phase_0')}",
            f"- reference phase 180: {config.get('reference_phase_180')}",
            f"- calibration: {report.get('calibration', {}).get('path')}",
            "",
            "## Files to attach if requested",
            "- decode_report.json (or fusion_report.json)",
            "- capture_diagnosis.txt",
            "- phase/absolute_phase_preview.png",
            "- height/delta_phase_preview.png when a reference is used",
            "- masks/combined_mask.png",
        ]
    )
    path = Path(output_dir) / "feedback_packet.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_fusion_diagnosis(fusion: Any, output_dir: Path) -> Path:
    deg0 = build_capture_diagnosis(fusion.deg0)
    deg180 = build_capture_diagnosis(fusion.deg180)
    fusion_scope = _analysis_scope(fusion.deg0)
    fused_valid_ratio = _ratio(fusion.height.mask, fusion_scope)
    overlap_ratio = _ratio(fusion.source_map == 3, fusion_scope)

    lines = [
        "0/180 촬영 자동 진단",
        "",
        _format_view_summary("0도", deg0),
        _format_view_summary("180도", deg180),
        f"병합 유효 픽셀: {_percent(fused_valid_ratio)}",
        f"두 각도 공통 유효 픽셀: {_percent(overlap_ratio)}",
        "",
        "권장 조치",
    ]

    recommendations: list[str] = []
    for label, diagnosis in (("0도", deg0), ("180도", deg180)):
        for recommendation in diagnosis["recommendations"]:
            if "주요 이상이 없습니다" not in recommendation:
                recommendations.append(f"{label}: {recommendation}")

    valid0 = deg0["metrics"]["combined_valid_ratio"]
    valid180 = deg180["metrics"]["combined_valid_ratio"]
    if abs(valid0 - valid180) >= 0.15:
        worse = "0도" if valid0 < valid180 else "180도"
        recommendations.insert(
            0,
            f"{worse} 결과가 상대 각도보다 크게 나쁩니다. 해당 각도의 그림자, 반사, 초점을 먼저 확인하세요.",
        )
    if not recommendations:
        recommendations.append("현재 임계값 기준 두 촬영 모두 주요 이상이 없습니다. 고정 노출, 초점, AWB 상태를 유지하세요.")

    lines.extend(f"- {text}" for text in _deduplicate(recommendations)[:4])
    lines.extend(
        [
            "",
            "참고: 이 결과는 원인을 확정하는 판정이 아니라 촬영 수치에 따른 점검 우선순위입니다.",
        ]
    )
    path = Path(output_dir) / "capture_diagnosis.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def _view_feedback_lines(report: dict[str, Any], label: str) -> list[str]:
    coverage = report.get("mask_coverage", {})
    phase = report.get("phase", {})
    return [
        "## Capture quality",
        f"- {label} combined valid ratio: {_ratio_text(coverage.get('combined_mask_ratio'))}",
        f"- {label} White/Black valid ratio: {_ratio_text(coverage.get('valid_mask_ratio'))}",
        f"- {label} Gray valid ratio: {_ratio_text(coverage.get('gray_valid_mask_ratio'))}",
        f"- {label} modulation valid ratio: {_ratio_text(coverage.get('modulation_mask_ratio'))}",
        f"- cycle-slip ratio: {_ratio_text(phase.get('cycle_slip_ratio'))}",
    ]


def _fusion_feedback_lines(report: dict[str, Any], config: dict[str, Any]) -> list[str]:
    fusion = report.get("fusion", {})
    coverage = fusion.get("coverage", {})
    lines = [
        "## Fusion quality",
        f"- registration: {config.get('fusion_registration', 'custom or rotation-180')}",
        f"- transform kind: {fusion.get('transform_kind')}",
        f"- fused valid ratio: {_ratio_text(coverage.get('fused_valid_ratio'))}",
        f"- overlap ratio: {_ratio_text(coverage.get('overlap_ratio'))}",
        f"- fusion rejection ratio: {_ratio_text(fusion.get('rejection_ratio'))}",
        f"- fusion cycle-slip ratio: {_ratio_text(fusion.get('cycle_slip_ratio'))}",
        f"- transform matrix: {fusion.get('transform_matrix')}",
        "",
        "## Per-view capture quality",
    ]
    views = report.get("views", {})
    for angle, view_report in (("0", views.get("deg_0", {})), ("180", views.get("deg_180", {}))):
        lines.extend(_view_feedback_lines(view_report, f"{angle} degree"))
    return lines


def _image_size_text(report: dict[str, Any]) -> str:
    image_shape = report.get("image_shape", {})
    if not image_shape:
        return "unknown"
    return f"{image_shape.get('width')} x {image_shape.get('height')}"


def _ratio_text(value: Any) -> str:
    try:
        return f"{100.0 * float(value):.2f}%"
    except (TypeError, ValueError):
        return "unknown"


def _format_capture_diagnosis(diagnosis: dict[str, Any]) -> str:
    metrics = diagnosis["metrics"]
    thresholds = diagnosis["thresholds"]
    if diagnosis["gray_decode_mode"] == "inverted_pair":
        gray_line = (
            f"- Gray 유효 픽셀: {_percent(metrics['gray_valid_ratio'])}, "
            f"confidence 중앙값 {metrics['gray_confidence_median']:.3f} "
            f"(기준 >= {thresholds['gray_pair_min_contrast']:g})"
        )
    else:
        gray_line = (
            f"- Gray 유효 픽셀: {_percent(metrics['gray_valid_ratio'])}, "
            f"confidence 중앙값 {metrics['gray_confidence_median']:.3f} "
            "(반전 Gray 없음: confidence는 참고값)"
        )

    lines = [
        "촬영 자동 진단",
        "",
        f"판정: {diagnosis['status']}",
        f"분석 픽셀: {metrics['analysis_pixels']:,}",
        f"최종 유효 픽셀: {_percent(metrics['combined_valid_ratio'])}",
        "",
        "수치 요약",
        f"- White 평균: {metrics['white_mean']:.1f} / 255",
        f"- Black 평균: {metrics['black_mean']:.1f} / 255",
        (
            f"- White-Black 신호: 평균 {metrics['signal_mean']:.1f}, "
            f"하위 10% {metrics['signal_p10']:.1f} "
            f"(기준 > {thresholds['min_signal']:g})"
        ),
        (
            f"- 과노출 픽셀: {_percent(metrics['overexposed_ratio'])} "
            f"(White >= {thresholds['saturation_threshold']:g})"
        ),
        (
            f"- 암부 픽셀: {_percent(metrics['dark_ratio'])} "
            f"(White <= {thresholds['dark_threshold']:g})"
        ),
        gray_line,
        (
            f"- Sine modulation 유효 픽셀: {_percent(metrics['modulation_valid_ratio'])}, "
            f"중앙값 {metrics['modulation_median']:.3f} "
            f"(기준 > {thresholds['modulation_threshold']:g})"
        ),
        "",
        "권장 조치",
    ]
    lines.extend(f"- {text}" for text in diagnosis["recommendations"])
    lines.extend(
        [
            "",
            "참고: 이 결과는 원인을 확정하는 판정이 아니라 촬영 수치에 따른 점검 우선순위입니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _format_view_summary(label: str, diagnosis: dict[str, Any]) -> str:
    metrics = diagnosis["metrics"]
    return (
        f"{label}: {diagnosis['status']} | 유효 {_percent(metrics['combined_valid_ratio'])} | "
        f"과노출 {_percent(metrics['overexposed_ratio'])} | 암부 {_percent(metrics['dark_ratio'])} | "
        f"Gray {_percent(metrics['gray_valid_ratio'])} | Modulation {_percent(metrics['modulation_valid_ratio'])}"
    )


def _evaluate(metrics: dict[str, float | int]) -> tuple[str, list[str]]:
    overexposed = float(metrics["overexposed_ratio"])
    dark = float(metrics["dark_ratio"])
    signal_fail = 1.0 - float(metrics["signal_valid_ratio"])
    gray_fail = 1.0 - float(metrics["gray_valid_ratio"])
    gray_weak = float(metrics["gray_confidence_median"]) < 0.05
    modulation_fail = 1.0 - float(metrics["modulation_valid_ratio"])
    combined = float(metrics["combined_valid_ratio"])

    if (
        combined >= 0.90
        and not gray_weak
        and max(overexposed, dark, signal_fail, gray_fail, modulation_fail) < 0.10
    ):
        status = "양호"
    elif combined >= 0.70:
        status = "점검 권장"
    else:
        status = "재촬영 설정 점검 필요"

    recommendations: list[str] = []
    if overexposed >= 0.02 and dark >= 0.05:
        recommendations.append(
            "밝은 영역과 어두운 영역이 함께 많습니다. 반사각, 카메라·프로젝터 정렬, 조명 균일도를 먼저 조정하세요."
        )
    elif overexposed >= 0.02:
        recommendations.append("카메라 노출 또는 ISO, 필요하면 프로젝터 밝기를 낮춰 포화를 줄이세요.")
    elif dark >= 0.05:
        recommendations.append("카메라 노출 또는 ISO를 높이고, 프로젝터가 시편 전체를 비추는지 확인하세요.")

    if signal_fail >= 0.10:
        recommendations.append("White-Black 대비가 부족합니다. 주변광을 줄이고 프로젝터 밝기와 초점을 확인하세요.")
    if gray_fail >= 0.10 or gray_weak:
        recommendations.append("Gray 분리가 불안정합니다. 자동 노출·AWB를 잠그고 패턴 순서와 촬영 중 움직임을 확인하세요.")
    if modulation_fail >= 0.10:
        recommendations.append("사인 패턴이 흐립니다. 카메라·프로젝터 초점, 흔들림, 반사광을 확인하세요.")
    if not recommendations:
        recommendations.append("현재 임계값 기준 주요 이상이 없습니다. 고정 노출, 초점, AWB 상태를 유지하세요.")
    return status, _deduplicate(recommendations)[:3]


def _analysis_scope(result: Any) -> np.ndarray:
    if result.analysis_roi is not None:
        return np.asarray(result.analysis_roi.mask, dtype=bool)
    return np.ones(result.patterns.shape, dtype=bool)


def _ratio(mask: np.ndarray, scope: np.ndarray) -> float:
    denominator = int(np.count_nonzero(scope))
    if denominator == 0:
        return 0.0
    return float(np.count_nonzero(np.asarray(mask, dtype=bool) & scope) / denominator)


def _masked_mean(values: np.ndarray, mask: np.ndarray) -> float:
    selected = np.asarray(values, dtype=np.float32)[mask]
    selected = selected[np.isfinite(selected)]
    return float(np.mean(selected)) if selected.size else 0.0


def _masked_percentile(values: np.ndarray, mask: np.ndarray, percentile: float) -> float:
    selected = np.asarray(values, dtype=np.float32)[mask]
    selected = selected[np.isfinite(selected)]
    return float(np.percentile(selected, percentile)) if selected.size else 0.0


def _percent(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def _deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
