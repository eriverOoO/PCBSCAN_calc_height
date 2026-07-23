from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image

from .manifests import pattern_files, sha256_file, write_json


SCANNER_SIM_SAMPLES: Mapping[str, Mapping[str, str]] = {
    "img_40.exr": {
        "role": "physical Gray/stripe-pattern HDR capture",
        "url": "https://geometryprocessing.github.io/scanner-sim/data/img_40.exr",
        "expected_sha256": "44deff2b483019fddf0fe13bf8dbdd7761c34b1cb4c6a7c0c42c8e50be3cd116",
    },
    "leo_010.exr": {
        "role": "physical micro-phase/unstructured-light HDR capture",
        "url": "https://geometryprocessing.github.io/scanner-sim/data/leo_010.exr",
        "expected_sha256": "2e1d7a41ec58d1a54f271d30371c3ad7de75697b027164072b02568b6c53025c",
    },
    "background.exr": {
        "role": "physical background capture with object removed",
        "url": "https://geometryprocessing.github.io/scanner-sim/data/background.exr",
        "expected_sha256": "48876cc06ece6c67fa8ed35b66327c0778c8bf75eab6f40631ec09d3b25aa4a9",
    },
}


def _sample_finite(image: np.ndarray, maximum: int = 2_000_000) -> np.ndarray:
    values = np.asarray(image, dtype=np.float32).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size > maximum:
        stride = max(1, values.size // maximum)
        values = values[::stride]
    return values


def linear_image_statistics(image: np.ndarray) -> dict[str, Any]:
    """Return scale-aware descriptors without claiming camera calibration.

    The descriptors are useful as a domain-gap sentinel.  They are not PSF,
    read-noise, gamma, or saturation estimates because one scene image cannot
    identify those quantities independently.
    """

    array = np.asarray(image, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("linear image statistics require a 2-D luminance array")
    finite = _sample_finite(array)
    if finite.size == 0:
        raise ValueError("image contains no finite pixels")
    quantile_levels = (0.1, 1.0, 5.0, 50.0, 95.0, 99.0, 99.9)
    quantiles = np.percentile(finite, quantile_levels)
    robust_high = max(float(quantiles[-1]), 1e-12)
    positive = finite[finite > 0]
    positive_low = float(np.percentile(positive, 1.0)) if positive.size else 0.0

    stride_y = max(1, array.shape[0] // 1024)
    stride_x = max(1, array.shape[1] // 1024)
    reduced = array[::stride_y, ::stride_x]
    reduced = np.nan_to_num(reduced, nan=0.0, posinf=robust_high, neginf=0.0)
    normalized = np.clip(reduced / robust_high, 0.0, 4.0)
    dx = np.diff(normalized, axis=1)
    dy = np.diff(normalized, axis=0)
    gradient_rms = float(
        np.sqrt(0.5 * (np.mean(dx * dx) + np.mean(dy * dy)))
    )

    return {
        "shape": list(array.shape),
        "finite_fraction": float(np.count_nonzero(np.isfinite(array)) / array.size),
        "linear_quantiles": {
            str(level): float(value)
            for level, value in zip(quantile_levels, quantiles, strict=True)
        },
        "robust_dynamic_range_p99p9_over_positive_p1": (
            float(robust_high / positive_low) if positive_low > 0 else None
        ),
        "fraction_above_linear_unity": float(np.count_nonzero(finite > 1.0) / finite.size),
        "normalized_dark_tail_fraction_below_1pct": float(
            np.count_nonzero(finite <= robust_high * 0.01) / finite.size
        ),
        "normalized_highlight_tail_fraction_above_95pct": float(
            np.count_nonzero(finite >= robust_high * 0.95) / finite.size
        ),
        "normalized_gradient_rms": gradient_rms,
        "identifiability_warning": (
            "single-image descriptors only; do not interpret as PSF, gamma, "
            "read-noise, or sensor-saturation measurements"
        ),
    }


def read_exr_luminance(path: str | Path) -> np.ndarray:
    try:
        import OpenEXR  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "OpenEXR is required for physical HDR evidence; install requirements.txt"
        ) from exc
    source = Path(path)
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
    available = [name for name in ("Y", "R", "G", "B") if name in channels]
    if not available:
        raise ValueError(f"EXR has no supported luminance/RGB channels: {source}")
    return np.asarray(channels[available[0]].pixels, dtype=np.float32)


def analyze_scanner_sim_samples(root: str | Path) -> dict[str, Any]:
    folder = Path(root).expanduser().resolve()
    samples: dict[str, Any] = {}
    for name, metadata in SCANNER_SIM_SAMPLES.items():
        path = folder / name
        if not path.exists():
            raise FileNotFoundError(
                f"missing scanner-sim sample: {path}; run fetch_external_fpp.py "
                "--dataset scanner_sim_physical --sample-set --yes"
            )
        luminance = read_exr_luminance(path)
        actual_sha256 = sha256_file(path)
        expected_sha256 = str(metadata["expected_sha256"])
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"scanner-sim checksum mismatch for {path}: {actual_sha256} != {expected_sha256}"
            )
        samples[name] = {
            **metadata,
            "sha256": actual_sha256,
            "statistics": linear_image_statistics(luminance),
        }
    return {
        "dataset": "scanner_sim_physical",
        "evidence_class": "peer-reviewed physical structured-light HDR capture without independent per-pixel GT",
        "ground_truth_available": False,
        "paper": "https://openreview.net/forum?id=bNL5VlTfe3p",
        "dataset_page": "https://geometryprocessing.github.io/scanner-sim/",
        "archive": "https://archive.nyu.edu/handle/2451/63306",
        "calibration_archive": "https://archive.nyu.edu/handle/2451/63307",
        "license": "CC BY 4.0",
        "samples": samples,
    }


def analyze_synthetic_sequence(root: str | Path) -> dict[str, Any]:
    folder = Path(root).expanduser().resolve()
    source = folder / "object_0" if (folder / "object_0").is_dir() else folder
    mapping = pattern_files(source)
    if sorted(mapping) != list(range(22)):
        raise ValueError(f"expected exact synthetic pattern ids 0..21 below {source}")
    frames: dict[str, Any] = {}
    for pattern_id in (0, 1, 10, 11, 12, 13):
        path = mapping[pattern_id]
        with Image.open(path) as image:
            array = np.asarray(image).astype(np.float32)
        maximum = 65535.0 if array.max(initial=0.0) > 255.0 else 255.0
        frames[str(pattern_id)] = {
            "file": path.name,
            "sha256": sha256_file(path),
            "statistics": linear_image_statistics(array / maximum),
        }
    return {
        "dataset": "local_procedural_22_pattern_sequence",
        "source_root": str(source),
        "frames": frames,
    }


def build_source_evidence_report(
    scanner_root: str | Path, synthetic_root: str | Path
) -> dict[str, Any]:
    physical = analyze_scanner_sim_samples(scanner_root)
    synthetic = analyze_synthetic_sequence(synthetic_root)
    physical_fringe = physical["samples"]["img_40.exr"]["statistics"]
    synthetic_fringe = synthetic["frames"]["10"]["statistics"]
    physical_gradient = float(physical_fringe["normalized_gradient_rms"])
    synthetic_gradient = float(synthetic_fringe["normalized_gradient_rms"])
    return {
        "schema_version": 1,
        "validation_level": "external-evidence",
        "real_world_accuracy_claim": False,
        "purpose": "detect image-domain mismatch; never tune decoder thresholds from this report",
        "physical_reference": physical,
        "synthetic_candidate": synthetic,
        "descriptive_comparison": {
            "physical_to_synthetic_normalized_gradient_rms_ratio": (
                physical_gradient / synthetic_gradient
                if synthetic_gradient > 0
                else None
            ),
            "comparison_limit": (
                "different scene, optics, resolution, and pattern family; descriptors are "
                "a domain-gap sentinel, not a pass/fail accuracy metric"
            ),
        },
        "excluded_inferences": [
            "PSF from a single scene image",
            "camera gamma from an HDR radiance image",
            "read noise without repeated dark/flat frames",
            "metric height accuracy without registered ground truth",
        ],
    }


def write_source_evidence_report(
    scanner_root: str | Path,
    synthetic_root: str | Path,
    output_root: str | Path,
) -> tuple[Path, Path]:
    output = Path(output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = build_source_evidence_report(scanner_root, synthetic_root)
    json_path = write_json(output / "source_evidence.json", report)

    physical_rows = []
    for name, item in report["physical_reference"]["samples"].items():
        stats = item["statistics"]
        q = stats["linear_quantiles"]
        physical_rows.append(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{html.escape(item['role'])}</td>"
            f"<td>{stats['shape'][1]} x {stats['shape'][0]}</td>"
            f"<td>{q['50.0']:.5g}</td><td>{q['99.9']:.5g}</td>"
            f"<td>{stats['normalized_gradient_rms']:.5f}</td>"
            "</tr>"
        )
    ratio = report["descriptive_comparison"][
        "physical_to_synthetic_normalized_gradient_rms_ratio"
    ]
    ratio_text = "n/a" if ratio is None else f"{ratio:.3f}"
    page = f"""<!doctype html>
<html lang=\"ko\"><head><meta charset=\"utf-8\"><title>Source-grounded evidence audit</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px;color:#17202a}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd1d1;padding:8px;text-align:left}}th{{background:#eef2f3}}.warn{{background:#fff4d6;padding:14px;border-left:5px solid #d68910}}code{{background:#f3f4f4;padding:2px 5px}}</style></head>
<body><h1>Source-grounded evidence audit</h1>
<p class=\"warn\"><strong>정확도 보고서가 아닙니다.</strong> 실제 scanner-sim HDR 영상과 로컬 합성 영상의 도메인 차이를 탐지하기 위한 기술 통계입니다. 서로 다른 장면이므로 pass/fail 기준으로 사용하지 않습니다.</p>
<h2>실제 물리 스캐너 샘플</h2><table><thead><tr><th>파일</th><th>역할</th><th>해상도</th><th>선형 P50</th><th>선형 P99.9</th><th>정규화 gradient RMS</th></tr></thead><tbody>{''.join(physical_rows)}</tbody></table>
<h2>기술 비교</h2><p>실제 <code>img_40.exr</code> / 합성 <code>pattern_010</code> 정규화 gradient RMS 비: <strong>{ratio_text}</strong></p>
<p>{html.escape(report['descriptive_comparison']['comparison_limit'])}</p>
<h2>출처</h2><ul><li><a href=\"https://openreview.net/forum?id=bNL5VlTfe3p\">NeurIPS 2021 paper</a></li><li><a href=\"https://geometryprocessing.github.io/scanner-sim/\">Dataset page</a> (CC BY 4.0)</li><li><a href=\"source_evidence.json\">전체 JSON과 SHA-256</a></li></ul></body></html>"""
    html_path = output / "source_evidence.html"
    html_path.write_text(page, encoding="utf-8")
    return html_path, json_path
