from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PhaseCorrelationAlignmentResult:
    matrix: list[list[float]]
    transform_kind: str
    residual_shift_xy: list[float]
    response: float
    rotation_center_xy: list[float]
    image_shape: list[int]
    initial_matrix: list[list[float]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate a 0/180 fusion transform by applying the nominal 180-degree "
            "rotation first, then refining residual x/y translation with phase "
            "correlation."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="0-degree scan folder")
    parser.add_argument(
        "--input-180",
        required=True,
        type=Path,
        help="Rotated scan folder to map into --input coordinates",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("phase_correlation_fusion_transform.json"),
        help="Output JSON transform path",
    )
    parser.add_argument(
        "--image",
        default="pattern_000.png",
        help="Image file inside each scan folder used for phase correlation",
    )
    parser.add_argument(
        "--fusion-center",
        nargs=2,
        type=float,
        metavar=("X", "Y"),
        help="Rotation center in pixels for the initial 180-degree alignment",
    )
    parser.add_argument(
        "--no-hann",
        action="store_true",
        help="Disable Hanning windowing before phase correlation",
    )
    parser.add_argument(
        "--min-response",
        type=float,
        default=0.0,
        help="Fail if the phase-correlation response is below this value",
    )
    return parser


def estimate_phase_correlation_transform(
    input_dir: Path,
    input_180_dir: Path,
    *,
    image_name: str = "pattern_000.png",
    fusion_center: tuple[float, float] | None = None,
    use_hann_window: bool = True,
    min_response: float = 0.0,
) -> PhaseCorrelationAlignmentResult:
    target_image = _load_detection_image(Path(input_dir) / image_name)
    source_image = _load_detection_image(Path(input_180_dir) / image_name)
    if target_image.shape != source_image.shape:
        raise ValueError(
            "phase-correlation alignment requires equal image shapes; "
            "use ArUco/homography alignment for resized or perspective-shifted scans"
        )

    height, width = target_image.shape
    center = _rotation_center((height, width), fusion_center)
    initial_matrix = _rotation_180_matrix(center)
    initially_aligned = _warp_affine(source_image, target_image.shape, initial_matrix)

    source_corr = _normalize_for_phase_correlation(initially_aligned)
    target_corr = _normalize_for_phase_correlation(target_image)

    cv2 = _load_cv2()
    window = None
    if use_hann_window:
        window = cv2.createHanningWindow((width, height), cv2.CV_32F)
    shift_xy, response = cv2.phaseCorrelate(source_corr, target_corr, window)
    shift_x = float(shift_xy[0])
    shift_y = float(shift_xy[1])
    response = float(response)
    if not np.isfinite(shift_x) or not np.isfinite(shift_y) or not np.isfinite(response):
        raise ValueError("phase correlation failed to produce a finite transform")
    if response < min_response:
        raise ValueError(
            f"phase-correlation response {response:.4f} is below "
            f"--min-response {min_response:.4f}"
        )

    matrix = initial_matrix.copy()
    matrix[0, 2] += shift_x
    matrix[1, 2] += shift_y

    return PhaseCorrelationAlignmentResult(
        matrix=np.asarray(matrix, dtype=float).tolist(),
        transform_kind="affine",
        residual_shift_xy=[shift_x, shift_y],
        response=response,
        rotation_center_xy=[float(center[0]), float(center[1])],
        image_shape=[int(height), int(width)],
        initial_matrix=np.asarray(initial_matrix, dtype=float).tolist(),
    )


def save_alignment_json(
    output_path: Path,
    result: PhaseCorrelationAlignmentResult,
    *,
    input_dir: Path,
    input_180_dir: Path,
    image_name: str,
    use_hann_window: bool,
) -> None:
    payload: dict[str, Any] = {
        "affine": result.matrix,
        "matrix": result.matrix,
        "transform_kind": result.transform_kind,
        "source": {
            "role": "rotated",
            "input_dir": str(input_180_dir),
            "image": image_name,
        },
        "target": {
            "role": "0-degree",
            "input_dir": str(input_dir),
            "image": image_name,
        },
        "phase_correlation": {
            **asdict(result),
            "window": "hann" if use_hann_window else "none",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for phase-correlation alignment") from exc
    return cv2


def _load_detection_image(path: Path) -> np.ndarray:
    cv2 = _load_cv2()
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Could not read phase-correlation image: {path}")
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return _to_float32(image)


def _to_float32(image: np.ndarray) -> np.ndarray:
    image = np.asarray(image, dtype=np.float32)
    return np.where(np.isfinite(image), image, 0.0).astype(np.float32)


def _normalize_for_phase_correlation(image: np.ndarray) -> np.ndarray:
    image = _to_float32(image)
    finite = image[np.isfinite(image)]
    if finite.size == 0:
        raise ValueError("phase-correlation image has no finite pixels")
    low, high = np.percentile(finite, [1.0, 99.0])
    if high <= low:
        low = float(np.min(finite))
        high = float(np.max(finite))
    if high <= low:
        raise ValueError(
            "phase-correlation image has no usable contrast; choose a textured frame"
        )
    normalized = np.clip((image - low) / (high - low), 0.0, 1.0).astype(np.float32)
    normalized -= float(np.mean(normalized))
    return normalized.astype(np.float32)


def _rotation_center(
    shape: tuple[int, int],
    fusion_center: tuple[float, float] | None,
) -> tuple[float, float]:
    height, width = shape
    if fusion_center is not None:
        return float(fusion_center[0]), float(fusion_center[1])
    return (width - 1) / 2.0, (height - 1) / 2.0


def _rotation_180_matrix(center: tuple[float, float]) -> np.ndarray:
    cx, cy = center
    return np.array([[-1.0, 0.0, 2.0 * cx], [0.0, -1.0, 2.0 * cy]], dtype=np.float32)


def _warp_affine(
    image: np.ndarray,
    target_shape: tuple[int, int],
    matrix: np.ndarray,
) -> np.ndarray:
    cv2 = _load_cv2()
    height, width = target_shape
    return cv2.warpAffine(
        image.astype(np.float32),
        matrix.astype(np.float32),
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    ).astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = estimate_phase_correlation_transform(
            args.input,
            args.input_180,
            image_name=args.image,
            fusion_center=tuple(args.fusion_center) if args.fusion_center else None,
            use_hann_window=not args.no_hann,
            min_response=args.min_response,
        )
        save_alignment_json(
            args.output,
            result,
            input_dir=args.input,
            input_180_dir=args.input_180,
            image_name=args.image,
            use_hann_window=not args.no_hann,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    print(f"Saved fusion transform: {args.output}")
    print(f"Transform kind: {result.transform_kind}")
    print(
        "Residual shift: "
        f"dx={result.residual_shift_xy[0]:.4f} px, "
        f"dy={result.residual_shift_xy[1]:.4f} px"
    )
    print(f"Phase-correlation response: {result.response:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
