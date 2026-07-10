# 촬영 워크스페이스 구현 프롬프트

아래 프롬프트는 이 디코더 저장소와 호환되는 촬영 워크스페이스를 만들기 위한 요구사항입니다. 촬영 시스템은 다르더라도 저장 포맷과 pattern id 규약은 동일하게 맞추는 것을 목표로 합니다.

## 공통 디코더 계약

현재 디코더가 기대하는 최종 decode 입력 폴더는 다음 pattern id를 가진 grayscale 이미지와 `scan_log.json`입니다.

```text
00 White
01 Black
02 Gray0      03 Gray1      04 Gray2      05 Gray3
06 Gray4      07 Gray5      08 Gray6      09 Gray7
10 Sine_000   11 Sine_090   12 Sine_180   13 Sine_270
14 Gray0_inv  15 Gray1_inv  16 Gray2_inv  17 Gray3_inv
18 Gray4_inv  19 Gray5_inv  20 Gray6_inv  21 Gray7_inv
```

`14..21`은 선택 사항이지만 새 촬영 파이프라인에서는 기본으로 촬영합니다. 최종 합성 이미지는 `pattern_000.png`부터 `pattern_021.png`처럼 저장하고, `scan_log.json`에는 각 이미지의 `pattern_id`, `label`, `filename`, exposure/gain/merge metadata를 기록합니다.

기준 평면 scan과 대상 scan은 같은 프로젝터 각도, 초점, 카메라 자세, 노출 bracket preset, 프로젝터 밝기 조건에서 촬영해야 합니다.

## 구현 프롬프트: UV 카메라 촬영 시스템

대상 환경: XIMEA UV 카메라처럼 수동 노출/게인 제어가 가능한 UV 카메라와 PRO4500 계열 구조광 프로젝터를 사용하는 촬영 프로그램

목표: UV 카메라와 PRO4500 계열 구조광 촬영 시스템에 반전 Gray code 촬영과 다중 노출 HDR 저장/합성 기능을 추가합니다. 최종 출력은 이 디코더가 바로 읽을 수 있는 패턴 폴더여야 합니다.

구현 요구사항:

1. 기존 14장 패턴 촬영에 `Gray0_inv..Gray7_inv` 8장을 추가해 총 22개 pattern id를 지원합니다.
2. pattern id 규약은 반드시 `0 White`, `1 Black`, `2..9 Gray0..Gray7`, `10..13 Sine_000..Sine_270`, `14..21 Gray0_inv..Gray7_inv`를 따릅니다.
3. 반전 Gray는 기존 Gray pattern의 논리 반전이어야 합니다. 프로젝터 감마 또는 밝기 스케일 보정이 있더라도 같은 조건에서 정상/반전 패턴이 한 쌍으로 대응되게 만듭니다.
4. 촬영 순서는 하드웨어 안정성에 맞게 정해도 되지만 `scan_log.json`의 `pattern_id`가 정확해야 합니다. 권장 순서는 `White`, `Black`, `Gray0`, `Gray0_inv`, ..., `Gray7`, `Gray7_inv`, `Sine_000`, `Sine_090`, `Sine_180`, `Sine_270`입니다.
5. XIMEA UV 카메라는 manual exposure/gain 모드로 제어합니다. 자동 exposure, 자동 gain, 자동 white balance, 자동 focus가 있다면 모두 끕니다.
6. 각 pattern id마다 다중 노출 bracket을 촬영합니다. 기본 preset 예시는 `short`, `mid`, `long` 3단계이며 설정값은 config 파일에서 바꿀 수 있게 합니다.
7. 각 exposure frame은 raw 보존용 하위 폴더에 저장합니다. 예: `exposures/pattern_002/short.png`, `mid.png`, `long.png`.
8. HDR merge 결과는 디코더 입력 루트에 `pattern_002.png`처럼 저장합니다.
9. HDR merge 알고리즘은 픽셀별로 포화되지 않은 가장 긴 노출을 우선 선택하고, intensity를 exposure time/gain 기준으로 radiance normalize한 뒤 최종 8-bit 또는 16-bit grayscale로 다시 스케일합니다.
10. saturated threshold, dark threshold, exposure_us, gain_db, projector pattern label, capture timestamp를 `scan_log.json` 또는 `hdr_merge_report.json`에 기록합니다.
11. merge 중 모든 bracket이 포화된 픽셀과 모든 bracket이 너무 어두운 픽셀의 mask를 저장합니다. 예: `hdr_masks/pattern_002_saturated.png`, `hdr_masks/pattern_002_dark.png`.
12. 기준 평면 촬영 모드를 추가합니다. 출력 폴더 이름 또는 metadata에 `scan_type: "reference"`를 기록합니다.
13. 대상 촬영 모드를 추가합니다. 출력 폴더 이름 또는 metadata에 `scan_type: "object"`를 기록합니다.
14. 기준/대상 촬영 모두 프로젝터 기울기 30도, Scheimpflug 또는 수동 초점 확인 상태, 리그/보정 id를 metadata에 기록할 수 있게 합니다.
15. 프로젝터 keystone 사전 왜곡은 기본으로 하지 않습니다. metadata에 `keystone_predistortion: false`를 기록합니다.
16. 촬영 완료 후 최종 decode 폴더에 0..21 pattern id가 모두 있는지 검증합니다. 누락되면 오류를 띄우고 누락 id를 표시합니다.
17. 기존 14장 촬영 모드는 legacy 옵션으로 남겨도 되지만 기본 촬영 모드는 22장 + HDR merge로 합니다.
18. 저장된 최종 폴더는 이 디코더에서 `--gray-decode-mode auto`로 바로 사용할 수 있어야 합니다.

검증:

1. synthetic 또는 dry-run 모드로 22개 pattern id와 `scan_log.json`이 생성되는지 확인합니다.
2. 실제 XIMEA UV 카메라 연결 후 각 pattern마다 bracket 이미지와 merge 이미지가 모두 저장되는지 확인합니다.
3. `scan_log.json`에 pattern id, label, final filename, bracket filenames, exposure_us, gain_db가 들어가는지 확인합니다.
4. 같은 평면을 기준/대상으로 연속 촬영했을 때 최종 디코더의 `height/delta_phase.npy`가 거의 0에 가까워져야 합니다.

## 구현 프롬프트: Android 폰 카메라 촬영 시스템

대상 환경: Android 폰 카메라와 PRO4500 계열 구조광 프로젝터를 사용하는 촬영 프로그램

목표: Android 폰 카메라와 PRO4500 계열 구조광 촬영 시스템에 반전 Gray code 촬영과 다중 노출 HDR 저장/합성 기능을 추가합니다. 최종 출력은 이 디코더가 바로 읽을 수 있는 패턴 폴더여야 합니다.

구현 요구사항:

1. 기존 14장 패턴 촬영에 `Gray0_inv..Gray7_inv` 8장을 추가해 총 22개 pattern id를 지원합니다.
2. pattern id 규약은 반드시 `0 White`, `1 Black`, `2..9 Gray0..Gray7`, `10..13 Sine_000..Sine_270`, `14..21 Gray0_inv..Gray7_inv`를 따릅니다.
3. 반전 Gray는 기존 Gray pattern의 논리 반전이어야 합니다. 프로젝터 감마 또는 밝기 스케일 보정이 있더라도 같은 조건에서 정상/반전 패턴이 한 쌍으로 대응되게 만듭니다.
4. 촬영 순서는 하드웨어 안정성에 맞게 정해도 되지만 `scan_log.json`의 `pattern_id`가 정확해야 합니다. 권장 순서는 `White`, `Black`, `Gray0`, `Gray0_inv`, ..., `Gray7`, `Gray7_inv`, `Sine_000`, `Sine_090`, `Sine_180`, `Sine_270`입니다.
5. Android 폰 카메라는 가능한 경우 Camera2/manual capture 또는 기존 프로젝트의 Android 제어 경로를 사용해 manual exposure/ISO/focus로 고정합니다. AE, AWB, AF가 켜져 있으면 pattern별 밝기가 흔들릴 수 있으므로 촬영 시작 전에 lock합니다.
6. 각 pattern id마다 다중 노출 bracket을 촬영합니다. 기본 preset 예시는 `short`, `mid`, `long` 3단계이며 설정값은 config 파일에서 바꿀 수 있게 합니다.
7. 각 exposure frame은 raw 보존용 하위 폴더에 저장합니다. 예: `exposures/pattern_002/short.png`, `mid.png`, `long.png`.
8. HDR merge 결과는 디코더 입력 루트에 `pattern_002.png`처럼 저장합니다.
9. HDR merge 알고리즘은 픽셀별로 포화되지 않은 가장 긴 노출을 우선 선택하고, intensity를 exposure time/ISO 기준으로 radiance normalize한 뒤 최종 8-bit 또는 16-bit grayscale로 다시 스케일합니다.
10. saturated threshold, dark threshold, exposure_ns 또는 exposure_us, ISO, focus distance, projector pattern label, capture timestamp를 `scan_log.json` 또는 `hdr_merge_report.json`에 기록합니다.
11. merge 중 모든 bracket이 포화된 픽셀과 모든 bracket이 너무 어두운 픽셀의 mask를 저장합니다. 예: `hdr_masks/pattern_002_saturated.png`, `hdr_masks/pattern_002_dark.png`.
12. 기준 평면 촬영 모드를 추가합니다. 출력 폴더 이름 또는 metadata에 `scan_type: "reference"`를 기록합니다.
13. 대상 촬영 모드를 추가합니다. 출력 폴더 이름 또는 metadata에 `scan_type: "object"`를 기록합니다.
14. 기준/대상 촬영 모두 프로젝터 기울기 30도, 수동 초점 확인 상태, 폰 마운트/보정 id를 metadata에 기록할 수 있게 합니다.
15. 프로젝터 keystone 사전 왜곡은 기본으로 하지 않습니다. metadata에 `keystone_predistortion: false`를 기록합니다.
16. 촬영 완료 후 최종 decode 폴더에 0..21 pattern id가 모두 있는지 검증합니다. 누락되면 오류를 띄우고 누락 id를 표시합니다.
17. 기존 14장 촬영 모드는 legacy 옵션으로 남겨도 되지만 기본 촬영 모드는 22장 + HDR merge로 합니다.
18. 저장된 최종 폴더는 이 디코더에서 `--gray-decode-mode auto`로 바로 사용할 수 있어야 합니다.

검증:

1. synthetic 또는 dry-run 모드로 22개 pattern id와 `scan_log.json`이 생성되는지 확인합니다.
2. 실제 Android 폰 카메라 연결 후 각 pattern마다 bracket 이미지와 merge 이미지가 모두 저장되는지 확인합니다.
3. `scan_log.json`에 pattern id, label, final filename, bracket filenames, exposure, ISO, focus metadata가 들어가는지 확인합니다.
4. 같은 평면을 기준/대상으로 연속 촬영했을 때 최종 디코더의 `height/delta_phase.npy`가 거의 0에 가까워져야 합니다.
