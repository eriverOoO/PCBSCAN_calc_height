# PCB 구조광/FPP 디코더

이 프로젝트는 PRO4500 또는 LightCrafter 4500 계열 구조광 시스템으로 촬영한 PCB 패턴 이미지를 전처리하고, Gray code와 4-step phase shifting을 이용해 위상 및 높이 지도를 복원하는 Python 도구입니다.

기본 입력은 `captures` 폴더 아래의 촬영 세트이고, 처리 결과는 별도의 `processed` 폴더에 저장하는 구성을 권장합니다.

## 광학 설정 메모

프로젝터를 약 30도 기울여 조사하면 PCB에서 가까운 쪽과 먼 쪽의 초점, 줄무늬 간격, 투영 기하가 달라질 수 있습니다. 이 디코더는 프로젝터 이미지를 사전에 왜곡하는 keystone pre-distortion을 기본 가정으로 사용하지 않습니다.

- 초점 문제는 PRO4500, 렌즈, 리그 쪽에서 Scheimpflug 또는 수동 초점 정렬로 해결하는 것을 권장합니다. 디코더는 초점이 맞지 않은 영역을 소프트웨어 deblur로 복구하지 않습니다.
- 사다리꼴 기하 성분은 같은 프로젝터/카메라 리그에서 평면 기준 영상을 먼저 촬영한 뒤 `delta_phi = phi_object - phi_reference`로 제거합니다.
- `triangulation` 또는 `inverse-linear` 높이 모드는 기준 위상이 없으면 실행하지 않고 오류를 냅니다.
- 30도 기울기로 인해 위치별 줄무늬 간격이나 기하 파라미터가 달라지는 경우 `.npz` calibration 파일에 `p`, `d`, `l` 맵을 넣어 사용할 수 있습니다.

## 입력 데이터

입력 폴더는 다음과 같은 형태를 사용할 수 있습니다.

```text
captures/scan_xxx/deg_0/
captures/scan_xxx/angle_000/
captures/scan_xxx/
```

기본 패턴 순서는 다음과 같습니다.

```text
00 White, 01 Black
02..09 Gray0..Gray7  (8-bit Gray code, Gray0=MSB)
10 Sine_000, 11 Sine_090, 12 Sine_180, 13 Sine_270
14..21 Gray0_inv..Gray7_inv  (선택 사항인 반전 Gray pair)
```

`scan_log.json`에 pattern id와 파일명이 있으면 그 정보를 우선 사용합니다. 로그가 없으면 `pattern_000.png` 또는 `00_White.png`처럼 파일명에 들어 있는 숫자에서 pattern id를 추출합니다.

14..21번 반전 Gray 패턴이 있으면 기본값인 `--gray-decode-mode auto`에서 자동으로 정상/반전 쌍 디코딩을 사용합니다.

## 명령줄 실행

먼저 높이 미리보기만 만들 때의 예시는 다음과 같습니다.

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

평면 기준 위상을 빼서 물리 단위 높이를 계산할 때의 예시는 다음과 같습니다.

```bash
python scripts/decode_scan.py \
  --input captures/scan_xxx/deg_0 \
  --output processed/scan_xxx/deg_0 \
  --height-mode triangulation \
  --reference-phase processed/reference/deg_0/phase/absolute_phase.npy \
  --calibration-config examples/calibration_config.example.json \
  --height-sign 1
```

Windows PowerShell에서는 위 예시의 `\` 대신 한 줄로 실행하거나 줄바꿈 문자로 backtick(`)을 사용하세요.

## 0도/180도 데이터 통합

PCB를 정방향으로 한 번, 180도 회전해서 한 번 촬영한 경우 `--input-180`을 추가하면 두 높이 지도를 정렬하고 통합합니다.

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

`deg_180` 높이 지도는 기본적으로 이미지 중심 `((width - 1) / 2, (height - 1) / 2)` 기준 180도 회전 행렬로 `deg_0` 좌표계에 정렬합니다. 회전 중심을 알고 있으면 `--fusion-center X Y`를 지정할 수 있고, 별도 보정으로 구한 2x3 affine 또는 3x3 homography가 있으면 `--fusion-transform transform.json` 또는 `.npy/.npz` 파일을 지정할 수 있습니다.

최종 통합 규칙은 픽셀 단위입니다. 한쪽만 valid이면 해당 값을 사용하고, 양쪽 모두 valid이면 기본 `modulation-weighted` 모드에서 sine modulation 신뢰도로 가중 평균합니다. 단순 평균이 필요하면 `--fusion-mode average`를 사용하세요.

통합 실행 후 개별 scan 결과는 `views/deg_0`, `views/deg_180`에 저장되고, 최종 결과는 출력 루트의 `height/height_fused.npy`, `height/height_heatmap.png`, `point_cloud/point_cloud.ply`, `masks/source_*.png` 등에 저장됩니다.

## 그래픽 화면 실행

```bash
python scripts/run_gui.py
```

그래픽 화면에서는 입력/출력 폴더, 기준 scan 또는 기준 phase, 보정 설정 파일, 높이 모드, 임계값을 선택한 뒤 `Run decode`를 누르면 같은 파이프라인이 실행됩니다. `reference`, `triangulation`, `inverse-linear` 모드에서는 기준 phase 또는 기준 scan이 필요합니다.

## 실행 파일 빌드

다른 Windows PC에서 사용할 실행 파일이 필요하면 프로젝트 루트에서 다음 파일을 실행합니다.

```bat
build.bat
```

빌드 스크립트는 `.venv`를 만들고 `requirements.txt`와 PyInstaller를 설치한 뒤 그래픽 화면 실행 파일과 보조 명령줄 실행 파일을 생성합니다.

```text
dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe
dist/PCB_FPP_Decoder_CLI/PCB_FPP_Decoder_CLI.exe
```

일반 사용자는 `dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe`를 더블 클릭하면 됩니다. 프로젝트 루트의 `PCB_FPP_Decoder.vbs`를 더블 클릭해도 같은 그래픽 화면이 실행됩니다. 다른 PC로 전달할 때는 `dist/PCB_FPP_Decoder` 폴더 전체를 복사하세요. 실행 PC에는 Python을 별도로 설치하지 않아도 됩니다.

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
    gray_confidence.npy
    gray_valid_mask.png
    gray_confidence_preview.png
    stripe_order_preview.png
  height/
    height.npy
    height_relative.npy 또는 height_mm.npy
    delta_phase.npy
    delta_phase_preview.png
    height_heatmap.png
    height_heatmap_colorbar.png
    height_relative_preview.png
  point_cloud/
    point_cloud.ply
    point_cloud_preview.png
  decode_report.json
```

`decode_report.json`에는 `optical_setup` 항목이 기록됩니다. 여기서 기준 위상 차감 사용 여부, 기준 데이터 경로, `height/delta_phase.npy` 저장 여부, 위치별 보정 맵 로딩 여부를 확인할 수 있습니다.

## 높이 해석

단일 14장 또는 22장 촬영만으로는 물리 단위 높이(mm)를 안정적으로 계산하기 어렵습니다. 기본 `relative` 모드는 절대 위상 또는 기울기 제거 위상을 높이처럼 시각화한 미리보기입니다.

물리 단위 높이를 얻으려면 다음 정보가 필요합니다.

- 평면 기준 scan 또는 `absolute_phase.npy`
- camera/projector calibration
- 기준선 `l`, 카메라-기준면 거리 `d`, 패턴 주기 또는 등가 주기 `p`
- 또는 여러 reference plane으로 얻은 inverse-linear 파라미터 `u`, `v`, `w`

삼각측량 방식은 다음 convention을 사용합니다.

```text
h = sign * (delta_phi * p * d) / (delta_phi * p + 2*pi*l)
delta_phi = phi_object - phi_reference
```

실제 시스템의 부호와 분모 규약은 기하 구성에 따라 달라질 수 있으므로 `--height-sign -1`과 보정 파일 단위를 확인하세요.

## 위치별 보정 맵

JSON 파일은 스칼라 `d`, `l`, `p` 값을 넣는 용도에 적합합니다. 사사각도 때문에 위치별 줄무늬 간격 변화가 크면 `.npz` 파일을 사용해 같은 이미지 shape의 `d`, `l`, `p` 배열을 저장하세요.

```python
import numpy as np

np.savez(
    "calibration_maps.npz",
    d=np.full((H, W), 300.0, dtype=np.float32),
    l=np.full((H, W), 120.0, dtype=np.float32),
    p=p_map.astype(np.float32),
)
```

배열은 위상 이미지 shape로 브로드캐스트 가능해야 합니다. 예를 들어 `p`는 `(H, W)`이고 `d`, `l`은 스칼라여도 사용할 수 있습니다.

## 주요 옵션

- `--gray-threshold-mode dynamic_raw`: Gray 이미지를 `(White + Black) / 2` 동적 threshold와 비교합니다.
- `--gray-threshold-mode normalized_0p5`: White/Black 보정 후 0.5 기준으로 Gray bit를 이진화합니다.
- `--gray-decode-mode auto/normal/inverted_pair`: 14..21 반전 Gray가 있으면 `auto`에서 쌍 디코딩을 사용합니다.
- `--gray-pair-min-contrast 0.05`: 정상/반전 Gray 쌍의 최소 정규화 차이입니다.
- `--phase-convention default/negated/swapped`: 4-step PSP의 atan2 convention을 바꿉니다.
- `--phase-direction normal/reverse`: projector X 방향이 미리보기에서 반대로 보일 때 사용합니다.
- `--apply-half-period-correction`: Gray 경계와 PSP 경계 불일치를 휴리스틱으로 보정합니다.
- `--median-filter 3`: height 또는 relative map에 median filter를 적용합니다.
- `--detrend`: 유효 픽셀 전체에 평면 맞춤을 수행해 기울기를 제거합니다.

PCB의 반사성 납땜부, 검은 부품, 실크/금속 경계, 그림자 때문에 잘못 디코딩되는 영역이 생길 수 있습니다. 실제 높이를 해석하기 전에 `combined_mask.png`, `stripe_order_preview.png`, `wrapped_phase_preview.png`, `absolute_phase_preview.png`, `delta_phase_preview.png`를 확인하세요.

## 테스트

```bash
pytest
```
