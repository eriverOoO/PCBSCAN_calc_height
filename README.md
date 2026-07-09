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

## Android 폰 촬영 입력

`PRO4500_Control_System`의 Android 촬영 워크플로는 보통 다음 구조를 만듭니다.

```text
captures/scan_YYYYMMDD_HHMMSS/
  angle_000/
    pattern_000.png
    ...
    pattern_021.png
    exposures/
    hdr_masks/
    scan_log.json
    hdr_merge_report.json
  angle_180/
    pattern_000.png
    ...
```

이제 `--input`에 스캔 루트를 넘겨도 decoder-ready `angle_000` 폴더를 자동으로 찾아 사용합니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input "C:\Users\shang\OneDrive\바탕 화면\PRO4500_Control_System\captures\scan_YYYYMMDD_HHMMSS" `
  --output processed\scan_YYYYMMDD_HHMMSS\angle_000 `
  --input-color-mode smartphone_uv_blue `
  --gray-decode-mode auto `
  --median-filter 3
```

다른 각도를 직접 지정하려면 `--input-angle 180`처럼 지정합니다. 같은 스캔 루트에 `angle_000`과 `angle_180`이 모두 있고 바로 통합하려면 `--auto-phone-fusion`을 사용할 수 있습니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input "C:\Users\shang\OneDrive\바탕 화면\PRO4500_Control_System\captures\scan_YYYYMMDD_HHMMSS" `
  --output processed\scan_YYYYMMDD_HHMMSS\fused `
  --auto-phone-fusion `
  --height-mode triangulation `
  --reference-scan "C:\Users\shang\OneDrive\바탕 화면\PRO4500_Control_System\captures\reference_scan" `
  --calibration-config examples\calibration_config.example.json
```

`scan_log.json`이 있으면 `decode_report.json`의 `phone_capture` 항목에 수동 노출/ISO, 수동 초점, AWB lock, HDR bracket, scan type, rig/calibration id, JPEG 사용 여부, 반전 Gray 누락 여부가 기록됩니다. 폰 촬영에서 경고가 없어야 한다는 뜻은 아니지만, height map을 해석하기 전에는 이 항목과 `masks/combined_mask.png`, `height/delta_phase_preview.png`를 함께 확인하세요.

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

### ArUco 마커 기반 회전 보정

로테이션 스테이지가 정확히 180.00도 회전하지 않는 경우에는 PCB에 붙인 ArUco 마커를 이용해 `deg_180` 영상을 `deg_0` 좌표계로 보정할 수 있습니다. 마커 이미지는 저장소에 포함하지 않고, 필요할 때 다음 명령으로 다시 생성합니다.

30 mm x 30 mm PCB의 대각 코너에 붙일 때는 마커 전체 크기가 15 mm 이내인 버전을 권장합니다. 아래 명령은 ID 0, ID 1 두 개를 A4 PDF로 만들며, 검은 ArUco 본체는 약 11.4 mm, 흰 여백 포함 전체 크기는 약 15 mm입니다.

```powershell
.venv\Scripts\python.exe scripts\generate_aruco_marker.py `
  --ids 0,1 `
  --dictionary DICT_4X4_50 `
  --marker-size-mm 11.4 `
  --quiet-zone-mm 1.8 `
  --dpi 300 `
  --format both `
  --no-label `
  --sheet a4 `
  --sheet-format both `
  --prefix aruco_total15mm `
  --sheet-prefix aruco_total15mm_sheet `
  --output aruco_markers_a4_total15mm
```

인쇄할 때는 프린터 배율을 `실제 크기` 또는 `100%`로 두고, `용지에 맞춤` 옵션은 끄세요. 생성된 `aruco_markers*`와 `markers` 폴더는 `.gitignore`에 포함되어 있으므로 출력물은 Git에 추가하지 않습니다.

촬영 후에는 White 프레임인 `pattern_000.png`에서 ID 0/1 마커를 검출해 fusion transform을 생성합니다.

```powershell
.venv\Scripts\python.exe scripts\estimate_aruco_fusion_transform.py `
  --input captures\scan_xxx\deg_0 `
  --input-180 captures\scan_xxx\deg_180 `
  --output processed\scan_xxx\aruco_fusion_transform.json `
  --ids 0,1 `
  --image pattern_000.png
```

그 다음 디코딩/통합 단계에서 생성된 JSON을 `--fusion-transform`에 전달합니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input captures\scan_xxx\deg_0 `
  --input-180 captures\scan_xxx\deg_180 `
  --output processed\scan_xxx\fused `
  --fusion-transform processed\scan_xxx\aruco_fusion_transform.json `
  --fusion-mode modulation-weighted
```

한 번의 디코딩 명령에서 ArUco 정합과 0/180 통합을 같이 수행할 수도 있습니다. 이 경우 transform은 출력 폴더의 `fusion/aruco_fusion_transform.json`에 저장되고, 그 보정 행렬이 곧바로 최종 height fusion에 사용됩니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input captures\scan_xxx\deg_0 `
  --input-180 captures\scan_xxx\deg_180 `
  --output processed\scan_xxx\fused `
  --fusion-registration aruco `
  --aruco-ids 0,1 `
  --aruco-image pattern_000.png `
  --aruco-method homography `
  --fusion-mode modulation-weighted
```

### Phase correlation 기반 평행 오차 보정

ArUco 마커 없이 로테이션 스테이지의 중심은 대략 맞지만, 180도 회전 후 이미지가 x/y 방향으로 몇 픽셀 밀리는 정도라면 phase correlation으로 잔여 평행 이동을 추정할 수 있습니다. 이 방법은 먼저 이론적 180도 회전 행렬을 적용한 뒤 남는 translation만 보정하므로, 실제 회전각 자체가 180도에서 크게 벗어나거나 원근 변형이 있으면 ArUco 기반 affine/homography 보정을 사용하세요.

```powershell
.venv\Scripts\python.exe scripts\estimate_phase_correlation_fusion_transform.py `
  --input captures\scan_xxx\deg_0 `
  --input-180 captures\scan_xxx\deg_180 `
  --output processed\scan_xxx\phase_fusion_transform.json `
  --image pattern_000.png
```

출력 JSON은 기존 `--fusion-transform` 입력과 같은 형식입니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input captures\scan_xxx\deg_0 `
  --input-180 captures\scan_xxx\deg_180 `
  --output processed\scan_xxx\fused `
  --fusion-transform processed\scan_xxx\phase_fusion_transform.json `
  --fusion-mode modulation-weighted
```

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

## Moreno-Taubin식 실장비 캘리브레이션 메타데이터

실제 카메라-프로젝터 리그에서 Moreno-Taubin local homography 방식으로 프로젝터 보정을 수행했다면 JSON 보정 파일에 `structured_light_calibration` 섹션을 함께 저장할 수 있습니다. 디코더는 이 값을 높이 계산식에 직접 대입하지는 않지만, `decode_report.json`의 `calibration.structured_light`와 `optical_setup.structured_light_calibration`에 캘리브레이션 품질을 기록합니다.

권장 절차는 다음 순서입니다.

```text
1. checkerboard 포즈별 white 이미지와 Gray code 시퀀스 촬영
2. white 이미지에서 카메라 체커보드 코너 검출 및 camera intrinsics 계산
3. Gray code 디코딩으로 camera pixel -> projector row/column 매핑 생성
4. 각 체커보드 코너 주변 47x47 px 패치에서 local homography 추정
5. 코너를 projector image domain의 sub-pixel 좌표로 변환
6. 변환된 projector 코너로 projector intrinsics/distortion 계산
7. camera/projector intrinsics를 고정하고 stereo extrinsics R/T 계산
```

예제 설정은 [examples/calibration_config.example.json](examples/calibration_config.example.json)에 들어 있습니다. 핵심 필드는 다음과 같습니다.

```json
"structured_light_calibration": {
  "method": "moreno_taubin_local_homography",
  "capture": {
    "pose_count": 12,
    "full_white_required": true,
    "gray_code_axes": ["x", "y"],
    "board_locked_during_sequence": true
  },
  "local_homography": {
    "patch_size_px": 47,
    "min_decoded_points": 1200
  },
  "reprojection_error": {
    "camera_rms_px": 0.12,
    "projector_rms_px": 0.18,
    "stereo_rms_px": 0.22,
    "target_max_px": 0.35
  }
}
```

PCB 납땜 반사 환경에서는 `target_max_px`를 보수적으로 0.35 px 전후로 두고, camera/projector/stereo RMS 중 하나라도 초과하면 다시 촬영하는 쪽이 안전합니다. white 이미지가 포화되지 않도록 노출을 낮추고, black 이미지가 노이즈 바닥에 묻히지 않게 조명을 조절하세요. 납땜부 glare가 Gray code를 깨뜨리면 카메라/프로젝터 편광필터를 교차 배치하고, 확산판은 Gray code 경계가 흐려지지 않는 범위에서만 사용하세요.

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
