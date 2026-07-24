from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation_harness.capture_evidence import (
    SUPPORTED_SUFFIXES,
    write_capture_evidence_report,
)
from run_validation_suite import run_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze the unordered XIMEA captures, then compare a clean synthetic "
            "case with an evaluation-only XIMEA-observed held-out stress case"
        )
    )
    parser.add_argument(
        "--capture-root",
        type=Path,
        default=Path("validation_data/external/ximea_0724"),
    )
    parser.add_argument(
        "--ideal-root",
        type=Path,
        default=Path("validation_data/ideal/ximea_observed_pcb_v1"),
    )
    parser.add_argument(
        "--stress-root",
        type=Path,
        default=Path("validation_data/stress/held_out/ximea_observed_v2"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("validation_results/ximea_observed"),
    )
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=320)
    parser.add_argument("--ideal-seed", type=int, default=17)
    parser.add_argument("--seeds-per-profile", type=int, choices=(1, 2), default=2)
    parser.add_argument("--open", action="store_true", dest="open_report")
    return parser


def _capture_paths(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(
            f"capture root not found: {root}; copy the nine TIFF files there "
            "or pass --capture-root"
        )
    paths = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: path.name.lower(),
    )
    if not paths:
        raise FileNotFoundError(f"no supported capture images below {root}")
    return paths


def _write_landing_page(
    output_root: Path, evidence_html: Path, dashboard: Path, failures: int
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    evidence_link = evidence_html.relative_to(output_root).as_posix()
    dashboard_link = dashboard.relative_to(output_root).as_posix()
    status = "완료" if failures == 0 else f"오류 {failures}건"
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>XIMEA-observed held-out validation</title>
<style>body{{font-family:system-ui,sans-serif;max-width:960px;margin:44px auto;padding:0 20px;color:#17202a}}.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.card{{border:1px solid #ccd1d1;border-radius:12px;padding:20px}}.warn{{background:#fff4d6;border-left:5px solid #d68910;padding:14px}}a{{color:#0969da}}@media(max-width:700px){{.cards{{grid-template-columns:1fr}}}}</style></head>
<body><h1>XIMEA 실사 참고 held-out 검증</h1><p>실행 상태: <strong>{html.escape(status)}</strong></p>
<p class="warn">9장은 순서·자세·초점·높이 GT가 통제되지 않았으므로 정확도 정답으로 쓰지 않았습니다. 관측 가능한 영상-domain 특성만 별도 held-out 스트레스 분포에 반영했으며 production decoder 설정은 바꾸지 않았습니다.</p>
<div class="cards"><section class="card"><h2>실사 특성 감사</h2><p>원본 contact sheet, 프레임별 intensity·포화·공간 불균일 통계, SHA-256과 추정 제외 항목을 확인합니다.</p><p><a href="{html.escape(evidence_link)}">실사 특성 보고서 열기</a></p></section>
<section class="card"><h2>Clean 대 XIMEA-observed</h2><p>같은 이상적 GT에 clean과 실사 참고 nuisance envelope를 적용한 입력 22장 및 복원 결과를 case별로 비교합니다.</p><p><a href="{html.escape(dashboard_link)}">시뮬레이션 대시보드 열기</a></p></section></div>
<h2>해석 한계</h2><ul><li>이 결과는 합성 GT에 대한 강건성 검사이며 실제 장비 mm 정확도가 아닙니다.</li><li>실사 9장의 패턴 순서나 자세 차이를 phase/height GT로 사용하지 않았습니다.</li><li>PSF·감마·노이즈·왜곡은 calibration capture가 없어 측정값으로 맞추지 않았습니다.</li></ul></body></html>"""
    target = output_root / "ximea_observed_index.html"
    target.write_text(page, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    capture_root = args.capture_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    evidence_html, evidence_json, _sheet = write_capture_evidence_report(
        _capture_paths(capture_root), output_root / "evidence"
    )
    suite_args = argparse.Namespace(
        ideal_root=args.ideal_root.expanduser().resolve(),
        stress_root=args.stress_root.expanduser().resolve(),
        output_root=output_root / "simulation",
        profiles=["clean", "ximea_observed"],
        seeds_per_profile=args.seeds_per_profile,
        width=args.width,
        height=args.height,
        ideal_seed=args.ideal_seed,
        open_dashboard=False,
    )
    dashboard, cases = run_suite(suite_args)
    failures = sum(case["status"] != "ok" for case in cases)
    landing = _write_landing_page(output_root, evidence_html, dashboard, failures)
    (output_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "capture_evidence": str(evidence_json),
                "simulation_dashboard": str(dashboard),
                "cases_total": len(cases),
                "case_failures": failures,
                "decoder_thresholds_tuned_from_capture_set": False,
                "real_world_accuracy_claim": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"XIMEA-observed landing page: {landing}")
    if args.open_report:
        if hasattr(os, "startfile"):
            os.startfile(landing)  # type: ignore[attr-defined]
        else:
            import webbrowser

            webbrowser.open(landing.as_uri())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
