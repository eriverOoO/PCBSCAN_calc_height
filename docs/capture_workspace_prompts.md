# Capture Workspace Implementation Prompts

아래 프롬프트는 현재 디코더 워크스페이스(`Non-planar_calc`)와 맞물리도록 작성했다. 두 촬영 워크스페이스의 차이는 카메라 제어 도구뿐이며, 저장 포맷과 pattern id 규약은 동일하게 맞춘다.

## 공통 Decoder Contract

현재 디코더가 기대하는 최종 decode 입력 폴더는 다음 pattern id를 가진 grayscale 이미지와 `scan_log.json`이다.

```text
00 White
01 Black
02 Gray0      03 Gray1      04 Gray2      05 Gray3
06 Gray4      07 Gray5      08 Gray6      09 Gray7
10 Sine_000   11 Sine_090   12 Sine_180   13 Sine_270
14 Gray0_inv  15 Gray1_inv  16 Gray2_inv  17 Gray3_inv
18 Gray4_inv  19 Gray5_inv  20 Gray6_inv  21 Gray7_inv
```

`14..21`은 선택이지만 새 촬영 파이프라인에서는 기본으로 촬영한다. 최종 합성 이미지는 `pattern_000.png` .. `pattern_021.png`처럼 저장하고, `scan_log.json`에는 각 이미지의 `pattern_id`, `label`, `filename`, exposure/gain/merge metadata를 기록한다.

Reference plane scan과 object scan은 같은 projector angle, focus, camera pose, exposure bracket preset, projector brightness 조건에서 촬영되어야 한다.

## Prompt: PRO4500_Control_System-UV

작업공간: `C:\Users\shang\OneDrive\바탕 화면\PRO4500_Control_System-UV`

목표: XIMEA UV 카메라 + PRO4500 구조광 촬영 시스템에 반전 Gray code 촬영과 멀티 노출 HDR 저장/합성 기능을 추가한다. 현재 디코더 워크스페이스 `Non-planar_calc`가 읽을 수 있는 최종 패턴 폴더를 생성해야 한다.

구현 요구사항:

1. 기존 14장 패턴 촬영에 `Gray0_inv..Gray7_inv` 8장을 추가해 총 22개 pattern id를 지원한다.
2. pattern id 규약은 반드시 다음을 따른다: `0 White`, `1 Black`, `2..9 Gray0..Gray7`, `10..13 Sine_000..Sine_270`, `14..21 Gray0_inv..Gray7_inv`.
3. 반전 Gray는 기존 Gray pattern의 logical inverse여야 한다. projector gamma나 intensity scale 보정이 있더라도 동일 조건에서 normal/inverted가 한 쌍으로 대응되게 만든다.
4. 촬영 순서는 하드웨어 안정성에 맞게 정해도 되지만 `scan_log.json`의 `pattern_id`가 정확하면 된다. 권장 순서는 `White`, `Black`, `Gray0`, `Gray0_inv`, ..., `Gray7`, `Gray7_inv`, `Sine_000`, `Sine_090`, `Sine_180`, `Sine_270`이다.
5. XIMEA UV 카메라는 manual exposure/gain 모드로 제어한다. 자동 exposure, 자동 gain, 자동 white balance, 자동 focus가 있다면 모두 끈다.
6. 각 pattern id마다 멀티 노출 bracket을 촬영한다. 기본 preset 예시는 `short`, `mid`, `long` 3단계이며 설정값은 config 파일에서 바꿀 수 있게 한다.
7. 각 exposure frame은 raw 보존용 하위 폴더에 저장한다. 예: `exposures/pattern_002/short.png`, `mid.png`, `long.png`.
8. HDR merge 결과는 디코더 입력 루트에 `pattern_002.png`처럼 저장한다.
9. HDR merge 알고리즘은 per-pixel로 “포화되지 않은 가장 긴 노출”을 우선 선택하고, intensity를 exposure time/gain 기준으로 radiance normalize한 뒤 최종 8-bit 또는 16-bit grayscale로 스케일한다.
10. saturated threshold, dark threshold, exposure_us, gain_db, projector pattern label, capture timestamp를 `scan_log.json` 또는 `hdr_merge_report.json`에 기록한다.
11. merge 중 모든 bracket이 포화된 픽셀과 모든 bracket이 너무 어두운 픽셀의 mask를 저장한다. 예: `hdr_masks/pattern_002_saturated.png`, `hdr_masks/pattern_002_dark.png`.
12. reference plane 촬영 모드를 추가한다. 출력 폴더 이름 또는 metadata에 `scan_type: "reference"`를 기록한다.
13. object 촬영 모드를 추가한다. 출력 폴더 이름 또는 metadata에 `scan_type: "object"`를 기록한다.
14. reference/object 모두 projector tilt 30도, Scheimpflug/manual focus 확인 상태, rig/calibration id를 metadata에 기록할 수 있게 한다.
15. projector keystone pre-distortion은 기본으로 하지 않는다. metadata에 `keystone_predistortion: false`를 기록한다.
16. 촬영 완료 후 최종 decode 폴더에 0..21 pattern id가 모두 있는지 검증한다. 누락되면 에러를 띄우고 어느 id가 없는지 표시한다.
17. 기존 14장 촬영 모드는 legacy 옵션으로 남겨도 되지만, 기본 촬영 모드는 22장 + HDR merge로 한다.
18. 저장된 최종 폴더는 `Non-planar_calc`의 디코더에서 `--gray-decode-mode auto`로 바로 읽혀야 한다.

검증:

1. synthetic 또는 dry-run 모드로 22개 pattern id와 `scan_log.json`이 생성되는지 확인한다.
2. 실제 XIMEA UV 카메라 연결 시 각 pattern마다 bracket 이미지와 merge 이미지가 모두 저장되는지 확인한다.
3. `scan_log.json`에 pattern id, label, final filename, bracket filenames, exposure_us, gain_db가 들어가는지 확인한다.
4. 같은 평면을 reference/object로 연속 촬영했을 때 최종 디코더의 `height/delta_phase.npy`가 거의 0에 가까워야 한다.

## Prompt: PRO4500_Control_System

작업공간: `C:\Users\shang\OneDrive\바탕 화면\PRO4500_Control_System`

목표: Android 폰 카메라 + PRO4500 구조광 촬영 시스템에 반전 Gray code 촬영과 멀티 노출 HDR 저장/합성 기능을 추가한다. 현재 디코더 워크스페이스 `Non-planar_calc`가 읽을 수 있는 최종 패턴 폴더를 생성해야 한다.

구현 요구사항:

1. 기존 14장 패턴 촬영에 `Gray0_inv..Gray7_inv` 8장을 추가해 총 22개 pattern id를 지원한다.
2. pattern id 규약은 반드시 다음을 따른다: `0 White`, `1 Black`, `2..9 Gray0..Gray7`, `10..13 Sine_000..Sine_270`, `14..21 Gray0_inv..Gray7_inv`.
3. 반전 Gray는 기존 Gray pattern의 logical inverse여야 한다. projector gamma나 intensity scale 보정이 있더라도 동일 조건에서 normal/inverted가 한 쌍으로 대응되게 만든다.
4. 촬영 순서는 하드웨어 안정성에 맞게 정해도 되지만 `scan_log.json`의 `pattern_id`가 정확하면 된다. 권장 순서는 `White`, `Black`, `Gray0`, `Gray0_inv`, ..., `Gray7`, `Gray7_inv`, `Sine_000`, `Sine_090`, `Sine_180`, `Sine_270`이다.
5. Android 폰 카메라는 가능한 경우 Camera2/manual capture 또는 기존 프로젝트의 Android 제어 경로를 사용해 manual exposure/ISO/focus로 고정한다. AE, AWB, AF가 켜져 있으면 pattern 간 밝기와 위상이 흔들리므로 촬영 시작 전에 lock한다.
6. 각 pattern id마다 멀티 노출 bracket을 촬영한다. 기본 preset 예시는 `short`, `mid`, `long` 3단계이며 설정값은 config 파일에서 바꿀 수 있게 한다.
7. 각 exposure frame은 raw 보존용 하위 폴더에 저장한다. 예: `exposures/pattern_002/short.png`, `mid.png`, `long.png`.
8. HDR merge 결과는 디코더 입력 루트에 `pattern_002.png`처럼 저장한다.
9. HDR merge 알고리즘은 per-pixel로 “포화되지 않은 가장 긴 노출”을 우선 선택하고, intensity를 exposure time/ISO 기준으로 radiance normalize한 뒤 최종 8-bit 또는 16-bit grayscale로 스케일한다.
10. saturated threshold, dark threshold, exposure_ns 또는 exposure_us, ISO, focus distance, projector pattern label, capture timestamp를 `scan_log.json` 또는 `hdr_merge_report.json`에 기록한다.
11. merge 중 모든 bracket이 포화된 픽셀과 모든 bracket이 너무 어두운 픽셀의 mask를 저장한다. 예: `hdr_masks/pattern_002_saturated.png`, `hdr_masks/pattern_002_dark.png`.
12. reference plane 촬영 모드를 추가한다. 출력 폴더 이름 또는 metadata에 `scan_type: "reference"`를 기록한다.
13. object 촬영 모드를 추가한다. 출력 폴더 이름 또는 metadata에 `scan_type: "object"`를 기록한다.
14. reference/object 모두 projector tilt 30도, manual focus 확인 상태, phone mount/calibration id를 metadata에 기록할 수 있게 한다.
15. projector keystone pre-distortion은 기본으로 하지 않는다. metadata에 `keystone_predistortion: false`를 기록한다.
16. 촬영 완료 후 최종 decode 폴더에 0..21 pattern id가 모두 있는지 검증한다. 누락되면 에러를 띄우고 어느 id가 없는지 표시한다.
17. 기존 14장 촬영 모드는 legacy 옵션으로 남겨도 되지만, 기본 촬영 모드는 22장 + HDR merge로 한다.
18. 저장된 최종 폴더는 `Non-planar_calc`의 디코더에서 `--gray-decode-mode auto`로 바로 읽혀야 한다.

검증:

1. synthetic 또는 dry-run 모드로 22개 pattern id와 `scan_log.json`이 생성되는지 확인한다.
2. 실제 Android 폰 카메라 연결 시 각 pattern마다 bracket 이미지와 merge 이미지가 모두 저장되는지 확인한다.
3. `scan_log.json`에 pattern id, label, final filename, bracket filenames, exposure, ISO, focus metadata가 들어가는지 확인한다.
4. 같은 평면을 reference/object로 연속 촬영했을 때 최종 디코더의 `height/delta_phase.npy`가 거의 0에 가까워야 한다.
