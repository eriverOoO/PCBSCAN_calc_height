from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from PIL import Image, ImageDraw

from .manifests import write_json


REPORT_NOTICE = "synthetic validation; not a real-world or hardware accuracy claim"


def _rows(summary: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    for view_name, view in summary.get("views", {}).items():
        for region_name, region in view.get("regions", {}).items():
            for domain_name, values in region.items():
                row = {"view": view_name, "region": region_name, "domain": domain_name}
                row.update(values)
                yield row


def write_summary(output_dir: str | Path, summary: Mapping[str, Any]) -> tuple[Path, Path]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    payload = dict(summary)
    payload.setdefault("report_notice", REPORT_NOTICE)
    json_path = write_json(folder / "summary.json", payload)
    rows = list(_rows(payload))
    fieldnames = ["view", "region", "domain"]
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    csv_path = folder / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def failure_record(
    *,
    case_id: str,
    seed: int | None,
    profile: str | None,
    reason: str,
    rerun_command: str,
    impairment_manifest: Mapping[str, Any] | None = None,
    error_metrics: Mapping[str, Any] | None = None,
    mask_paths: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "seed": seed,
        "profile": profile,
        "reason": reason,
        "rerun_command": rerun_command,
        "impairment_manifest": dict(impairment_manifest or {}),
        "error_metrics": dict(error_metrics or {}),
        "error_mask_paths": list(mask_paths),
        "decoder_change_applied": False,
    }


def write_failures(output_dir: str | Path, failures: Iterable[Mapping[str, Any]]) -> Path:
    payload = {
        "schema_version": 1,
        "policy": "record synthetic failures; do not tune the production decoder automatically",
        "failures": list(failures),
    }
    return write_json(Path(output_dir) / "failures.json", payload)


def _normalize(array: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    values = np.asarray(array, dtype=np.float64)
    mask = np.isfinite(values)
    if valid is not None:
        mask &= np.asarray(valid, dtype=bool)
    if not np.any(mask):
        return np.zeros(values.shape, dtype=np.uint8)
    low, high = np.percentile(values[mask], [2, 98])
    if high <= low:
        high = low + 1.0
    scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
    scaled[~mask] = 0.0
    return np.rint(scaled * 255.0).astype(np.uint8)


def write_overview(
    path: str | Path,
    *,
    prediction: np.ndarray,
    truth: np.ndarray | None,
    valid: np.ndarray | None,
    title: str,
) -> Path:
    predicted = _normalize(prediction, valid)
    panels = [("prediction", predicted)]
    if truth is not None:
        truth_arr = np.asarray(truth)
        panels.append(("ground truth", _normalize(truth_arr)))
        panels.append(("absolute error", _normalize(np.abs(np.asarray(prediction) - truth_arr), valid)))
    height, width = predicted.shape
    header = 28
    canvas = Image.new("L", (width * len(panels), height + header), color=0)
    draw = ImageDraw.Draw(canvas)
    for index, (label, panel) in enumerate(panels):
        canvas.paste(Image.fromarray(panel), (index * width, header))
        draw.text((index * width + 4, 4), label, fill=255)
    draw.text((4, 16), title[:120], fill=200)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output
