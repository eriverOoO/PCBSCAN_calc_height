from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

import numpy as np
from PIL import Image, ImageDraw

from .manifests import write_json


VIEWS = ("object_0", "object_180", "reference_0", "reference_180")


def _metric(summary: Mapping[str, Any], view: str, name: str) -> float | None:
    value = (
        summary.get("views", {})
        .get(view, {})
        .get("regions", {})
        .get("pcb_all", {})
        .get("phase_error_rad", {})
        .get(name)
    )
    return float(value) if isinstance(value, (int, float)) else None


def _format(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _relative_or_uri(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_uri()


def _case_row(case: Mapping[str, Any], dashboard_root: Path) -> dict[str, Any]:
    summary = case.get("summary") if isinstance(case.get("summary"), dict) else {}
    result_dir = Path(case["result_dir"])
    return {
        "profile": case.get("profile", "unknown"),
        "seed": case.get("seed"),
        "status": case.get("status", "unknown"),
        "error": case.get("error"),
        "deg0_valid": _metric(summary, "deg_0", "valid_ratio"),
        "deg0_mae": _metric(summary, "deg_0", "mae"),
        "deg0_p95": _metric(summary, "deg_0", "p95_absolute_error"),
        "deg180_valid": _metric(summary, "deg_180", "valid_ratio"),
        "deg180_mae": _metric(summary, "deg_180", "mae"),
        "deg180_p95": _metric(summary, "deg_180", "p95_absolute_error"),
        "case_dir": Path(case["case_dir"]),
        "result_dir": result_dir,
        "result_relative": _relative_or_uri(result_dir, dashboard_root),
    }


def _profile_aggregates(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["profile"]), []).append(row)
    output: list[dict[str, Any]] = []
    for profile, values in grouped.items():
        successful = [row for row in values if row["status"] == "ok"]

        def average(key: str) -> float | None:
            numbers = [float(row[key]) for row in successful if row[key] is not None]
            return sum(numbers) / len(numbers) if numbers else None

        output.append(
            {
                "profile": profile,
                "case_count": len(values),
                "success_count": len(successful),
                "deg0_valid": average("deg0_valid"),
                "deg0_mae": average("deg0_mae"),
                "deg180_valid": average("deg180_valid"),
                "deg180_mae": average("deg180_mae"),
            }
        )
    order = {"clean": 0, "normal": 1, "hard": 2, "extreme": 3}
    return sorted(output, key=lambda item: order.get(item["profile"], 99))


def _bar(value: float | None, maximum: float, kind: str) -> str:
    ratio = 0.0 if value is None else max(0.0, min(float(value) / maximum, 1.0))
    return (
        f'<span class="bar {kind}" aria-hidden="true">'
        f'<span style="width:{ratio * 100.0:.2f}%"></span></span>'
    )


def _to_preview(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    data = np.asarray(image)
    if data.ndim == 3:
        data = data[..., :3].mean(axis=2)
    data = data.astype(np.float32)
    source_max = 65535.0 if data.size and float(np.nanmax(data)) > 255.0 else 255.0
    normalized = np.clip(data / source_max * 255.0, 0, 255).astype(np.uint8)
    preview = Image.fromarray(normalized)
    preview.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("L", size, 16)
    canvas.paste(preview, ((size[0] - preview.width) // 2, (size[1] - preview.height) // 2))
    return canvas


def _write_contact_sheet(view_dir: Path, output_path: Path) -> bool:
    frames = sorted(view_dir.glob("*.png"))
    if not frames:
        return False
    columns = 6
    thumb_size = (154, 96)
    label_height = 18
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("L", (columns * thumb_size[0], rows * (thumb_size[1] + label_height)), 16)
    draw = ImageDraw.Draw(sheet)
    for index, frame_path in enumerate(frames):
        x = (index % columns) * thumb_size[0]
        y = (index // columns) * (thumb_size[1] + label_height)
        with Image.open(frame_path) as image:
            sheet.paste(_to_preview(image, thumb_size), (x, y))
        draw.text((x + 4, y + thumb_size[1] + 2), frame_path.stem, fill=230)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, optimize=True)
    return True


def _case_visuals(row: Mapping[str, Any], root: Path) -> dict[str, str]:
    asset_dir = root / "assets" / f'{row["profile"]}_{row["seed"]}'
    visuals: dict[str, str] = {}
    for view in VIEWS:
        sheet_path = asset_dir / f"input_{view}.png"
        if _write_contact_sheet(Path(row["case_dir"]) / "views" / view, sheet_path):
            visuals[view] = _relative_or_uri(sheet_path, root)
    overview = Path(row["result_dir"]) / "overview.png"
    if overview.exists():
        visuals["overview"] = _relative_or_uri(overview, root)
    return visuals


def write_suite_dashboard(
    output_root: str | Path,
    *,
    cases: list[Mapping[str, Any]],
    l0_summary: Mapping[str, Any] | None,
    suite_metadata: Mapping[str, Any],
) -> tuple[Path, Path]:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = [_case_row(case, root) for case in cases]
    profiles = _profile_aggregates(rows)
    failure_count = sum(row["status"] != "ok" for row in rows)
    l0_checks = (l0_summary or {}).get("checks", {})
    l0_ok = bool(l0_checks) and all(
        value is True or isinstance(value, (int, float, list, dict))
        for value in l0_checks.values()
    )
    payload_rows = [
        {key: value for key, value in row.items() if key not in {"case_dir", "result_dir"}}
        for row in rows
    ]
    payload = {
        "schema_version": 2,
        "scope": "synthetic phase-domain validation; not hardware/mm accuracy",
        "metadata": dict(suite_metadata),
        "l0": dict(l0_summary or {}),
        "profiles": profiles,
        "cases": payload_rows,
        "failure_count": failure_count,
    }
    json_path = write_json(root / "suite_summary.json", payload)

    max_mae = max(
        [float(row["deg0_mae"]) for row in rows if row["deg0_mae"] is not None]
        + [float(row["deg180_mae"]) for row in rows if row["deg180_mae"] is not None]
        + [1.0]
    )
    profile_rows = []
    for item in profiles:
        profile_rows.append(
            "<tr>"
            f'<th scope="row">{html.escape(str(item["profile"]))}</th>'
            f'<td>{item["success_count"]}/{item["case_count"]}</td>'
            f'<td><strong>{_format(item["deg0_valid"] * 100 if item["deg0_valid"] is not None else None, 1)}%</strong>{_bar(item["deg0_valid"], 1.0, "valid")}</td>'
            f'<td><strong>{_format(item["deg0_mae"])}</strong> rad{_bar(item["deg0_mae"], max_mae, "error")}</td>'
            f'<td><strong>{_format(item["deg180_valid"] * 100 if item["deg180_valid"] is not None else None, 1)}%</strong>{_bar(item["deg180_valid"], 1.0, "valid")}</td>'
            f'<td><strong>{_format(item["deg180_mae"])}</strong> rad{_bar(item["deg180_mae"], max_mae, "error")}</td>'
            "</tr>"
        )

    case_rows = []
    for row in rows:
        status_text = "완료" if row["status"] == "ok" else "실패"
        status_class = "ok" if row["status"] == "ok" else "failed"
        error = f'<div class="error-text">{html.escape(str(row["error"]))}</div>' if row["error"] else ""
        visuals = _case_visuals(row, root)
        input_preview = visuals.get("object_0")
        input_html = "입력 없음"
        if input_preview:
            detail_images = "".join(
                f'<figure><figcaption>{html.escape(view)}</figcaption><a href="{quote(path)}"><img src="{quote(path)}" alt="{html.escape(view)}의 22장 입력 contact sheet" loading="lazy"></a></figure>'
                for view, path in visuals.items()
                if view in VIEWS
            )
            input_html = (
                f'<a href="{quote(input_preview)}"><img class="main-preview" src="{quote(input_preview)}" '
                'alt="object_0의 22장 입력 contact sheet" loading="lazy"></a>'
                '<div class="caption">object_0 · 22 frames</div>'
                f'<details><summary>4개 view의 입력 88장 보기</summary><div class="input-grid">{detail_images}</div></details>'
            )
        overview = visuals.get("overview")
        result_html = "결과 없음"
        if overview:
            result_html = (
                f'<a href="{quote(overview)}"><img class="main-preview" src="{quote(overview)}" '
                'alt="decoder 결과 overview" loading="lazy"></a>'
                '<div class="caption">복원 결과 overview</div>'
            )
        summary_link = f'{row["result_relative"]}/summary.json'
        case_rows.append(
            "<tr>"
            f'<th scope="row"><strong>{html.escape(str(row["profile"]))}</strong><br><span class="muted">seed {row["seed"]}</span><br><span class="status {status_class}">{status_text}</span>{error}</th>'
            f'<td class="visual-cell">{input_html}</td>'
            f'<td class="visual-cell">{result_html}</td>'
            '<td class="metrics">'
            f'<div><span>0° valid</span><strong>{_format(row["deg0_valid"] * 100 if row["deg0_valid"] is not None else None, 1)}%</strong></div>'
            f'<div><span>0° MAE / P95</span><strong>{_format(row["deg0_mae"])} / {_format(row["deg0_p95"])} rad</strong></div>'
            f'<div><span>180° valid</span><strong>{_format(row["deg180_valid"] * 100 if row["deg180_valid"] is not None else None, 1)}%</strong></div>'
            f'<div><span>180° MAE / P95</span><strong>{_format(row["deg180_mae"])} / {_format(row["deg180_p95"])} rad</strong></div>'
            f'<a href="{quote(summary_link)}">상세 JSON</a></td>'
            "</tr>"
        )

    l0_label = "통과" if l0_ok else "확인 필요"
    document = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PCB FPP validation suite</title>
<style>
:root {{ color-scheme:light dark; --bg:#f6f7f9; --fg:#17191c; --muted:#667085; --panel:#fff; --border:#d9dde4; --ok:#16803c; --bad:#b42318; --valid:#2563eb; --error:#ef8354; }}
@media (prefers-color-scheme:dark) {{ :root {{ --bg:#121417; --fg:#eef0f3; --muted:#a7adb7; --panel:#1c2025; --border:#343a43; --ok:#55c878; --bad:#ff7b72; --valid:#60a5fa; --error:#f59e72; }} }}
* {{ box-sizing:border-box; }} body {{ margin:0; padding:24px; font:14px/1.45 system-ui,sans-serif; background:var(--bg); color:var(--fg); }}
main {{ max-width:1440px; margin:auto; }} h1 {{ margin:0 0 4px; font-size:24px; }} h2 {{ margin:26px 0 10px; font-size:17px; }}
.scope,.muted,.caption {{ color:var(--muted); }} .scope {{ margin:0 0 18px; }} .caption {{ margin-top:4px; font-size:12px; }}
.stats {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }} .stat {{ background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px; }}
.stat span {{ display:block; color:var(--muted); }} .stat strong {{ display:block; font-size:22px; margin-top:3px; }}
.table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--border); }}
th,td {{ padding:10px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; }} thead th {{ color:var(--muted); font-weight:500; white-space:nowrap; }}
.profile-table td {{ white-space:nowrap; }} .bar {{ display:block; width:150px; max-width:100%; height:5px; margin-top:6px; background:var(--border); border-radius:4px; overflow:hidden; }}
.bar span {{ display:block; height:100%; }} .bar.valid span {{ background:var(--valid); }} .bar.error span {{ background:var(--error); }}
.status {{ display:inline-block; margin-top:8px; font-weight:600; }} .status.ok {{ color:var(--ok); }} .status.failed,.error-text {{ color:var(--bad); }}
.case-table {{ table-layout:fixed; min-width:1050px; }} .case-table th:first-child {{ width:105px; }} .case-table .visual-cell {{ width:31%; }} .case-table .metrics {{ width:250px; }}
.main-preview {{ display:block; width:100%; height:auto; max-height:260px; object-fit:contain; background:#101010; }} a {{ color:var(--valid); }}
.metrics div {{ display:flex; justify-content:space-between; gap:12px; padding:4px 0; border-bottom:1px solid var(--border); }} .metrics span {{ color:var(--muted); }} .metrics a {{ display:inline-block; margin-top:10px; }}
details {{ margin-top:8px; }} summary {{ cursor:pointer; color:var(--valid); }} .input-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:8px; }}
figure {{ margin:0; }} figcaption {{ color:var(--muted); margin-bottom:3px; }} figure img {{ display:block; width:100%; height:auto; background:#101010; }} code {{ color:var(--muted); }}
@media (max-width:700px) {{ body {{ padding:14px; }} .stats {{ grid-template-columns:1fr; }} .input-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><main>
<h1>PCB FPP validation suite</h1>
<p class="scope">합성 데이터의 phase-domain 검증입니다. 실제 장비의 mm 정확도를 뜻하지 않습니다.</p>
<section class="stats" aria-label="실행 요약">
  <div class="stat"><span>L0 self-consistency</span><strong>{l0_label}</strong></div>
  <div class="stat"><span>L1 완료 case</span><strong>{len(rows) - failure_count}/{len(rows)}</strong></div>
  <div class="stat"><span>Decoder 실행 실패</span><strong>{failure_count}</strong></div>
</section>
<h2>Profile 비교</h2>
<div class="table-wrap"><table class="profile-table"><thead><tr><th>Profile</th><th>완료</th><th>0° valid</th><th>0° MAE</th><th>180° valid</th><th>180° MAE</th></tr></thead><tbody>{''.join(profile_rows)}</tbody></table></div>
<h2>Case별 입력과 결과</h2>
<div class="table-wrap"><table class="case-table"><thead><tr><th>Case</th><th>실제 입력 이미지</th><th>Decoder 결과</th><th>정량 결과</th></tr></thead><tbody>{''.join(case_rows)}</tbody></table></div>
<p class="scope">입력 contact sheet의 각 칸은 decoder에 전달된 원본 16-bit PNG를 8-bit로 축소 표시한 것입니다. 설정: <code>{html.escape(json.dumps(dict(suite_metadata), ensure_ascii=False))}</code></p>
</main></body></html>
"""
    html_path = root / "index.html"
    html_path.write_text(document, encoding="utf-8")
    return html_path, json_path
