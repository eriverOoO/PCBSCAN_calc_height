from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyze_source_evidence import main as analyze_evidence
from fetch_external_fpp import main as fetch_external
from run_validation_suite import run_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the manufacturer-bounded CS126MU sensor case and a descriptive "
            "audit against checksum-pinned physical scanner-sim HDR samples"
        )
    )
    parser.add_argument(
        "--external-root", type=Path, default=Path("validation_data/external")
    )
    parser.add_argument(
        "--ideal-root",
        type=Path,
        default=Path("validation_data/ideal/source_grounded_pcb_v2"),
    )
    parser.add_argument(
        "--stress-root",
        type=Path,
        default=Path("validation_data/stress/held_out/source_grounded_v2"),
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("validation_results/source_grounded")
    )
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=320)
    parser.add_argument("--ideal-seed", type=int, default=17)
    parser.add_argument("--seeds-per-profile", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Use already-downloaded scanner-sim files and do not access the network",
    )
    parser.add_argument("--open", action="store_true", dest="open_report")
    return parser


def _write_landing_page(
    output_root: Path, dashboard: Path, evidence_html: Path, failures: int
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    dashboard_link = dashboard.relative_to(output_root).as_posix()
    evidence_link = evidence_html.relative_to(output_root).as_posix()
    status = "완료" if failures == 0 else f"오류 {failures}건"
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>Source-grounded validation</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:48px auto;padding:0 20px;color:#17202a}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}}.card{{border:1px solid #ccd1d1;border-radius:12px;padding:20px}}a{{color:#0969da}}.warn{{background:#fff4d6;border-left:5px solid #d68910;padding:14px}}code{{background:#f3f4f4;padding:2px 5px}}</style></head>
<body><h1>출처 기반 검증 결과</h1><p>실행 상태: <strong>{html.escape(status)}</strong></p>
<p class="warn">두 보고서는 서로 다른 질문에 답합니다. CS126MU 보고서는 공개 제조사 사양으로 경계가 정해진 센서 잡음만 검사하고, 외부 증거 감사는 실제 scanner-sim 영상과의 도메인 차이만 기술합니다. 어느 쪽도 실제 장비의 mm 높이 정확도를 입증하지 않습니다.</p>
<div class="cards"><section class="card"><h2>CS126MU 센서 검증</h2><p>full-well, read noise, 12-bit ADC를 적용한 22-frame 디코딩 결과와 case별 입력/출력 표입니다. physical-background proxy case는 별도 행으로 표시됩니다.</p><p><a href="{html.escape(dashboard_link)}">시뮬레이션 대시보드 열기</a></p></section>
<section class="card"><h2>실제 영상 도메인 감사</h2><p>체크섬으로 고정한 실제 HDR 패턴/배경 샘플과 로컬 합성 프레임의 기술 통계입니다.</p><p><a href="{html.escape(evidence_link)}">외부 증거 감사 열기</a></p></section></div>
<h2>해석 제한</h2><ul><li>단일 장면에서 PSF, 감마, read noise를 역추정하지 않았습니다.</li><li>scanner-sim의 패턴군과 장면은 production PCB 22-frame 입력과 다릅니다.</li><li>실제 장비에서 반복 dark/flat, PSF target, geometric calibration, 등록된 3D ground truth를 취득해야 최종 정확도 검증이 가능합니다.</li></ul></body></html>"""
    target = output_root / "source_grounded_index.html"
    target.write_text(page, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    external_root = args.external_root.expanduser().resolve()
    ideal_root = args.ideal_root.expanduser().resolve()
    stress_root = args.stress_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()

    if not args.no_download:
        download_status = fetch_external(
            [
                "--dataset",
                "scanner_sim_physical",
                "--sample-set",
                "--output-root",
                str(external_root),
                "--yes",
            ]
        )
        if download_status:
            return int(download_status)

    suite_args = argparse.Namespace(
        ideal_root=ideal_root,
        stress_root=stress_root,
        output_root=output_root / "simulation",
        # Keep the published-sensor case and the separate measured-background
        # transfer case side by side.  The latter is still not a real-rig
        # accuracy claim; it is an auditable image-domain cross-check.
        profiles=["cs126mu", "source_empirical"],
        seeds_per_profile=args.seeds_per_profile,
        width=args.width,
        height=args.height,
        ideal_seed=args.ideal_seed,
        open_dashboard=False,
    )
    dashboard, cases = run_suite(suite_args)
    failures = sum(case["status"] != "ok" for case in cases)

    evidence_status = analyze_evidence(
        [
            "--scanner-root",
            str(external_root / "scanner_sim_physical"),
            "--synthetic-root",
            str(ideal_root),
            "--output-root",
            str(output_root / "evidence"),
        ]
    )
    if evidence_status:
        return int(evidence_status)
    evidence_html = output_root / "evidence" / "source_evidence.html"
    landing = _write_landing_page(output_root, dashboard, evidence_html, failures)
    (output_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dashboard": str(dashboard),
                "evidence_report": str(evidence_html),
                "cases_total": len(cases),
                "case_failures": failures,
                "real_world_accuracy_claim": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Source-grounded landing page: {landing}")
    if args.open_report:
        if hasattr(os, "startfile"):
            os.startfile(landing)  # type: ignore[attr-defined]
        else:
            import webbrowser

            webbrowser.open(landing.as_uri())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
