from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw


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
class MarkerSpec:
    marker_id: int
    dictionary: str
    marker_size_mm: float
    quiet_zone_mm: float
    dpi: int
    marker_pixels: int
    quiet_zone_pixels: int
    png: str | None
    pdf: str | None


@dataclass(frozen=True)
class SheetSpec:
    paper: str
    width_mm: float
    height_mm: float
    png: str | None
    pdf: str | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate printable ArUco marker images for rotation-stage alignment."
    )
    parser.add_argument(
        "--ids",
        default="0",
        help="Marker id list, for example: 0 or 0,1,2 or 0-3",
    )
    parser.add_argument(
        "--dictionary",
        default="DICT_4X4_50",
        choices=sorted(ARUCO_DICTIONARIES),
        help="OpenCV ArUco dictionary",
    )
    parser.add_argument(
        "--marker-size-mm",
        type=float,
        default=50.0,
        help="Printed black ArUco square size in millimeters",
    )
    parser.add_argument(
        "--quiet-zone-mm",
        type=float,
        default=10.0,
        help="White margin around the marker in millimeters",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Output resolution metadata for printing",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("markers") / "aruco",
        help="Output folder",
    )
    parser.add_argument(
        "--format",
        choices=("png", "pdf", "both"),
        default="png",
        help="Output file format",
    )
    parser.add_argument(
        "--prefix",
        default="aruco",
        help="Output file name prefix",
    )
    parser.add_argument(
        "--no-label",
        action="store_true",
        help="Do not print dictionary/id/size text below the quiet zone",
    )
    parser.add_argument(
        "--sheet",
        choices=("none", "a4"),
        default="none",
        help="Also save all requested markers on a printable paper sheet",
    )
    parser.add_argument(
        "--sheet-format",
        choices=("png", "pdf", "both"),
        default="both",
        help="Output format for --sheet",
    )
    parser.add_argument(
        "--sheet-prefix",
        default="aruco_sheet",
        help="Output file name prefix for --sheet",
    )
    return parser


def parse_marker_ids(value: str) -> list[int]:
    ids: list[int] = []
    for chunk in value.split(","):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"Invalid descending id range: {part}")
            ids.extend(range(start, end + 1))
        else:
            ids.append(int(part))
    if not ids:
        raise ValueError("At least one marker id is required")
    return ids


def mm_to_pixels(mm: float, dpi: int) -> int:
    if mm <= 0:
        raise ValueError("Millimeter values must be positive")
    return max(1, round(mm * dpi / 25.4))


def load_aruco_dictionary(dictionary_name: str):
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV with ArUco support is required. Install opencv-contrib-python, "
            "then run this script again."
        ) from exc

    aruco = getattr(cv2, "aruco", None)
    if aruco is None:
        raise RuntimeError(
            "This OpenCV build does not include cv2.aruco. Install "
            "opencv-contrib-python instead of opencv-python."
        )

    dictionary_id = getattr(aruco, dictionary_name, None)
    if dictionary_id is None:
        raise RuntimeError(f"OpenCV does not provide ArUco dictionary {dictionary_name}")

    if hasattr(aruco, "getPredefinedDictionary"):
        dictionary = aruco.getPredefinedDictionary(dictionary_id)
    else:
        dictionary = aruco.Dictionary_get(dictionary_id)
    return cv2, aruco, dictionary


def generate_marker_image(
    marker_id: int,
    dictionary_name: str,
    marker_size_mm: float,
    quiet_zone_mm: float,
    dpi: int,
    label: bool = True,
) -> tuple[Image.Image, int, int]:
    cv2, aruco, dictionary = load_aruco_dictionary(dictionary_name)
    marker_pixels = mm_to_pixels(marker_size_mm, dpi)
    quiet_zone_pixels = mm_to_pixels(quiet_zone_mm, dpi)
    marker_count = dictionary.bytesList.shape[0]
    if marker_id < 0 or marker_id >= marker_count:
        raise ValueError(
            f"Marker id {marker_id} is outside {dictionary_name} range "
            f"0..{marker_count - 1}"
        )

    if hasattr(aruco, "generateImageMarker"):
        marker = aruco.generateImageMarker(dictionary, marker_id, marker_pixels)
    else:
        marker = aruco.drawMarker(dictionary, marker_id, marker_pixels)

    marker_image = Image.fromarray(marker).convert("L")
    canvas_size = marker_pixels + quiet_zone_pixels * 2
    label_height = 0
    label_text = (
        f"{dictionary_name}  id={marker_id}  marker={marker_size_mm:g}mm  "
        f"quiet={quiet_zone_mm:g}mm"
    )
    if label:
        label_height = max(28, round(0.08 * canvas_size))

    canvas = Image.new("L", (canvas_size, canvas_size + label_height), 255)
    canvas.paste(marker_image, (quiet_zone_pixels, quiet_zone_pixels))

    if label:
        draw = ImageDraw.Draw(canvas)
        bbox = draw.textbbox((0, 0), label_text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = max(0, (canvas_size - text_width) // 2)
        y = canvas_size + max(0, (label_height - text_height) // 2) - 1
        draw.text((x, y), label_text, fill=0)

    return canvas, marker_pixels, quiet_zone_pixels


def save_marker(
    marker_id: int,
    dictionary_name: str,
    marker_size_mm: float,
    quiet_zone_mm: float,
    dpi: int,
    output_dir: Path,
    output_format: str,
    prefix: str,
    label: bool,
) -> MarkerSpec:
    image, marker_pixels, quiet_zone_pixels = generate_marker_image(
        marker_id=marker_id,
        dictionary_name=dictionary_name,
        marker_size_mm=marker_size_mm,
        quiet_zone_mm=quiet_zone_mm,
        dpi=dpi,
        label=label,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{prefix}_{dictionary_name.lower()}_id{marker_id:03d}_{marker_size_mm:g}mm"
    png_path: Path | None = None
    pdf_path: Path | None = None

    if output_format in ("png", "both"):
        png_path = output_dir / f"{stem}.png"
        image.save(png_path, dpi=(dpi, dpi))
    if output_format in ("pdf", "both"):
        pdf_path = output_dir / f"{stem}.pdf"
        image.convert("RGB").save(pdf_path, resolution=dpi)

    return MarkerSpec(
        marker_id=marker_id,
        dictionary=dictionary_name,
        marker_size_mm=marker_size_mm,
        quiet_zone_mm=quiet_zone_mm,
        dpi=dpi,
        marker_pixels=marker_pixels,
        quiet_zone_pixels=quiet_zone_pixels,
        png=str(png_path) if png_path else None,
        pdf=str(pdf_path) if pdf_path else None,
    )


def save_a4_sheet(
    marker_ids: list[int],
    dictionary_name: str,
    marker_size_mm: float,
    quiet_zone_mm: float,
    dpi: int,
    output_dir: Path,
    output_format: str,
    prefix: str,
) -> SheetSpec:
    page_width_mm = 210.0
    page_height_mm = 297.0
    page_width = mm_to_pixels(page_width_mm, dpi)
    page_height = mm_to_pixels(page_height_mm, dpi)
    margin = mm_to_pixels(20.0, dpi)
    gap = mm_to_pixels(18.0, dpi)
    label_height = mm_to_pixels(6.0, dpi)

    marker_images: list[tuple[int, Image.Image]] = []
    for marker_id in marker_ids:
        image, _, _ = generate_marker_image(
            marker_id=marker_id,
            dictionary_name=dictionary_name,
            marker_size_mm=marker_size_mm,
            quiet_zone_mm=quiet_zone_mm,
            dpi=dpi,
            label=False,
        )
        marker_images.append((marker_id, image))

    page = Image.new("L", (page_width, page_height), 255)
    draw = ImageDraw.Draw(page)
    marker_width = marker_images[0][1].width
    marker_height = marker_images[0][1].height
    usable_width = page_width - margin * 2
    columns = max(1, (usable_width + gap) // (marker_width + gap))
    row_step = marker_height + label_height + gap

    for row_start in range(0, len(marker_images), columns):
        row = marker_images[row_start : row_start + columns]
        row_width = len(row) * marker_width + max(0, len(row) - 1) * gap
        x = (page_width - row_width) // 2
        y = margin + (row_start // columns) * row_step
        if y + marker_height + label_height > page_height - margin:
            raise ValueError("Too many markers to fit on one A4 sheet")
        for marker_id, image in row:
            page.paste(image, (x, y))
            text = f"ID {marker_id}"
            bbox = draw.textbbox((0, 0), text)
            text_width = bbox[2] - bbox[0]
            draw.text((x + (marker_width - text_width) // 2, y + marker_height + 4), text, fill=0)
            x += marker_width + gap

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{prefix}_{dictionary_name.lower()}_{marker_size_mm:g}mm_a4"
    png_path: Path | None = None
    pdf_path: Path | None = None

    if output_format in ("png", "both"):
        png_path = output_dir / f"{stem}.png"
        page.save(png_path, dpi=(dpi, dpi))
    if output_format in ("pdf", "both"):
        pdf_path = output_dir / f"{stem}.pdf"
        page.convert("RGB").save(pdf_path, resolution=dpi)

    return SheetSpec(
        paper="a4",
        width_mm=page_width_mm,
        height_mm=page_height_mm,
        png=str(png_path) if png_path else None,
        pdf=str(pdf_path) if pdf_path else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        marker_ids = parse_marker_ids(args.ids)
        specs = [
            save_marker(
                marker_id=marker_id,
                dictionary_name=args.dictionary,
                marker_size_mm=args.marker_size_mm,
                quiet_zone_mm=args.quiet_zone_mm,
                dpi=args.dpi,
                output_dir=args.output,
                output_format=args.format,
                prefix=args.prefix,
                label=not args.no_label,
            )
            for marker_id in marker_ids
        ]
        sheet_spec = None
        if args.sheet == "a4":
            sheet_spec = save_a4_sheet(
                marker_ids=marker_ids,
                dictionary_name=args.dictionary,
                marker_size_mm=args.marker_size_mm,
                quiet_zone_mm=args.quiet_zone_mm,
                dpi=args.dpi,
                output_dir=args.output,
                output_format=args.sheet_format,
                prefix=args.sheet_prefix,
            )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    manifest = {
        "markers": [asdict(spec) for spec in specs],
        "sheet": asdict(sheet_spec) if sheet_spec else None,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(f"Generated {len(specs)} marker(s)")
    if sheet_spec:
        print(f"Generated A4 sheet: {sheet_spec.pdf or sheet_spec.png}")
    print(f"Output folder: {args.output}")
    print(f"Manifest: {manifest_path}")
    return 0
