# PCB Structured-Light / FPP Decoder

PRO4500 / LightCrafter 4500 계열 structured-light 시스템에서 촬영한 14장 패턴 세트를 후처리하는 Python 도구입니다. 원본 `captures` 폴더는 읽기 전용으로 다루고, 모든 결과는 별도 `processed` 폴더에 저장합니다.

## 입력

입력 폴더는 다음 중 하나처럼 14장 이미지와 선택적 `scan_log.json`을 포함합니다.

```text
captures/scan_xxx/deg_0/
captures/scan_xxx/angle_000/
captures/scan_xxx/
```

패턴 순서는 다음과 같습니다.

```text
00 White, 01 Black
02..09 Gray0..Gray7  (8-bit Gray code, Gray0=MSB)
10 Sine_000, 11 Sine_090, 12 Sine_180, 13 Sine_270
```

`scan_log.json`에 pattern id와 파일명이 있으면 그것을 우선 사용합니다. 없으면 `pattern_000.png` 또는 `00_White.png`처럼 파일명에서 숫자를 추출합니다.

## CLI 실행

```bash
python scripts/decode_scan.py \
  --input captures/scan_xxx/deg_0 \
  --output processed/scan_xxx/deg_0 \
  --projector-width 1280 \
  --gray-bits 8 \
  --min-signal 20 \
  --saturation-threshold 250 \
  --dark-threshold 5 \
  --modulation-threshold 0.05 \
  --apply-half-period-correction \
  --detrend \
  --median-filter 3
```

Windows PowerShell에서는 줄바꿈 대신 한 줄로 실행하거나 백틱(`` ` ``)을 사용하세요.

## 간단 GUI

로컬 폴더 선택 UI가 필요하면 다음을 실행합니다.

```bash
python scripts/run_gui.py
```

입력 폴더와 출력 폴더를 선택하고 threshold를 조정한 뒤 `Run decode`를 누르면 같은 파이프라인이 실행됩니다.

## EXE 빌드

다른 Windows PC에서 사용할 실행 파일이 필요하면 프로젝트 루트에서 다음 파일을 실행합니다.

```bat
build.bat
```

빌드 스크립트는 `.venv`를 만들고 `requirements.txt`와 PyInstaller를 설치한 뒤 GUI 실행 파일과 보조 CLI 실행 파일을 생성합니다.

```text
dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe
dist/PCB_FPP_Decoder_CLI/PCB_FPP_Decoder_CLI.exe
```

일반 사용자는 `dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe`를 더블클릭하면 됩니다. 프로젝트 루트에서 `PCB_FPP_Decoder.vbs`를 더블클릭해도 같은 GUI를 실행합니다. GUI에서 입력/출력 폴더, reference phase/scan, calibration config, height mode를 선택할 수 있으므로 일반 사용자가 터미널에서 직접 명령을 입력할 필요는 없습니다.

다른 PC에 전달할 때는 `dist/PCB_FPP_Decoder` 폴더 전체를 복사하세요. 실행 PC에는 Python을 따로 설치하지 않아도 됩니다.

보조 CLI exe는 자동화나 디버깅이 필요할 때만 사용하며, `python scripts/decode_scan.py`와 같은 옵션을 받습니다. GUI와 CLI 모두 디코딩 후 `height/height_heatmap.png`, `point_cloud/point_cloud.ply`, `point_cloud/point_cloud_preview.png`를 생성합니다.

## 출력 구조

```text
processed/<scan_id>/deg_0/
  corrected/
  masks/
    valid_mask.png
    modulation_mask.png
    saturation_mask.png
    combined_mask.png
  phase/
    wrapped_phase.npy
    wrapped_phase_preview.png
    absolute_phase.npy
    absolute_phase_preview.png
    absolute_phase_before_correction_preview.png
    boundary_correction_mask.png
  gray/
    gray_bits.npy
    gray_code_value.npy
    stripe_order_k.npy
    stripe_order_preview.png
  height/
    height.npy
    height_relative.npy 또는 height_mm.npy
    height_heatmap.png
    height_heatmap_colorbar.png
  point_cloud/
    point_cloud.ply
    point_cloud_preview.png
  decode_report.json
```

## Height 해석

단일 14장 촬영만으로는 metric height(mm)를 안정적으로 계산할 수 없습니다. 기본 `relative` 모드는 absolute phase 또는 detrended phase를 높이처럼 시각화한 preview입니다. `decode_report.json`에도 `metric calibration missing; output is relative phase-derived preview, not physical height`가 기록됩니다.

Metric height를 얻으려면 다음 중 하나가 필요합니다.

- 기준 평면 scan 또는 `reference_absolute_phase.npy`
- camera/projector calibration
- baseline `l`, camera-reference distance `d`, pattern period 또는 등가 주기 `p`
- 또는 다중 reference plane으로 얻은 inverse-linear calibration 파라미터 `u, v, w`

예시 설정은 `examples/calibration_config.example.json`에 있습니다.

```bash
python scripts/decode_scan.py \
  --input captures/scan_xxx/deg_0 \
  --output processed/scan_xxx/deg_0 \
  --height-mode triangulation \
  --reference-phase processed/reference/deg_0/phase/absolute_phase.npy \
  --calibration-config examples/calibration_config.example.json \
  --height-sign 1
```

삼각측량식은 다음 convention을 사용합니다.

```text
h = sign * (delta_phi * p * d) / (delta_phi * p + 2*pi*l)
```

실제 시스템의 부호와 분모 convention은 geometry에 따라 달라질 수 있으므로 `--height-sign -1`과 calibration 파일의 단위를 확인하세요.

## 주요 옵션

- `--gray-threshold-mode dynamic_raw`: Gray 이미지를 `(White + Black) / 2` 동적 threshold와 비교합니다.
- `--gray-threshold-mode normalized_0p5`: White/Black 보정 후 0.5 기준으로 Gray bit를 이진화합니다.
- `--phase-convention default/negated/swapped`: 4-step PSP의 atan2 convention을 바꿉니다.
- `--phase-direction normal/reverse`: projector X 방향이 preview에서 반대로 보일 때 사용합니다.
- `--apply-half-period-correction`: Gray 경계와 PSP 경계 불일치에 대한 heuristic 보정을 적용합니다. 이는 정확한 Cai 2020 알고리즘 구현이 아니라 경계 연속성 기반 heuristic입니다.
- `--median-filter 3`: height/relative map에 median filter를 적용합니다.
- `--detrend`: valid pixel 전체에 plane fitting을 수행해 tilt를 제거합니다.

## Threshold 튜닝

- `min_signal`: White-Black 차이가 너무 낮은 shadow/black component 영역을 제거합니다.
- `modulation_threshold`: sine contrast가 낮은 픽셀을 제거합니다. corrected sine 기준 기본값은 `0.05`입니다.
- `saturation_threshold`: solder highlight처럼 white image에서 포화된 영역을 제거합니다.
- `median_filter`: isolated outlier가 많을 때 3 또는 5를 시도합니다.

PCB는 specular solder, black component, silk/metal 경계, shadow 때문에 잘못 decoded된 픽셀이 생기기 쉽습니다. 실제 height 해석 전에는 `combined_mask.png`, `stripe_order_preview.png`, `wrapped_phase_preview.png`, `absolute_phase_preview.png`를 반드시 확인하세요.

## 테스트

실제 이미지 없이 synthetic 14장 scan을 생성해 동작을 검증합니다.

```bash
pytest
```
