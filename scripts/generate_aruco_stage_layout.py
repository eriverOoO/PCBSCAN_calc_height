from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, JpegImagePlugin  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pcb_fpp_decoder.aruco_marker import generate_marker_image, mm_to_pixels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a printable circular rotating-stage ArUco marker layout."
    )
    parser.add_argument("--ids", default="0,1,2,3", help="Marker IDs for top,right,bottom,left")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--stage-diameter-mm", type=float, default=105.0)
    parser.add_argument("--marker-radius-mm", type=float, default=42.0)
    parser.add_argument("--marker-total-mm", type=float, default=15.0)
    parser.add_argument("--quiet-zone-mm", type=float, default=1.8)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--output", type=Path, default=Path("aruco_markers_stage_layout"))
    parser.add_argument("--prefix", default="aruco_stage_d105_r42_total15")
    return parser


def parse_ids(text: str) -> list[int]:
    ids = [int(part.strip()) for part in text.split(",") if part.strip()]
    if len(ids) != 4:
        raise ValueError("--ids must contain exactly four marker IDs: top,right,bottom,left")
    return ids


def build_stage_image(
    *,
    marker_ids: list[int],
    dictionary: str,
    stage_diameter_mm: float,
    marker_radius_mm: float,
    marker_total_mm: float,
    quiet_zone_mm: float,
    dpi: int,
) -> tuple[Image.Image, dict[str, object]]:
    marker_size_mm = marker_total_mm - quiet_zone_mm * 2.0
    if marker_size_mm <= 0:
        raise ValueError("--marker-total-mm must be larger than 2 * --quiet-zone-mm")

    stage_px = mm_to_pixels(stage_diameter_mm, dpi)
    radius_px = stage_px / 2.0
    center = (stage_px // 2, stage_px // 2)
    marker_radius_px = mm_to_pixels(marker_radius_mm, dpi)

    stage = Image.new("L", (stage_px, stage_px), 255)
    draw = ImageDraw.Draw(stage)
    draw.ellipse((1, 1, stage_px - 2, stage_px - 2), outline=0, width=max(2, dpi // 150))

    cross = mm_to_pixels(3.0, dpi)
    draw.line((center[0] - cross, center[1], center[0] + cross, center[1]), fill=0, width=1)
    draw.line((center[0], center[1] - cross, center[0], center[1] + cross), fill=0, width=1)

    positions = {
        "top": (center[0], center[1] - marker_radius_px),
        "right": (center[0] + marker_radius_px, center[1]),
        "bottom": (center[0], center[1] + marker_radius_px),
        "left": (center[0] - marker_radius_px, center[1]),
    }
    ordered_positions = ["top", "right", "bottom", "left"]
    marker_records: list[dict[str, object]] = []

    for marker_id, name in zip(marker_ids, ordered_positions):
        marker, _marker_pixels, _quiet_pixels = generate_marker_image(
            marker_id=marker_id,
            dictionary_name=dictionary,
            marker_size_mm=marker_size_mm,
            quiet_zone_mm=quiet_zone_mm,
            dpi=dpi,
            label=False,
        )
        cx, cy = positions[name]
        x = int(round(cx - marker.width / 2.0))
        y = int(round(cy - marker.height / 2.0))
        stage.paste(marker, (x, y))
        marker_records.append(
            {
                "id": marker_id,
                "position": name,
                "center_mm_from_stage_center": _center_mm(name, marker_radius_mm),
                "center_px": [int(cx), int(cy)],
                "box_px": [x, y, x + marker.width, y + marker.height],
            }
        )

    manifest = {
        "dictionary": dictionary,
        "stage_diameter_mm": stage_diameter_mm,
        "marker_center_radius_mm": marker_radius_mm,
        "marker_total_mm": marker_total_mm,
        "marker_black_square_mm": marker_size_mm,
        "quiet_zone_mm": quiet_zone_mm,
        "dpi": dpi,
        "markers": marker_records,
    }
    return stage, manifest


def save_outputs(
    stage: Image.Image,
    manifest: dict[str, object],
    *,
    output: Path,
    prefix: str,
    dpi: int,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    stage_png = output / f"{prefix}_stage.png"
    stage_pdf = output / f"{prefix}_stage.pdf"
    a4_png = output / f"{prefix}_a4.png"
    a4_pdf = output / f"{prefix}_a4.pdf"

    stage.save(stage_png, dpi=(dpi, dpi))
    stage.convert("RGB").save(stage_pdf, resolution=dpi)

    a4_width = mm_to_pixels(210.0, dpi)
    a4_height = mm_to_pixels(297.0, dpi)
    a4 = Image.new("L", (a4_width, a4_height), 255)
    x = (a4_width - stage.width) // 2
    y = (a4_height - stage.height) // 2
    a4.paste(stage, (x, y))
    a4.save(a4_png, dpi=(dpi, dpi))
    a4.convert("RGB").save(a4_pdf, resolution=dpi)

    manifest.update(
        {
            "stage_png": str(stage_png),
            "stage_pdf": str(stage_pdf),
            "a4_png": str(a4_png),
            "a4_pdf": str(a4_pdf),
        }
    )
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def _center_mm(position: str, radius_mm: float) -> list[float]:
    if position == "top":
        return [0.0, -radius_mm]
    if position == "right":
        return [radius_mm, 0.0]
    if position == "bottom":
        return [0.0, radius_mm]
    if position == "left":
        return [-radius_mm, 0.0]
    raise ValueError(position)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        marker_ids = parse_ids(args.ids)
        stage, manifest = build_stage_image(
            marker_ids=marker_ids,
            dictionary=args.dictionary,
            stage_diameter_mm=args.stage_diameter_mm,
            marker_radius_mm=args.marker_radius_mm,
            marker_total_mm=args.marker_total_mm,
            quiet_zone_mm=args.quiet_zone_mm,
            dpi=args.dpi,
        )
        save_outputs(stage, manifest, output=args.output, prefix=args.prefix, dpi=args.dpi)
    except ValueError as exc:
        parser.error(str(exc))

    print(f"Generated stage layout: {args.output}")
    print(f"Stage diameter: {args.stage_diameter_mm:g} mm")
    print(f"Marker center radius: {args.marker_radius_mm:g} mm")
    print(f"Marker total size: {args.marker_total_mm:g} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
