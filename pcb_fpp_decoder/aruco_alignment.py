from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


ARUCO_DICTIONARIES = {
    "DICT_4X4_50": "DICT_4X4_50",
    "DICT_4X4_100": "DICT_4X4_100",
    "DICT_4X4_250": "DICT_4X4_250",
    "DICT_4X4_1000": "DICT_4X4_1000",
    "DICT_5X5_50": "DICT_5X5_50",
    "DICT_5X5_100": "DICT_5X5_100",
    "DICT_5X5_250": "DICT_5X5_250",
    "DICT_5X5_1000": "DICT_5X5_1000",
    "DICT_6X6_50": "DICT_6X6_50",
    "DICT_6X6_100": "DICT_6X6_100",
    "DICT_6X6_250": "DICT_6X6_250",
    "DICT_6X6_1000": "DICT_6X6_1000",
    "DICT_7X7_50": "DICT_7X7_50",
    "DICT_7X7_100": "DICT_7X7_100",
    "DICT_7X7_250": "DICT_7X7_250",
    "DICT_7X7_1000": "DICT_7X7_1000",
    "DICT_ARUCO_ORIGINAL": "DICT_ARUCO_ORIGINAL",
}


@dataclass(frozen=True)
class DetectedMarker:
    marker_id: int
    center: list[float]
    corners: list[list[float]]


@dataclass(frozen=True)
class AlignmentResult:
    matrix: list[list[float]]
    transform_kind: str
    reprojection_rmse_px: float
    inlier_reprojection_rmse_px: float
    max_reprojection_error_px: float
    point_count: int
    inlier_count: int
    marker_ids: list[int]
    rotation_source_to_target_deg: float | None
    deviation_from_180_deg: float | None
    target_markers: list[DetectedMarker]
    source_markers: list[DetectedMarker]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate a fusion transform from ArUco markers in 0-degree and "
            "rotated scan folders."
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
        default=Path("aruco_fusion_transform.json"),
        help="Output JSON transform path",
    )
    parser.add_argument(
        "--dictionary",
        default="DICT_4X4_50",
        choices=sorted(ARUCO_DICTIONARIES),
        help="OpenCV ArUco dictionary",
    )
    parser.add_argument(
        "--ids",
        default="0,1,2,3",
        help="Marker IDs to use, for example 0,1,2,3",
    )
    parser.add_argument(
        "--image",
        default="pattern_000.png",
        help="Image file inside each scan folder used for marker detection",
    )
    parser.add_argument(
        "--method",
        choices=("homography", "affine"),
        default="homography",
        help="Transform model to estimate from marker corners",
    )
    parser.add_argument(
        "--ransac-threshold-px",
        type=float,
        default=3.0,
        help="RANSAC reprojection threshold in pixels for robust marker fitting",
    )
    return parser


def parse_marker_ids(value: str) -> list[int]:
    ids = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not ids:
        raise ValueError("At least one marker id is required")
    return ids


def estimate_aruco_transform(
    input_dir: Path,
    input_180_dir: Path,
    *,
    dictionary_name: str = "DICT_4X4_50",
    marker_ids: list[int] | None = None,
    image_name: str = "pattern_000.png",
    method: str = "homography",
    ransac_threshold_px: float = 3.0,
) -> AlignmentResult:
    marker_ids = marker_ids or [0, 1, 2, 3]
    target_image = _load_detection_image(input_dir / image_name)
    source_image = _load_detection_image(input_180_dir / image_name)
    target_markers = _detect_markers(target_image, dictionary_name)
    source_markers = _detect_markers(source_image, dictionary_name)

    target_by_id = {marker.marker_id: marker for marker in target_markers}
    source_by_id = {marker.marker_id: marker for marker in source_markers}
    missing_target = [marker_id for marker_id in marker_ids if marker_id not in target_by_id]
    missing_source = [marker_id for marker_id in marker_ids if marker_id not in source_by_id]
    if missing_target or missing_source:
        raise ValueError(
            "Requested ArUco markers were not detected. "
            f"missing in 0-degree={missing_target}, missing in rotated={missing_source}"
        )

    source_points: list[list[float]] = []
    target_points: list[list[float]] = []
    for marker_id in marker_ids:
        source_points.extend(source_by_id[marker_id].corners)
        target_points.extend(target_by_id[marker_id].corners)

    src = np.asarray(source_points, dtype=np.float32)
    dst = np.asarray(target_points, dtype=np.float32)

    cv2 = _load_cv2()
    if method == "homography":
        matrix, inliers = cv2.findHomography(
            src,
            dst,
            method=cv2.RANSAC,
            ransacReprojThreshold=float(ransac_threshold_px),
        )
        if matrix is None:
            raise ValueError("Could not estimate homography from detected markers")
        transform_kind = "homography"
    else:
        matrix, inliers = cv2.estimateAffinePartial2D(
            src,
            dst,
            method=cv2.RANSAC,
            ransacReprojThreshold=float(ransac_threshold_px),
        )
        if matrix is None:
            raise ValueError("Could not estimate affine transform from detected markers")
        transform_kind = "affine"

    inlier_mask = _normalize_inlier_mask(inliers, point_count=src.shape[0])
    rmse, inlier_rmse, max_error = _reprojection_stats(
        src,
        dst,
        matrix,
        transform_kind,
        inlier_mask,
    )
    rotation_deg = _center_vector_rotation_deg(source_by_id, target_by_id, marker_ids)
    deviation_deg = None
    if rotation_deg is not None:
        deviation_deg = abs(abs(rotation_deg) - 180.0)

    return AlignmentResult(
        matrix=np.asarray(matrix, dtype=float).tolist(),
        transform_kind=transform_kind,
        reprojection_rmse_px=rmse,
        inlier_reprojection_rmse_px=inlier_rmse,
        max_reprojection_error_px=max_error,
        point_count=int(src.shape[0]),
        inlier_count=int(np.count_nonzero(inlier_mask)),
        marker_ids=marker_ids,
        rotation_source_to_target_deg=rotation_deg,
        deviation_from_180_deg=deviation_deg,
        target_markers=[target_by_id[marker_id] for marker_id in marker_ids],
        source_markers=[source_by_id[marker_id] for marker_id in marker_ids],
    )


def save_alignment_json(
    output_path: Path,
    result: AlignmentResult,
    *,
    input_dir: Path,
    input_180_dir: Path,
    dictionary_name: str,
    image_name: str,
    method: str,
    ransac_threshold_px: float | None = None,
) -> None:
    key = "homography" if result.transform_kind == "homography" else "affine"
    payload: dict[str, Any] = {
        key: result.matrix,
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
        "aruco": {
            "dictionary": dictionary_name,
            "marker_ids": result.marker_ids,
            "method": method,
            "ransac_threshold_px": ransac_threshold_px,
            "reprojection_rmse_px": result.reprojection_rmse_px,
            "inlier_reprojection_rmse_px": result.inlier_reprojection_rmse_px,
            "max_reprojection_error_px": result.max_reprojection_error_px,
            "point_count": result.point_count,
            "inlier_count": result.inlier_count,
            "rotation_source_to_target_deg": result.rotation_source_to_target_deg,
            "deviation_from_180_deg": result.deviation_from_180_deg,
            "target_markers": [asdict(marker) for marker in result.target_markers],
            "source_markers": [asdict(marker) for marker in result.source_markers],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for ArUco alignment") from exc
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("This OpenCV build does not include cv2.aruco")
    return cv2


def _load_detection_image(path: Path) -> np.ndarray:
    cv2 = _load_cv2()
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Could not read marker detection image: {path}")
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return _to_uint8(image)


def _to_uint8(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint8:
        return image
    finite = image[np.isfinite(image)]
    if finite.size == 0:
        return np.zeros(image.shape, dtype=np.uint8)
    low, high = np.percentile(finite, [1.0, 99.0])
    if high <= low:
        high = float(np.max(finite))
        low = float(np.min(finite))
    if high <= low:
        return np.zeros(image.shape, dtype=np.uint8)
    scaled = (image.astype(np.float32) - float(low)) * (255.0 / (float(high) - float(low)))
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _detect_markers(image: np.ndarray, dictionary_name: str) -> list[DetectedMarker]:
    cv2 = _load_cv2()
    aruco = cv2.aruco
    dictionary_id = getattr(aruco, dictionary_name, None)
    if dictionary_id is None:
        raise ValueError(f"Unknown ArUco dictionary: {dictionary_name}")
    if hasattr(aruco, "getPredefinedDictionary"):
        dictionary = aruco.getPredefinedDictionary(dictionary_id)
    else:
        dictionary = aruco.Dictionary_get(dictionary_id)

    if hasattr(aruco, "ArucoDetector"):
        detector = aruco.ArucoDetector(dictionary, aruco.DetectorParameters())
        corners, ids, _rejected = detector.detectMarkers(image)
    else:
        corners, ids, _rejected = aruco.detectMarkers(image, dictionary)
    if ids is None:
        return []

    markers: list[DetectedMarker] = []
    for marker_id, marker_corners in zip(ids.ravel().tolist(), corners):
        pts = marker_corners.reshape(4, 2).astype(float)
        center = pts.mean(axis=0)
        markers.append(
            DetectedMarker(
                marker_id=int(marker_id),
                center=[float(center[0]), float(center[1])],
                corners=[[float(x), float(y)] for x, y in pts.tolist()],
            )
        )
    return sorted(markers, key=lambda marker: marker.marker_id)


def _project_points(
    src: np.ndarray,
    matrix: np.ndarray,
    transform_kind: str,
) -> np.ndarray:
    if transform_kind == "homography":
        ones = np.ones((src.shape[0], 1), dtype=np.float32)
        homogeneous = np.concatenate([src, ones], axis=1) @ matrix.T
        return homogeneous[:, :2] / homogeneous[:, 2:3]
    ones = np.ones((src.shape[0], 1), dtype=np.float32)
    return np.concatenate([src, ones], axis=1) @ matrix.T


def _reprojection_stats(
    src: np.ndarray,
    dst: np.ndarray,
    matrix: np.ndarray,
    transform_kind: str,
    inlier_mask: np.ndarray,
) -> tuple[float, float, float]:
    projected = _project_points(src, matrix, transform_kind)
    error = projected.astype(np.float32) - dst.astype(np.float32)
    distances = np.sqrt(np.sum(error * error, axis=1))
    rmse = float(np.sqrt(np.mean(distances * distances)))
    max_error = float(np.max(distances))
    if np.any(inlier_mask):
        inlier_distances = distances[inlier_mask]
        inlier_rmse = float(np.sqrt(np.mean(inlier_distances * inlier_distances)))
    else:
        inlier_rmse = rmse
    return rmse, inlier_rmse, max_error


def _normalize_inlier_mask(inliers: np.ndarray | None, *, point_count: int) -> np.ndarray:
    if inliers is None:
        return np.ones(point_count, dtype=bool)
    mask = np.asarray(inliers).reshape(-1).astype(bool)
    if mask.shape[0] != point_count:
        return np.ones(point_count, dtype=bool)
    return mask


def _center_vector_rotation_deg(
    source_by_id: dict[int, DetectedMarker],
    target_by_id: dict[int, DetectedMarker],
    marker_ids: list[int],
) -> float | None:
    if len(marker_ids) < 2:
        return None
    first, second = marker_ids[:2]
    source_vector = np.asarray(source_by_id[second].center) - np.asarray(source_by_id[first].center)
    target_vector = np.asarray(target_by_id[second].center) - np.asarray(target_by_id[first].center)
    source_angle = math.degrees(math.atan2(float(source_vector[1]), float(source_vector[0])))
    target_angle = math.degrees(math.atan2(float(target_vector[1]), float(target_vector[0])))
    return _normalize_degrees(target_angle - source_angle)


def _normalize_degrees(angle: float) -> float:
    while angle <= -180.0:
        angle += 360.0
    while angle > 180.0:
        angle -= 360.0
    return angle


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        marker_ids = parse_marker_ids(args.ids)
        result = estimate_aruco_transform(
            args.input,
            args.input_180,
            dictionary_name=args.dictionary,
            marker_ids=marker_ids,
            image_name=args.image,
            method=args.method,
            ransac_threshold_px=args.ransac_threshold_px,
        )
        save_alignment_json(
            args.output,
            result,
            input_dir=args.input,
            input_180_dir=args.input_180,
            dictionary_name=args.dictionary,
            image_name=args.image,
            method=args.method,
            ransac_threshold_px=args.ransac_threshold_px,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))

    print(f"Saved fusion transform: {args.output}")
    print(f"Transform kind: {result.transform_kind}")
    print(
        "Reprojection RMSE: "
        f"{result.reprojection_rmse_px:.3f} px "
        f"(inlier {result.inlier_reprojection_rmse_px:.3f} px, "
        f"{result.inlier_count}/{result.point_count} inliers)"
    )
    if result.rotation_source_to_target_deg is not None:
        print(f"Source->target rotation: {result.rotation_source_to_target_deg:.4f} deg")
        print(f"Deviation from 180 deg: {result.deviation_from_180_deg:.4f} deg")
    return 0
