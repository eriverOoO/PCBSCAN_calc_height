from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .aruco_alignment import (
    DetectedMarker,
    _detect_markers,
    _load_cv2,
    _load_detection_image,
)


@dataclass(frozen=True)
class AnalysisRoiResult:
    mask: np.ndarray
    marker_space_mask: np.ndarray
    pcb_mask: np.ndarray | None
    marker_ids: tuple[int, ...]
    ordered_marker_ids: tuple[int, ...]
    marker_space_corners: list[list[float]]
    bounding_box_xywh: tuple[int, int, int, int]
    report: dict[str, Any]


def estimate_aruco_analysis_roi(
    input_dir: Path,
    shape: tuple[int, int],
    *,
    dictionary_name: str = "DICT_4X4_50",
    marker_ids: Sequence[int] = (0, 1, 2, 3),
    image_name: str = "pattern_000.png",
    workspace_width_mm: float | None = None,
    workspace_height_mm: float | None = None,
    pcb_width_mm: float | None = None,
    pcb_height_mm: float | None = None,
    pcb_margin_mm: float = 0.0,
) -> AnalysisRoiResult:
    marker_ids = tuple(int(marker_id) for marker_id in marker_ids)
    pcb_margin_mm = float(pcb_margin_mm)
    _validate_roi_inputs(
        marker_ids,
        workspace_width_mm,
        workspace_height_mm,
        pcb_width_mm,
        pcb_height_mm,
        pcb_margin_mm,
    )

    image_path = Path(input_dir) / image_name
    image = _load_detection_image(image_path)
    if image.shape != shape:
        raise ValueError(
            f"ArUco analysis image shape {image.shape} does not match scan shape {shape}: "
            f"{image_path}"
        )

    detected = _detect_markers(image, dictionary_name)
    detected_by_id = {marker.marker_id: marker for marker in detected}
    missing = [marker_id for marker_id in marker_ids if marker_id not in detected_by_id]
    if missing:
        raise ValueError(
            "Requested ArUco analysis ROI markers were not detected: "
            f"{missing}. Detected ids: {sorted(detected_by_id)}"
        )

    requested_markers = [detected_by_id[marker_id] for marker_id in marker_ids]
    ordered_markers = _order_markers_by_center(requested_markers)
    center = np.mean([marker.center for marker in ordered_markers], axis=0)
    inner_corners = np.asarray(
        [_corner_closest_to(marker, center) for marker in ordered_markers],
        dtype=np.float32,
    )
    marker_space_corners = _order_points_tl_tr_br_bl(inner_corners)

    marker_space_mask = _polygon_mask(shape, marker_space_corners)
    pcb_mask: np.ndarray | None = None
    analysis_mask = marker_space_mask
    workspace_homography: np.ndarray | None = None
    if workspace_width_mm is not None and workspace_height_mm is not None:
        workspace_mask, workspace_homography = _workspace_mask_from_homography(
            shape,
            marker_space_corners,
            float(workspace_width_mm),
            float(workspace_height_mm),
        )
        analysis_mask = workspace_mask
        if pcb_width_mm is not None and pcb_height_mm is not None:
            effective_pcb_width_mm = min(
                float(workspace_width_mm),
                float(pcb_width_mm) + 2.0 * pcb_margin_mm,
            )
            effective_pcb_height_mm = min(
                float(workspace_height_mm),
                float(pcb_height_mm) + 2.0 * pcb_margin_mm,
            )
            pcb_mask = _centered_pcb_mask_from_homography(
                shape,
                workspace_homography,
                float(workspace_width_mm),
                float(workspace_height_mm),
                effective_pcb_width_mm,
                effective_pcb_height_mm,
            )
            analysis_mask = pcb_mask

    analysis_mask = analysis_mask & marker_space_mask
    bbox = _mask_bounding_box(marker_space_mask)
    report = _build_report(
        shape,
        input_dir=Path(input_dir),
        image_name=image_name,
        dictionary_name=dictionary_name,
        requested_marker_ids=marker_ids,
        ordered_markers=ordered_markers,
        marker_space_corners=marker_space_corners,
        marker_space_mask=marker_space_mask,
        analysis_mask=analysis_mask,
        pcb_mask=pcb_mask,
        bounding_box_xywh=bbox,
        workspace_width_mm=workspace_width_mm,
        workspace_height_mm=workspace_height_mm,
        pcb_width_mm=pcb_width_mm,
        pcb_height_mm=pcb_height_mm,
        pcb_margin_mm=pcb_margin_mm,
        workspace_homography=workspace_homography,
    )

    return AnalysisRoiResult(
        mask=analysis_mask.astype(bool),
        marker_space_mask=marker_space_mask.astype(bool),
        pcb_mask=pcb_mask.astype(bool) if pcb_mask is not None else None,
        marker_ids=marker_ids,
        ordered_marker_ids=tuple(marker.marker_id for marker in ordered_markers),
        marker_space_corners=marker_space_corners.astype(float).tolist(),
        bounding_box_xywh=bbox,
        report=report,
    )


def _validate_roi_inputs(
    marker_ids: tuple[int, ...],
    workspace_width_mm: float | None,
    workspace_height_mm: float | None,
    pcb_width_mm: float | None,
    pcb_height_mm: float | None,
    pcb_margin_mm: float,
) -> None:
    if len(marker_ids) != 4:
        raise ValueError("ArUco analysis ROI requires exactly four marker IDs")
    if len(set(marker_ids)) != len(marker_ids):
        raise ValueError("ArUco analysis ROI marker IDs must be unique")

    _validate_size_pair("analysis workspace", workspace_width_mm, workspace_height_mm)
    _validate_size_pair("PCB", pcb_width_mm, pcb_height_mm)
    if pcb_margin_mm < 0:
        raise ValueError("PCB margin must be zero or positive")

    pcb_size_given = pcb_width_mm is not None or pcb_height_mm is not None
    workspace_size_given = workspace_width_mm is not None or workspace_height_mm is not None
    if pcb_size_given and not workspace_size_given:
        raise ValueError(
            "PCB size in mm requires analysis workspace width/height in mm so pixels "
            "can be mapped to physical size"
        )
    if (
        pcb_width_mm is not None
        and pcb_height_mm is not None
        and workspace_width_mm is not None
        and workspace_height_mm is not None
    ):
        if pcb_width_mm > workspace_width_mm or pcb_height_mm > workspace_height_mm:
            raise ValueError("PCB size must not exceed the ArUco marker-space workspace size")


def _validate_size_pair(name: str, width_mm: float | None, height_mm: float | None) -> None:
    if (width_mm is None) != (height_mm is None):
        raise ValueError(f"{name} width and height must be provided together")
    if width_mm is None or height_mm is None:
        return
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError(f"{name} width and height must be positive")


def _order_markers_by_center(markers: Sequence[DetectedMarker]) -> list[DetectedMarker]:
    centers = np.asarray([marker.center for marker in markers], dtype=np.float32)
    order = _point_order_indices_tl_tr_br_bl(centers)
    return [markers[index] for index in order]


def _corner_closest_to(marker: DetectedMarker, point: np.ndarray) -> np.ndarray:
    corners = np.asarray(marker.corners, dtype=np.float32)
    distances = np.sum((corners - point.astype(np.float32)) ** 2, axis=1)
    return corners[int(np.argmin(distances))]


def _order_points_tl_tr_br_bl(points: np.ndarray) -> np.ndarray:
    order = _point_order_indices_tl_tr_br_bl(np.asarray(points, dtype=np.float32))
    return np.asarray(points, dtype=np.float32)[order]


def _point_order_indices_tl_tr_br_bl(points: np.ndarray) -> list[int]:
    if points.shape != (4, 2):
        raise ValueError("Exactly four points are required")
    sums = points[:, 0] + points[:, 1]
    diffs = points[:, 0] - points[:, 1]
    order = [
        int(np.argmin(sums)),
        int(np.argmax(diffs)),
        int(np.argmax(sums)),
        int(np.argmin(diffs)),
    ]
    if len(set(order)) == 4:
        return order

    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ccw_order = list(np.argsort(angles))
    start = min(ccw_order, key=lambda index: points[index, 0] + points[index, 1])
    start_pos = ccw_order.index(start)
    return ccw_order[start_pos:] + ccw_order[:start_pos]


def _polygon_mask(shape: tuple[int, int], points: np.ndarray) -> np.ndarray:
    cv2 = _load_cv2()
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.round(points).astype(np.int32), 1)
    return mask.astype(bool)


def _workspace_mask_from_homography(
    shape: tuple[int, int],
    source_points: np.ndarray,
    workspace_width_mm: float,
    workspace_height_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    cv2 = _load_cv2()
    destination = np.asarray(
        [
            [0.0, 0.0],
            [workspace_width_mm, 0.0],
            [workspace_width_mm, workspace_height_mm],
            [0.0, workspace_height_mm],
        ],
        dtype=np.float32,
    )
    homography = cv2.getPerspectiveTransform(source_points.astype(np.float32), destination)
    workspace_x, workspace_y = _project_grid(shape, homography)
    mask = (
        np.isfinite(workspace_x)
        & np.isfinite(workspace_y)
        & (workspace_x >= 0.0)
        & (workspace_x <= workspace_width_mm)
        & (workspace_y >= 0.0)
        & (workspace_y <= workspace_height_mm)
    )
    return mask.astype(bool), homography.astype(np.float32)


def _centered_pcb_mask_from_homography(
    shape: tuple[int, int],
    homography: np.ndarray,
    workspace_width_mm: float,
    workspace_height_mm: float,
    pcb_width_mm: float,
    pcb_height_mm: float,
) -> np.ndarray:
    workspace_x, workspace_y = _project_grid(shape, homography)
    x0 = 0.5 * (workspace_width_mm - pcb_width_mm)
    x1 = x0 + pcb_width_mm
    y0 = 0.5 * (workspace_height_mm - pcb_height_mm)
    y1 = y0 + pcb_height_mm
    return (
        np.isfinite(workspace_x)
        & np.isfinite(workspace_y)
        & (workspace_x >= x0)
        & (workspace_x <= x1)
        & (workspace_y >= y0)
        & (workspace_y <= y1)
    ).astype(bool)


def _project_grid(shape: tuple[int, int], homography: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = np.indices(shape, dtype=np.float32)
    x = cols + 0.5
    y = rows + 0.5
    denom = homography[2, 0] * x + homography[2, 1] * y + homography[2, 2]
    valid = np.abs(denom) > 1e-8
    workspace_x = np.divide(
        homography[0, 0] * x + homography[0, 1] * y + homography[0, 2],
        denom,
        out=np.full(shape, np.nan, dtype=np.float32),
        where=valid,
    )
    workspace_y = np.divide(
        homography[1, 0] * x + homography[1, 1] * y + homography[1, 2],
        denom,
        out=np.full(shape, np.nan, dtype=np.float32),
        where=valid,
    )
    return workspace_x.astype(np.float32), workspace_y.astype(np.float32)


def _mask_bounding_box(mask: np.ndarray) -> tuple[int, int, int, int]:
    rows, cols = np.nonzero(mask)
    if rows.size == 0 or cols.size == 0:
        return (0, 0, 0, 0)
    x0 = int(cols.min())
    x1 = int(cols.max())
    y0 = int(rows.min())
    y1 = int(rows.max())
    return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def _build_report(
    shape: tuple[int, int],
    *,
    input_dir: Path,
    image_name: str,
    dictionary_name: str,
    requested_marker_ids: tuple[int, ...],
    ordered_markers: Sequence[DetectedMarker],
    marker_space_corners: np.ndarray,
    marker_space_mask: np.ndarray,
    analysis_mask: np.ndarray,
    pcb_mask: np.ndarray | None,
    bounding_box_xywh: tuple[int, int, int, int],
    workspace_width_mm: float | None,
    workspace_height_mm: float | None,
    pcb_width_mm: float | None,
    pcb_height_mm: float | None,
    pcb_margin_mm: float,
    workspace_homography: np.ndarray | None,
) -> dict[str, Any]:
    total = int(np.prod(shape))
    return {
        "enabled": True,
        "mode": "aruco",
        "input_dir": str(input_dir),
        "image": image_name,
        "dictionary": dictionary_name,
        "requested_marker_ids": list(requested_marker_ids),
        "ordered_marker_ids_tl_tr_br_bl": [marker.marker_id for marker in ordered_markers],
        "marker_space_corners_tl_tr_br_bl": marker_space_corners.astype(float).tolist(),
        "bounding_box_xywh": list(bounding_box_xywh),
        "workspace_size_mm": (
            {
                "width": float(workspace_width_mm),
                "height": float(workspace_height_mm),
            }
            if workspace_width_mm is not None and workspace_height_mm is not None
            else None
        ),
        "pcb_size_mm": (
            {
                "width": float(pcb_width_mm),
                "height": float(pcb_height_mm),
                "margin": float(pcb_margin_mm),
                "effective_width": float(
                    min(float(workspace_width_mm), float(pcb_width_mm) + 2.0 * pcb_margin_mm)
                )
                if workspace_width_mm is not None
                else None,
                "effective_height": float(
                    min(float(workspace_height_mm), float(pcb_height_mm) + 2.0 * pcb_margin_mm)
                )
                if workspace_height_mm is not None
                else None,
                "assumed_centered": True,
            }
            if pcb_width_mm is not None and pcb_height_mm is not None
            else None
        ),
        "workspace_homography_pixel_to_mm": (
            workspace_homography.astype(float).tolist()
            if workspace_homography is not None
            else None
        ),
        "marker_space_mask_ratio": float(np.count_nonzero(marker_space_mask) / total),
        "analysis_mask_ratio": float(np.count_nonzero(analysis_mask) / total),
        "pcb_mask_ratio": (
            float(np.count_nonzero(pcb_mask) / total) if pcb_mask is not None else None
        ),
        "markers": [asdict(marker) for marker in ordered_markers],
    }
