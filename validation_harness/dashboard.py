from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .manifests import write_json


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


def _case_row(case: Mapping[str, Any], dashboard_root: Path) -> dict[str, Any]:
    summary = case.get("summary") if isinstance(case.get("summary"), dict) else {}
    result_dir = Path(case["result_dir"])
    try:
        result_relative = result_dir.resolve().relative_to(dashboard_root.resolve()).as_posix()
    except ValueError:
        result_relative = result_dir.resolve().as_uri()
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
        "result_relative": result_relative,
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
    width = ratio * 100.0
    return (
        f'<span class="bar {kind}" aria-hidden="true"><span style="width:{width:.2f}%"></span></span>'
    )


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
    payload = {
        "schema_version": 1,
        "scope": "synthetic phase-domain validation; not hardware/mm accuracy",
        "metadata": dict(suite_metadata),
        "l0": dict(l0_summary or {}),
        "profiles": profiles,
        "cases": rows,
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
        error = html.escape(str(row["error"])) if row["error"] else ""
        overview = f'{row["result_relative"]}/overview.png'
        summary_link = f'{row["result_relative"]}/summary.json'
        case_rows.append(
            "<tr>"
            f'<td>{html.escape(str(row["profile"]))}</td>'
            f'<td>{row["seed"]}</td>'
            f'<td><span class="status {status_class}">{status_text}</span>{error}</td>'
            f'<td>{_format(row["deg0_valid"] * 100 if row["deg0_valid"] is not None else None, 1)}%</td>'
            f'<td>{_format(row["deg0_mae"])} / {_format(row["deg0_p95"])} rad</td>'
            f'<td>{_format(row["deg180_valid"] * 100 if row["deg180_valid"] is not None else None, 1)}%</td>'
            f'<td>{_format(row["deg180_mae"])} / {_format(row["deg180_p95"])} rad</td>'
            f'<td><a href="{html.escape(overview)}">overview</a> · <a href="{html.escape(summary_link)}">JSON</a></td>'
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
:root {{ color-scheme: light dark; --bg:#f6f7f9; --fg:#17191c; --muted:#667085; --panel:#fff; --border:#d9dde4; --ok:#16803c; --bad:#b42318; --valid:#3b82f6; --error:#ef8354; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121417; --fg:#eef0f3; --muted:#a7adb7; --panel:#1c2025; --border:#343a43; --ok:#55c878; --bad:#ff7b72; --valid:#60a5fa; --error:#f59e72; }} }}
* {{ box-sizing:border-box; }} body {{ margin:0; padding:24px; font:14px/1.45 system-ui,sans-serif; background:var(--bg); color:var(--fg); }}
main {{ max-width:1180px; margin:auto; }} h1 {{ margin:0 0 4px; font-size:24px; }} h2 {{ margin:26px 0 10px; font-size:17px; }}
.scope {{ color:var(--muted); margin:0 0 18px; }} .stats {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
.stat {{ background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px; }} .stat span {{ display:block; color:var(--muted); }} .stat strong {{ display:block; font-size:22px; margin-top:3px; }}
.table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--border); }} th,td {{ padding:10px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; white-space:nowrap; }} thead th {{ color:var(--muted); font-weight:500; }}
.bar {{ display:block; width:150px; max-width:100%; height:5px; margin-top:6px; background:var(--border); border-radius:4px; overflow:hidden; }} .bar span {{ display:block; height:100%; }} .bar.valid span {{ background:var(--valid); }} .bar.error span {{ background:var(--error); }}
.status {{ font-weight:600; margin-right:6px; }} .status.ok {{ color:var(--ok); }} .status.failed {{ color:var(--bad); }} a {{ color:var(--valid); }} code {{ color:var(--muted); }}
@media (max-width:700px) {{ body {{ padding:14px; }} .stats {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><main>
<h1>PCB FPP validation suite</h1>
<p class="scope">Synthetic phase-domain validation · 실장비/mm 정확도 주장이 아님</p>
<section class="stats" aria-label="실행 요약">
  <div class="stat"><span>L0 self-consistency</span><strong>{l0_label}</strong></div>
  <div class="stat"><span>L1 완료 case</span><strong>{len(rows) - failure_count}/{len(rows)}</strong></div>
  <div class="stat"><span>Decoder 실행 실패</span><strong>{failure_count}</strong></div>
</section>
<h2>Profile 비교</h2>
<div class="table-wrap"><table><thead><tr><th>Profile</th><th>완료</th><th>0° valid</th><th>0° MAE</th><th>180° valid</th><th>180° MAE</th></tr></thead><tbody>{''.join(profile_rows)}</tbody></table></div>
<h2>Case 상세</h2>
<div class="table-wrap"><table><thead><tr><th>Profile</th><th>Seed</th><th>상태</th><th>0° valid</th><th>0° MAE / P95</th><th>180° valid</th><th>180° MAE / P95</th><th>결과</th></tr></thead><tbody>{''.join(case_rows)}</tbody></table></div>
<p class="scope">설정: <code>{html.escape(json.dumps(dict(suite_metadata), ensure_ascii=False))}</code></p>
</main></body></html>
"""
    html_path = root / "index.html"
    html_path.write_text(document, encoding="utf-8")
    return html_path, json_path
