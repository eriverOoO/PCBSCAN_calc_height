# PCB Structured-Light / FPP Decoder

PRO4500 / LightCrafter 4500 계열 구조광 시스템에서 촬영한 14장 패턴 세트를 전처리하고, Gray code + 4-step phase shifting으로 PCB 높이 지도를 복원하는 Python 도구입니다. 원본 `captures` 폴더는 읽기 전용으로 두고 모든 결과는 별도 `processed` 폴더에 저장합니다.

## 핵심 운영 원칙

30도 정도 기울여 투사하면 PCB 위 패턴은 가까운 쪽이 좁고 먼 쪽이 넓은 사다리꼴로 맺힙니다. 이 시스템은 프로젝터 이미지를 억지로 펴는 keystone pre-distortion을 하지 않습니다.

- 초점 흐려짐: PRO4500/렌즈/리그의 Scheimpflug 또는 수동 초점 정렬로 하드웨어에서 해결합니다. 디코더는 초점이 맞지 않은 영역을 소프트웨어로 deblur하지 않습니다.
- 사다리꼴 기하 왜곡: 같은 프로젝터/카메라/리그 상태에서 먼저 촬영한 평면 reference phase를 사용해 `delta_phi = phi_object - phi_reference`로 제거합니다.
- Metric height: `triangulation` 또는 `inverse-linear` 모드는 reference phase가 없으면 실행하지 않고 에러를 냅니다.
- 위치별 줄무늬 간격: 30도 투사로 `p`, `d`, `l`이 위치별로 달라지는 경우 `.npz` calibration 파일에 `p`, `d`, `l` 맵을 넣어 사용할 수 있습니다.

## 입력

입력 폴더에는 14장 이미지와 선택적 `scan_log.json`이 들어갑니다.

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
14..21 Gray0_inv..Gray7_inv  (optional inverted Gray pair)
```

`scan_log.json`에 pattern id와 파일명이 있으면 우선 사용합니다. 없으면 `pattern_000.png` 또는 `00_White.png`처럼 파일명에서 숫자를 추출합니다.
14..21 반전 Gray가 있으면 기본 `--gray-decode-mode auto`에서 자동으로 normal/inverted pair decoding을 사용합니다.

## CLI 실행

상대 위상 preview만 만들 때:

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

기준 평면을 빼서 metric height를 계산할 때:

```bash
python scripts/decode_scan.py \
  --input captures/scan_xxx/deg_0 \
  --output processed/scan_xxx/deg_0 \
  --height-mode triangulation \
  --reference-phase processed/reference/deg_0/phase/absolute_phase.npy \
  --calibration-config examples/calibration_config.example.json \
  --height-sign 1
```

Windows PowerShell에서는 줄바꿈 문자가 다르므로 한 줄로 실행하거나 백틱(`)을 사용하세요.

## 0도 / 180도 데이터 융합

PCB를 정방향으로 한 번, 180도 회전해 한 번 촬영한 경우 `--input-180`을 추가하면 두 높이 지도를 정렬하고 융합합니다.

```bash
python scripts/decode_scan.py \
  --input captures/scan_xxx/deg_0 \
  --input-180 captures/scan_xxx/deg_180 \
  --output processed/scan_xxx/fused \
  --height-mode triangulation \
  --reference-phase processed/reference/deg_0/phase/absolute_phase.npy \
  --calibration-config examples/calibration_config.example.json \
  --fusion-mode modulation-weighted
```

`deg_180` 높이 지도는 기본적으로 이미지 중심 `((width-1)/2, (height-1)/2)` 기준 180도 회전 행렬로 `deg_0` 좌표계에 정렬됩니다. 회전 중심을 알고 있으면 `--fusion-center X Y`를 지정하고, 보정 타겟으로 구한 2x3 affine 또는 3x3 homography가 있으면 `--fusion-transform transform.json` 또는 `.npy/.npz` 파일을 지정합니다.

최종 fusion 규칙은 픽셀 단위입니다. 한쪽만 valid이면 그 값을 사용하고, 양쪽 모두 valid이면 기본값 `modulation-weighted`에서 sine modulation 신뢰도 가중 평균을 사용합니다. 단순 평균이 필요하면 `--fusion-mode average`를 사용하세요. fusion 실행 시 개별 scan 결과는 `views/deg_0`, `views/deg_180`에 저장되고, 최종 결과는 출력 루트의 `height/height_fused.npy`, `height/height_heatmap.png`, `point_cloud/point_cloud.ply`, `masks/source_*.png`에 저장됩니다.

## GUI

```bash
python scripts/run_gui.py
```

입력/출력 폴더, reference phase/scan, calibration config, height mode, threshold를 선택한 뒤 `Run decode`를 누르면 같은 파이프라인이 실행됩니다. `reference`, `triangulation`, `inverse-linear` 모드에서는 reference phase 또는 reference scan이 필요합니다.

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

일반 사용자는 `dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe`를 더블클릭하면 됩니다. 프로젝트 루트에서 `PCB_FPP_Decoder.vbs`를 더블클릭해도 같은 GUI를 실행합니다. 다른 PC에 전달할 때는 `dist/PCB_FPP_Decoder` 폴더 전체를 복사하세요. 실행 PC에는 Python을 따로 설치하지 않아도 됩니다.

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
    delta_phase.npy                 # reference 사용 시 저장
    delta_phase_preview.png         # reference 사용 시 저장
    height_heatmap.png
    height_heatmap_colorbar.png
  point_cloud/
    point_cloud.ply
    point_cloud_preview.png
  decode_report.json
```

`decode_report.json`에는 `optical_setup` 항목이 기록됩니다. 여기에서 reference subtraction 활성 여부, reference 경로, `height/delta_phase.npy` 저장 여부, 위치별 calibration map 로딩 여부를 확인할 수 있습니다.

## Height 해석

단일 14장 촬영만으로는 metric height(mm)를 안정적으로 계산할 수 없습니다. 기본 `relative` 모드는 absolute phase 또는 detrended phase를 높이처럼 시각화한 preview입니다.

Metric height를 얻으려면 다음이 필요합니다.

- 평평한 기준면 scan 또는 `absolute_phase.npy`
- camera/projector calibration
- baseline `l`, camera-reference distance `d`, pattern period 또는 등가 주기 `p`
- 또는 다중 reference plane으로 얻은 inverse-linear 파라미터 `u`, `v`, `w`

삼각측량식은 다음 convention을 사용합니다.

```text
h = sign * (delta_phi * p * d) / (delta_phi * p + 2*pi*l)
delta_phi = phi_object - phi_reference
```

실제 시스템의 부호와 분모 convention은 geometry에 따라 달라질 수 있으므로 `--height-sign -1`과 calibration 파일의 단위를 확인하세요.

## 위치별 Calibration Map

JSON 파일은 스칼라 `d`, `l`, `p` 값을 담는 용도에 적합합니다. 투사 각도 때문에 위치별 줄무늬 간격 변화가 크면 `.npz` 파일을 사용해 같은 이미지 shape로 `d`, `l`, `p` 배열을 저장하세요.

```python
import numpy as np

np.savez(
    "calibration_maps.npz",
    d=np.full((H, W), 300.0, dtype=np.float32),
    l=np.full((H, W), 120.0, dtype=np.float32),
    p=p_map.astype(np.float32),
)
```

배열은 phase image shape로 broadcast 가능해야 합니다. 예를 들어 `p`는 `(H, W)`, `d`와 `l`은 스칼라도 가능합니다.

## 주요 옵션

- `--gray-threshold-mode dynamic_raw`: Gray 이미지를 `(White + Black) / 2` 동적 threshold와 비교합니다.
- `--gray-threshold-mode normalized_0p5`: White/Black 보정 후 0.5 기준으로 Gray bit를 이진화합니다.
- `--gray-decode-mode auto/normal/inverted_pair`: 14..21 반전 Gray가 있으면 `auto`에서 pair decoding을 사용합니다.
- `--gray-pair-min-contrast 0.05`: normal/inverted Gray pair의 최소 normalized 차이입니다.
- `--phase-convention default/negated/swapped`: 4-step PSP의 atan2 convention을 바꿉니다.
- `--phase-direction normal/reverse`: projector X 방향이 preview에서 반대로 보일 때 사용합니다.
- `--apply-half-period-correction`: Gray 경계와 PSP 경계 불일치에 대한 heuristic 보정입니다.
- `--median-filter 3`: height/relative map에 median filter를 적용합니다.
- `--detrend`: valid pixel 전체에 plane fitting을 수행해 tilt를 제거합니다.

PCB의 specular solder, black component, silk/metal 경계, shadow 때문에 잘못 decode되는 픽셀이 생길 수 있습니다. 실제 height 해석 전 `combined_mask.png`, `stripe_order_preview.png`, `wrapped_phase_preview.png`, `absolute_phase_preview.png`, `delta_phase_preview.png`를 확인하세요.

## 테스트

```bash
pytest
```
