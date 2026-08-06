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
    similarity_scale: float | None
    rotation_center_target_xy: list[float] | None
    target_markers: list[DetectedMarker]
    source_markers: list[DetectedMarker]
    expected_rotation_deg: float = 180.0
    deviation_from_expected_deg: float | None = None


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
    expected_rotation_deg: float = 180.0,
) -> AlignmentResult:
    marker_ids = marker_ids or [0, 1, 2, 3]
    return estimate_aruco_transform_from_images(
        Path(input_dir) / image_name,
        Path(input_180_dir) / image_name,
        dictionary_name=dictionary_name,
        marker_ids=marker_ids,
        method=method,
        ransac_threshold_px=ransac_threshold_px,
        expected_rotation_deg=expected_rotation_deg,
    )


def estimate_aruco_transform_from_images(
    target_image_path: Path,
    source_image_path: Path,
    *,
    dictionary_name: str = "DICT_4X4_50",
    marker_ids: list[int] | None = None,
    method: str = "homography",
    ransac_threshold_px: float = 3.0,
    expected_rotation_deg: float = 180.0,
) -> AlignmentResult:
    """Map a rotated image into a 0-degree image using their ArUco markers.

    This accepts two ordinary image paths so a no-pattern prescan can be
    calibrated before the structured-light scan folders exist.
    """
    marker_ids = marker_ids or [0, 1, 2, 3]
    target_image = _load_detection_image(Path(target_image_path))
    source_image = _load_detection_image(Path(source_image_path))
    target_markers = _detect_markers(target_image, dictionary_name)
    source_markers = _detect_markers(source_image, dictionary_name)

    target_by_id = {marker.marker_id: marker for marker in target_markers}
    source_by_id = {marker.marker_id: marker for marker in source_markers}
    marker_ids = _select_marker_ids_for_alignment(
        marker_ids,
        target_by_id,
        source_by_id,
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
    rotation_deg, similarity_scale, rotation_center = _similarity_rotation_summary(src, dst)
    deviation_deg = None
    deviation_expected = None
    if rotation_deg is not None:
        deviation_deg = abs(abs(rotation_deg) - 180.0)
        deviation_expected = _rotation_magnitude_deviation(rotation_deg, expected_rotation_deg)

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
        similarity_scale=similarity_scale,
        rotation_center_target_xy=rotation_center,
        target_markers=[target_by_id[marker_id] for marker_id in marker_ids],
        source_markers=[source_by_id[marker_id] for marker_id in marker_ids],
        expected_rotation_deg=float(expected_rotation_deg),
        deviation_from_expected_deg=deviation_expected,
    )


def estimate_stage_cross_transform_from_images(
    target_image_path: Path,
    source_image_path: Path,
    *,
    dictionary_name: str = "DICT_4X4_50",
    marker_ids: list[int] | None = None,
    marker_center_radius_mm: float = 25.0,
    marker_black_square_mm: float = 11.4,
    expected_rotation_deg: float = 180.0,
    ransac_threshold_px: float = 3.0,
) -> AlignmentResult:
    """Map one rotated stage view to the zero-degree view via board coordinates.

    Unlike direct ID-to-ID alignment, the two images do not need to expose the
    same marker IDs.  Each image independently estimates a homography from the
    known top/right/bottom/left stage-cross layout, then the homographies are
    composed into a source-to-target transform.
    """
    marker_ids = marker_ids or [0, 1, 2, 3]
    if len(marker_ids) != 4:
        raise ValueError("stage-cross registration requires four marker IDs")
    if marker_center_radius_mm <= 0 or marker_black_square_mm <= 0:
        raise ValueError("stage-cross marker radius and black-square size must be positive")

    target_image = _load_detection_image(Path(target_image_path))
    source_image = _load_detection_image(Path(source_image_path))
    target_markers = _detect_markers(target_image, dictionary_name)
    source_markers = _detect_markers(source_image, dictionary_name)
    target_by_id = {marker.marker_id: marker for marker in target_markers}
    source_by_id = {marker.marker_id: marker for marker in source_markers}

    target_object, target_image_points, target_used = _stage_cross_correspondences(
        marker_ids,
        target_by_id,
        marker_center_radius_mm=marker_center_radius_mm,
        marker_black_square_mm=marker_black_square_mm,
    )
    source_object, source_image_points, source_used = _stage_cross_correspondences(
        marker_ids,
        source_by_id,
        marker_center_radius_mm=marker_center_radius_mm,
        marker_black_square_mm=marker_black_square_mm,
    )
    if len(target_used) < 2 or len(source_used) < 2:
        raise ValueError(
            "stage-cross registration requires at least two visible markers in each view; "
            f"target has {target_used}, source has {source_used}"
        )

    cv2 = _load_cv2()
    target_h, target_inliers = cv2.findHomography(
        target_object,
        target_image_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=float(ransac_threshold_px),
    )
    source_h, source_inliers = cv2.findHomography(
        source_object,
        source_image_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=float(ransac_threshold_px),
    )
    if target_h is None or source_h is None:
        raise ValueError("Could not estimate stage-cross homography from visible markers")
    try:
        matrix = target_h @ np.linalg.inv(source_h)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Stage-cross source homography is singular") from exc
    matrix = matrix / matrix[2, 2]

    target_mask = _normalize_inlier_mask(target_inliers, point_count=target_object.shape[0])
    source_mask = _normalize_inlier_mask(source_inliers, point_count=source_object.shape[0])
    errors = np.concatenate(
        [
            _point_distances(_project_points(target_object, target_h, "homography"), target_image_points),
            _point_distances(_project_points(source_object, source_h, "homography"), source_image_points),
        ]
    )
    inlier_mask = np.concatenate([target_mask, source_mask])
    rmse = float(np.sqrt(np.mean(errors * errors)))
    inlier_rmse = float(np.sqrt(np.mean(errors[inlier_mask] * errors[inlier_mask])))

    layout_centers = _stage_cross_layout_centers(marker_ids, marker_center_radius_mm)
    source_centers = _project_points(layout_centers, source_h, "homography")
    target_centers = _project_points(layout_centers, target_h, "homography")
    rotation_deg, similarity_scale, rotation_center = _similarity_rotation_summary(
        source_centers,
        target_centers,
    )
    deviation_expected = (
        _rotation_magnitude_deviation(rotation_deg, float(expected_rotation_deg))
        if rotation_deg is not None
        else None
    )
    deviation_180 = (
        _angular_distance_degrees(rotation_deg, -180.0)
        if rotation_deg is not None
        else None
    )
    used_ids = sorted(set(target_used) | set(source_used))
    return AlignmentResult(
        matrix=np.asarray(matrix, dtype=float).tolist(),
        transform_kind="homography",
        reprojection_rmse_px=rmse,
        inlier_reprojection_rmse_px=inlier_rmse,
        max_reprojection_error_px=float(np.max(errors)),
        point_count=int(errors.size),
        inlier_count=int(np.count_nonzero(inlier_mask)),
        marker_ids=used_ids,
        rotation_source_to_target_deg=rotation_deg,
        deviation_from_180_deg=deviation_180,
        similarity_scale=similarity_scale,
        rotation_center_target_xy=rotation_center,
        target_markers=[target_by_id[marker_id] for marker_id in target_used],
        source_markers=[source_by_id[marker_id] for marker_id in source_used],
        expected_rotation_deg=float(expected_rotation_deg),
        deviation_from_expected_deg=deviation_expected,
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
    target_angle_deg: float = 0.0,
    source_angle_deg: float = 180.0,
) -> None:
    key = "homography" if result.transform_kind == "homography" else "affine"
    payload: dict[str, Any] = {
        key: result.matrix,
        "matrix": result.matrix,
        "transform_kind": result.transform_kind,
        "source": {
            "role": f"{source_angle_deg:g}-degree",
            "input_dir": str(input_180_dir),
            "image": image_name,
        },
        "target": {
            "role": f"{target_angle_deg:g}-degree",
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
            "expected_rotation_deg": result.expected_rotation_deg,
            "deviation_from_expected_deg": result.deviation_from_expected_deg,
            "similarity_scale": result.similarity_scale,
            "rotation_center_target_xy": result.rotation_center_target_xy,
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
    buffer = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_UNCHANGED)
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


def _stage_cross_layout_centers(marker_ids: list[int], radius_mm: float) -> np.ndarray:
    positions = (
        (0.0, -radius_mm),
        (radius_mm, 0.0),
        (0.0, radius_mm),
        (-radius_mm, 0.0),
    )
    return np.asarray(positions[: len(marker_ids)], dtype=np.float32)


def _stage_cross_correspondences(
    requested_ids: list[int],
    detected_by_id: dict[int, DetectedMarker],
    *,
    marker_center_radius_mm: float,
    marker_black_square_mm: float,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    centers = _stage_cross_layout_centers(requested_ids, marker_center_radius_mm)
    half = 0.5 * float(marker_black_square_mm)
    local_corners = np.asarray(
        [(-half, -half), (half, -half), (half, half), (-half, half)],
        dtype=np.float32,
    )
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    used_ids: list[int] = []
    for index, marker_id in enumerate(requested_ids):
        marker = detected_by_id.get(marker_id)
        if marker is None:
            continue
        object_points.append(local_corners + centers[index])
        image_points.append(np.asarray(marker.corners, dtype=np.float32))
        used_ids.append(marker_id)
    if not object_points:
        return (
            np.empty((0, 2), dtype=np.float32),
            np.empty((0, 2), dtype=np.float32),
            used_ids,
        )
    return np.concatenate(object_points), np.concatenate(image_points), used_ids


def _point_distances(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    delta = np.asarray(first, dtype=np.float32) - np.asarray(second, dtype=np.float32)
    return np.sqrt(np.sum(delta * delta, axis=1))


def _select_marker_ids_for_alignment(
    requested_ids: list[int],
    target_by_id: dict[int, DetectedMarker],
    source_by_id: dict[int, DetectedMarker],
) -> list[int]:
    """Use all visible markers, or one opposite pair when the camera crops two.

    The requested four IDs are ordered around the stage.  Thus [0, 1, 2, 3]
    represents opposite pairs (0, 2) and (1, 3); a [1, 2, 3, 4] layout uses
    (1, 3) and (2, 4).  Both views must expose the same selected pair.
    """
    common = {
        marker_id
        for marker_id in requested_ids
        if marker_id in target_by_id and marker_id in source_by_id
    }
    if all(marker_id in common for marker_id in requested_ids):
        return requested_ids

    if len(requested_ids) == 4:
        candidates = ([requested_ids[0], requested_ids[2]], [requested_ids[1], requested_ids[3]])
    else:
        candidates = [requested_ids[index : index + 2] for index in range(len(requested_ids) - 1)]
    for candidate in candidates:
        if all(marker_id in common for marker_id in candidate):
            return candidate

    missing_target = [marker_id for marker_id in requested_ids if marker_id not in target_by_id]
    missing_source = [marker_id for marker_id in requested_ids if marker_id not in source_by_id]
    pairs = (
        f"{requested_ids[0]},{requested_ids[2]} or {requested_ids[1]},{requested_ids[3]}"
        if len(requested_ids) == 4
        else "at least one common marker pair"
    )
    raise ValueError(
        "ArUco alignment requires all requested markers or the same opposite pair in both views. "
        f"Expected {pairs}; missing in 0-degree={missing_target}, "
        f"missing in rotated={missing_source}"
    )


def _similarity_rotation_summary(
    source_points: np.ndarray,
    target_points: np.ndarray,
) -> tuple[float | None, float | None, list[float] | None]:
    """Estimate the rigid stage-rotation summary independently of the warp."""
    if source_points.shape[0] < 2:
        return None, None, None

    src = np.asarray(source_points, dtype=np.float64)
    dst = np.asarray(target_points, dtype=np.float64)
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_centered = src - src_mean
    dst_centered = dst - dst_mean
    source_energy = float(np.sum(src_centered * src_centered))
    if source_energy <= np.finfo(float).eps:
        return None, None, None

    covariance = src_centered.T @ dst_centered
    u, _singular_values, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T

    transformed_source = src_centered @ rotation.T
    scale = float(np.sum(transformed_source * dst_centered) / source_energy)
    translation = dst_mean - scale * (rotation @ src_mean)
    rotation_deg = _normalize_degrees(
        math.degrees(math.atan2(float(rotation[1, 0]), float(rotation[0, 0])))
    )

    # For dst = s R src + t, the fixed point c satisfies (I - s R)c = t.
    fixed_point_matrix = np.eye(2) - scale * rotation
    if abs(float(np.linalg.det(fixed_point_matrix))) < 1e-8:
        center = None
    else:
        center_array = np.linalg.solve(fixed_point_matrix, translation)
        center = [float(center_array[0]), float(center_array[1])]
    return rotation_deg, scale, center


def _normalize_degrees(angle: float) -> float:
    while angle <= -180.0:
        angle += 360.0
    while angle > 180.0:
        angle -= 360.0
    return angle


def _angular_distance_degrees(first: float, second: float) -> float:
    return abs(_normalize_degrees(float(first) - float(second)))


def _rotation_magnitude_deviation(measured: float, expected: float) -> float:
    measured_magnitude = abs(_normalize_degrees(float(measured)))
    expected_magnitude = abs(_normalize_degrees(float(expected)))
    return abs(measured_magnitude - expected_magnitude)


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
