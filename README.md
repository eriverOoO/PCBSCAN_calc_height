# PCB 구조광/FPP 디코더

이 프로젝트는 PRO4500 또는 LightCrafter 4500 계열 구조광 시스템으로 촬영한 PCB 패턴 이미지를 전처리하고, Gray code와 4-step phase shifting을 이용해 위상 및 높이 지도를 복원하는 Python 도구입니다.

## 하드웨어 트리거 촬영 계약

정밀 계측 모드에서는 프로젝터의 pattern advance와 카메라 exposure를 같은 하드웨어 trigger line으로 묶어야 합니다. 이 저장소에는 카메라/프로젝터 SDK 제어기가 포함되지 않으므로, 제어기는 촬영 후 각 view의 `scan_log.json`에 아래 증거를 기록해야 합니다. `--require-hardware-capture`를 주면 이 증거가 없거나 자동 노출/감마가 켜진 촬영은 디코딩하지 않습니다.

```json
{
  "capture_contract_version": 1,
  "status": "ok",
  "capture_protocol": {
    "sequence_locked": true,
    "projector_pattern_advance": "hardware_trigger",
    "camera_exposure": "hardware_trigger",
    "trigger_source": "PRO4500.TRIG_OUT -> XIMEA.GPI_1"
  },
  "settings": {
    "auto_exposure": false,
    "auto_gain": false,
    "auto_white_balance": false,
    "gamma_enabled": false,
    "output_linear": true,
    "exposure_mode": "manual",
    "gain_mode": "manual",
    "focus_mode": "manual",
    "pixel_format": "Mono8"
  },
  "rows": [{"pattern_id": 0, "filename": "pattern_000.png", "sequence_index": 0, "trigger_id": "trigger-000"}]
}
```

`rows`에는 사용한 모든 필수 패턴(최소 0..13)을 한 번씩, 순서대로 기록해야 합니다. `trigger_id`는 카메라가 실제 수신한 exposure event의 식별자여야 합니다.

```powershell
python scripts\verify_hardware_capture.py --input captures\scan_xxx\deg_0
python scripts\decode_scan.py --input captures\scan_xxx\deg_0 --output processed\scan_xxx\deg_0 --require-hardware-capture
python scripts\review_scan_results.py --capture captures\scan_xxx\deg_0 --processed processed\scan_xxx\deg_0
```

마지막 명령은 `scan_review.json`을 생성합니다. 이후 촬영 폴더와 처리 폴더(또는 이 파일)를 공유하면 trigger/설정 증거, 디코더의 유효 픽셀 비율, capture diagnosis를 함께 재검토할 수 있습니다.

기본 입력은 `captures` 폴더 아래의 촬영 세트이고, 처리 결과는 별도의 `processed` 폴더에 저장하는 구성을 권장합니다.

## 처음 사용하는 사람을 위한 사용법

이 프로그램을 전달받은 사용자는 보통 Python 코드를 직접 다루지 않고 Windows 실행 파일로 사용합니다. 배포 폴더를 받은 경우 `dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe`를 실행하세요. 개발용 소스 폴더를 받은 경우에는 먼저 [실행 파일 빌드](#실행-파일-빌드)를 따라 EXE를 만든 뒤 같은 파일을 실행하면 됩니다.

### 1. 입력 스캔 준비

디코더가 읽을 수 있는 입력은 한 번의 촬영에 해당하는 패턴 이미지 묶음입니다. 최소한 0..13번 패턴이 필요하고, 14..21번 반전 Gray 패턴이 있으면 더 안정적으로 동작합니다.

```text
pattern_000.png  White
pattern_001.png  Black
pattern_002.png  Gray0
...
pattern_009.png  Gray7
pattern_010.png  Sine_000
pattern_011.png  Sine_090
pattern_012.png  Sine_180
pattern_013.png  Sine_270
pattern_014.png..pattern_021.png  Gray0_inv..Gray7_inv
```

촬영 프로그램이 `scan_log.json`을 함께 저장했다면 파일명이 조금 달라도 됩니다. 이 경우 디코더는 `scan_log.json`에 기록된 `pattern_id`와 파일 경로를 우선 사용합니다. 로그가 없다면 파일명에 `pattern_000.png`처럼 pattern id가 들어 있어야 합니다.

입력 폴더 예시는 다음 중 하나처럼 구성할 수 있습니다.

```text
captures/<scan_id>/pattern_000.png
captures/<scan_id>/angle_000/pattern_000.png
captures/<scan_id>/deg_0/pattern_000.png
```

`angle_000`, `deg_0`처럼 각도별 하위 폴더가 있는 경우 스캔 루트 폴더를 선택해도 디코더가 사용할 수 있는 하위 폴더를 자동으로 찾습니다.

### 2. GUI로 디코딩하기

가장 쉬운 사용 방법은 그래픽 화면입니다.

1. `PCB_FPP_Decoder.exe`를 실행합니다.
2. `입력 스캔 폴더`에 촬영 이미지가 들어 있는 폴더를 선택합니다.
3. `출력 폴더`에는 결과를 저장할 새 폴더를 선택합니다.
4. 우선 높이 모드는 `relative`로 둔 채 실행해 입력 데이터가 정상인지 확인합니다.
5. 기준 평면을 촬영해 둔 경우 `Reference scan` 또는 `Reference phase`를 지정하고 `reference`, `triangulation`, `inverse-linear` 중 필요한 높이 모드를 선택합니다.
6. 물리 단위 높이(mm 등)가 필요하면 `Calibration config`에 보정 JSON 또는 NPZ 파일을 지정하고 `triangulation` 또는 `inverse-linear` 모드를 사용합니다.
7. `Run decode`를 누릅니다.
8. 완료 후 표시되는 valid ratio와 heat map 경로를 확인합니다.

처음 실행할 때는 기본값으로 충분합니다. 결과가 너무 많이 비어 있으면 `Min signal`, `Saturation threshold`, `Dark threshold`, `Modulation threshold`를 촬영 조건에 맞게 조정합니다. PCB 반사나 그림자가 많은 경우에는 threshold를 낮추기보다 먼저 입력 이미지의 포화, 초점, 노출, 마스크 결과를 확인하는 편이 안전합니다.

### 3. 어떤 높이 모드를 골라야 하나

- `relative`: 기준 평면이나 보정 파일 없이 실행합니다. 실제 mm 높이가 아니라 phase 기반 미리보기입니다. 새 데이터가 정상적으로 디코딩되는지 확인할 때 가장 먼저 사용합니다.
- `reference`: 같은 조건에서 촬영한 평면 기준 데이터를 빼서 사다리꼴 투영 성분을 제거합니다. 단위는 여전히 phase입니다.
- `triangulation`: 기준 평면과 `d`, `l`, `p` 보정값을 이용해 물리 단위 높이를 계산합니다.
- `inverse-linear`: 여러 기준 높이로 얻은 `u`, `v`, `w` 보정 모델을 이용해 물리 단위 높이를 계산합니다.

물리 높이가 목적이면 기준 평면 촬영은 사실상 필수입니다. 기준 평면 없이 단일 object scan만 넣으면 `relative` 미리보기는 가능하지만, 실제 높이로 해석하기 어렵습니다.

### 4. 결과가 정상인지 확인하는 순서

디코딩 후에는 먼저 heat map만 보지 말고 다음 항목을 함께 확인하세요.

1. `combined_mask`: 실제 계산에 사용된 픽셀 영역입니다. PCB 대부분이 빠져 있으면 노출, 초점, threshold, ROI 설정을 확인해야 합니다.
2. `stripe_order_preview`: Gray code 줄무늬 번호가 큰 끊김 없이 변하는지 확인합니다.
3. `wrapped_phase_preview`: sine phase가 부드럽게 이어지는지 확인합니다.
4. `absolute_phase_preview`: Gray code와 sine phase가 결합된 전체 위상이 계단처럼 튀지 않는지 확인합니다.
5. `delta_phase_preview`: 기준 평면을 사용한 경우 object와 reference의 차이가 의도한 표면 형상만 남기는지 확인합니다.

mask가 넓게 빠지는 것은 실패라기보다 “신뢰할 수 없는 픽셀을 제외했다”는 뜻입니다. 다만 PCB의 핵심 영역이 빠졌다면 촬영 조건이나 threshold를 다시 조정해야 합니다.

### 5. 다른 PC에 전달할 때

일반 사용자는 Python을 설치할 필요가 없습니다. 빌드된 `dist/PCB_FPP_Decoder` 폴더 전체를 전달하고, 그 안의 `PCB_FPP_Decoder.exe`를 실행하게 하면 됩니다. 폴더 안의 DLL과 라이브러리가 함께 필요하므로 EXE 파일 하나만 따로 복사하지 마세요.

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

PRO4500 촬영기의 최종 `pattern_XXX.png`가 mono16 PNG이면 입력 단계에서
선형 0..255 부동소수점 범위로 정규화합니다. 따라서 기존 포화/암부
임계값은 8-bit 입력과 동일하게 유지됩니다. RGB 원본은 재평가용이며
실제 Gray code/PSP 계산에는 촬영기에서 선택한 한 채널의 mono16 프레임만
사용합니다.

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

Android 촬영 워크플로는 보통 다음과 같은 스캔 폴더 구조를 만듭니다. 실제 저장 위치는 사용자의 장비 제어 프로그램 설정에 맞게 달라질 수 있습니다.

```text
captures/<scan_id>/
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

`--input`에 스캔 루트를 넘겨도 디코더가 사용할 수 있는 `angle_000` 폴더를 자동으로 찾아 사용합니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input "captures\<scan_id>" `
  --output "processed\<scan_id>\angle_000" `
  --input-color-mode smartphone_uv_blue `
  --gray-decode-mode auto `
  --median-filter 3
```

CLI 기본 출력은 `compact` 프로필입니다. 보고서, 미리보기 PNG, 재사용에 필요한 핵심 `.npy`만 저장하고 보정 프레임 전체, 중간 배열 묶음, PLY 포인트 클라우드는 남기지 않습니다. 전체 진단 산출물이 필요할 때만 `--output-profile full`을 추가하세요.

다른 각도를 직접 지정하려면 `--input-angle 180`처럼 지정합니다. 같은 스캔 루트에 `angle_000`과 `angle_180`이 모두 있고 바로 통합하려면 `--auto-phone-fusion`을 사용할 수 있습니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input "captures\<scan_id>" `
  --output "processed\<scan_id>\fused" `
  --auto-phone-fusion `
  --height-mode triangulation `
  --reference-scan "captures\<reference_scan_id>" `
  --calibration-config examples\calibration_config.example.json
```

`scan_log.json`이 있으면 `decode_report.json`의 `phone_capture` 항목에 수동 노출/ISO, 수동 초점, AWB lock, HDR bracket, scan type, rig/calibration id, JPEG 사용 여부, 반전 Gray 누락 여부가 기록됩니다. 폰 촬영에서 경고가 없어야 한다는 뜻은 아니지만, height map을 해석하기 전에는 이 항목과 `masks/combined_mask.png`, `height/delta_phase_preview.png`를 함께 확인하세요.

## 0°/90°/180°/270° 4방향 데이터 통합

현재 4방향 촬영의 표준 폴더 구성은 다음과 같습니다. `--four-direction`은 스캔 루트 아래의 네 폴더를 자동으로 찾고, 하나라도 없으면 2방향으로 조용히 축소하지 않고 오류로 중단합니다.

```text
captures/scan_xxx/
  angle_000/
  angle_090/
  angle_180/
  angle_270/
```

각 폴더의 `pattern_000.png`에는 `aruco_stage_d105_r25_total15_a4.pdf`로 출력한 ID 0/1/2/3 마커 중 최소 두 개가 보여야 합니다. 마커 중심은 스테이지 중심에서 각각 25 mm, 검은 ArUco 사각형은 11.4 mm입니다. 각 뷰는 자기 사진에서 검출된 마커를 실제 스테이지 좌표로 먼저 보낸 뒤 0° 카메라 프레임으로 변환하므로, 0°와 90° 사진에 서로 다른 마커 쌍이 보여도 정합할 수 있습니다. 한 사진 안에서는 최소 두 마커가 필요하며, 한 마커만 보이면 그 뷰의 스테이지 좌표계와 회전·이동을 안정적으로 결정하지 못하므로 중단합니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input captures\scan_xxx `
  --four-direction `
  --output processed\scan_xxx\fused_four `
  --height-mode phase_linear `
  --reference-phase-0 processed\reference\reference_phase_0.npy `
  --reference-phase-90 processed\reference\reference_phase_90.npy `
  --reference-phase-180 processed\reference\reference_phase_180.npy `
  --reference-phase-270 processed\reference\reference_phase_270.npy `
  --calibration-config examples\calibration_config.example.json `
  --fusion-registration aruco `
  --aruco-method stage-cross `
  --aruco-marker-center-radius-mm 25 `
  --aruco-marker-black-square-mm 11.4
```

하드웨어 트리거 촬영을 강제 검증하려면 `--require-hardware-capture`를 추가합니다. 이때 각 각도의 `scan_log.json`에는 `stage.settled=true`, `stage.commanded_angle_deg`, 실제 또는 측정 각도, 고유한 `stage.position_id`가 있어야 하고 기본 허용 오차는 ±0.5°입니다. `--stage-angle-tolerance-deg`로 장비 사양에 맞게 조정할 수 있습니다.

정합 결과는 `fusion/aruco_transform_deg_90.json`, `aruco_transform_deg_180.json`, `aruco_transform_deg_270.json`에 남습니다. 계산은 네 높이 지도를 순차 평균하지 않고, 모두 0° 프레임에 맞춘 뒤 동시에 비교합니다. 한 뷰만 유효하면 그 값을 쓰고, 겹치는 뷰는 modulation 신뢰도로 가중하며, 높이 차이가 허용치를 넘는 관측은 더 높은 신뢰도 뷰를 선택하거나 `invalid` 정책에 따라 제외합니다. `source_map.npy`는 비트 마스크 `1=0°`, `2=90°`, `4=180°`, `8=270°`로 기여 뷰를 기록하므로 값 15는 네 뷰 모두가 기여했다는 뜻입니다.

이 설계는 OpenCV의 공식 [ArUco 검출 문서](https://docs.opencv.org/4.13.0/d5/dae/tutorial_aruco_detection.html)가 설명하는 마커 코너 대응점과 여러 마커/부분 가림을 처리하는 Board 개념을 따릅니다. 모든 뷰를 공통 기준 프레임으로 정렬한 뒤 함께 결합하는 구조는 Open3D 공식 [multiway registration 문서](https://open3d.org/docs/latest/tutorial/Advanced/multiway_registration.html)의 전역 기준 프레임 원칙과 같은 방향입니다. 다만 이 구현은 3D ICP가 아니라 알려진 평면 stage-cross 좌표에 대한 2D homography와 구조광 높이 신뢰도 결합을 사용합니다.

## 0도/180도 데이터 통합(호환 모드)

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

#### 무조명 사전보정(권장: 실제 스캔 중 마커 검출 없음)

라이트 패턴이 ArUco를 가려 실제 스캔에서 검출이 불안정하면, PCB를 올린 직후 **패턴을 투사하지 않은 상태**에서 0과 **스테이지 프로그램 명령값 250**으로 각각 한 장씩만 촬영합니다. 이 250은 각도가 아니라, **실제 180° 회전을 의도한 장비 제어값**입니다. 그 뒤 PCB와 스테이지를 절대 건드리지 않고 실제 0°/명목 180° 패턴 스캔을 촬영합니다. 아래 사전보정은 실제 회전각, 0도 이미지 좌표계의 회전 중심, 재투영 오차와 함께 회전 뷰를 0도 뷰로 보내는 변환 JSON을 만듭니다. 따라서 PCB가 스테이지 정중앙에서 벗어나 있어도 그 오프셋이 변환에 포함됩니다.

```powershell
.venv\Scripts\python.exe scripts\estimate_stage_precalibration.py `
  --image-0 captures\scan_xxx\prescan_0.png `
  --image-rotated captures\scan_xxx\prescan_nominal_180.png `
  --stage-command-value 250 `
  --intended-rotation-deg 180 `
  --ids 0,1,2,3 `
  --output processed\scan_xxx\stage_precalibration.json
```

실제 패턴 스캔에서는 생성한 파일만 사용합니다. `--fusion-registration rotation-180`은 자동 ArUco 정합을 끄기 위한 설정이고, `--analysis-roi none`도 실제 스캔 중 ArUco ROI 검출을 끕니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input captures\scan_xxx\deg_0 `
  --input-180 captures\scan_xxx\deg_180 `
  --output processed\scan_xxx\fused `
  --fusion-transform processed\scan_xxx\stage_precalibration.json `
  --fusion-registration rotation-180 `
  --analysis-roi none `
  --fusion-mode modulation-weighted
```

사전보정 JSON의 `stage_precalibration.commanded_stage_value`는 프로그램에 넣은 값(예: `250`)이고, `actual_rotation_magnitude_deg`가 그 명령에 대응하는 **실측 회전량**입니다. `intended_rotation_deg`는 명목 목표값(기본 `180`)입니다. `rotation_center_target_xy`는 0도 이미지에서의 보정 중심입니다. 재투영 RMSE가 크면(예: 수 픽셀 이상) 두 무조명 사진의 초점/노출, 마커 가림·흐림, 또는 촬영 사이 PCB 이동을 먼저 점검해야 합니다.

로테이션 스테이지가 정확히 180.00도 회전하지 않는 경우에는 PCB에 붙인 ArUco 마커를 이용해 `deg_180` 영상을 `deg_0` 좌표계로 보정할 수 있습니다. 마커 이미지는 저장소에 포함하지 않고, 필요할 때 다음 명령으로 다시 생성합니다.

현재 기본 실행값은 스테이지 ArUco 마커를 사용하는 쪽입니다. 4방향 통합에서는 `--fusion-registration aruco`, `--aruco-method stage-cross`가 기본이고, 단일 디코딩에서도 `--analysis-roi aruco`, `--analysis-aruco-layout stage-cross`, 마커 반경 `25 mm`, 스테이지 지름 `105 mm`, PCB `30 x 30 mm`가 기본입니다. 마커가 없는 과거 촬영 데이터를 처리할 때만 `--analysis-roi none` 또는 2방향의 `--fusion-registration rotation-180`을 명시하세요.

스테이지 원판 전체에 붙일 때는 실제 스테이지에 맞는 레이아웃을 생성해 사용합니다. 아래 명령은 지름 105 mm 원판 안에 ID 0, 1, 2, 3 마커를 위/오른쪽/아래/왼쪽 순서로 배치합니다. 각 마커 중심은 원판 중심에서 25 mm 떨어지고, 흰 여백 포함 전체 마커 크기는 약 15 mm입니다. 이 값들이 스크립트의 기본값이므로 옵션 없이 실행해도 `aruco_stage_d105_r25_total15_a4.pdf`가 생성됩니다.

```powershell
.venv\Scripts\python.exe scripts\generate_aruco_stage_layout.py `
  --ids 0,1,2,3 `
  --dictionary DICT_4X4_50 `
  --stage-diameter-mm 105 `
  --marker-radius-mm 25 `
  --marker-total-mm 15 `
  --quiet-zone-mm 1.8 `
  --dpi 300 `
  --output aruco_markers_stage_layout `
  --prefix aruco_stage_d105_r25_total15
```

인쇄할 때는 프린터 배율을 `실제 크기` 또는 `100%`로 두고, `용지에 맞춤` 옵션은 끄세요. A4 PDF로 출력한 뒤 원형 외곽선을 따라 잘라 원판 중심과 십자 표시를 맞춰 붙입니다. 생성된 `aruco_markers*`와 `markers` 폴더는 `.gitignore`에 포함되어 있으므로 출력물은 Git에 추가하지 않습니다.

4방향 보정은 출력 치수와 부착 치수(반경 25 mm, 검은 사각형 11.4 mm)를 스테이지 좌표계 정의에 사용합니다. 각 사진에서 마커 코너를 검출하고 RANSAC 기반 homography로 사진↔스테이지 변환을 구하므로 작은 검출 오차에는 강하지만, 인쇄 배율이나 마커 부착 위치 오차가 곧 좌표계 오차가 됩니다. 반드시 100% 배율로 인쇄하고 중심 십자와 실제 회전 중심을 맞추세요. 기존 2방향 `homography` 방식은 두 사진에 같은 마커들이 보일 때 직접 영상 간 대응을 구하므로 그 호환 경로도 유지됩니다.

원판을 A4에서 잘라 붙이면 마커 주변과 PCB-마커 사이의 흰 종이 영역도 촬영됩니다. 이 영역은 마커 검출에는 필요하지만 높이 계산에는 들어가면 안 되므로, 디코딩 시 ArUco 기반 analysis ROI를 함께 켭니다. `stage-cross` 레이아웃은 ID 0/1/2/3 마커 중심을 각각 위/오른쪽/아래/왼쪽 기준점으로 보고 스테이지 좌표계를 만든 뒤, 중심에 놓인 PCB 영역만 남깁니다. 기본 `--pcb-inset-mm 0.5`는 PCB 외곽에서 안쪽으로 0.5 mm를 추가 제외해, 실물 배치·마커 검출·호모그래피의 작은 오차로 형광 A4 종이가 가장자리에 섞이는 일을 막습니다. 따라서 기본 30 x 30 mm PCB의 실제 계산 영역은 29 x 29 mm이며, 외곽까지 측정해야 할 때만 `--pcb-inset-mm 0`으로 설정하세요. PCB가 가리지 못한 모든 종이 영역은 `combined_mask`와 height map에서 제외됩니다.

```powershell
.venv\Scripts\python.exe scripts\decode_scan.py `
  --input captures\scan_xxx\deg_0 `
  --output processed\scan_xxx\deg_0 `
  --analysis-roi aruco `
  --analysis-aruco-layout stage-cross `
  --analysis-aruco-ids 0,1,2,3 `
  --analysis-marker-center-radius-mm 25 `
  --analysis-stage-diameter-mm 105 `
  --pcb-width-mm 30 `
  --pcb-height-mm 30 `
  --pcb-margin-mm 0 `
  --pcb-inset-mm 0.5
```

출력 폴더의 `masks/analysis_roi_mask.png`, `masks/marker_space_mask.png`, `masks/pcb_analysis_mask.png`를 확인하면 실제로 어느 영역이 계산에 사용됐는지 볼 수 있습니다. `pcb_analysis_mask.png`의 바깥은 보정·위상·높이·0/180 통합 모두에서 제외됩니다. PCB를 중심에서 의도적으로 벗어나게 붙이는 경우에는 현재 옵션 대신 별도 PCB 위치 기준점이나 수동 ROI가 필요합니다.

촬영 후에는 White 프레임인 `pattern_000.png`에서 ID 0/1/2/3 마커를 검출해 fusion transform을 생성합니다.

```powershell
.venv\Scripts\python.exe scripts\estimate_aruco_fusion_transform.py `
  --input captures\scan_xxx\deg_0 `
  --input-180 captures\scan_xxx\deg_180 `
  --output processed\scan_xxx\aruco_fusion_transform.json `
  --ids 0,1,2,3 `
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
  --aruco-ids 0,1,2,3 `
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

그래픽 화면은 반복 측정용으로 정리되어 있습니다. 빈 스테이지의 0°/90°/180°/270° 스캔을 `기준면 검증 및 저장`으로 등록한 뒤, PCB 네 방향의 스캔 폴더와 결과 폴더를 지정해 `높이 계산 및 시각화`를 누르세요. 하나의 스캔 루트를 선택하면 `angle_000/090/180/270`을 자동으로 채웁니다. GUI는 반경 25 mm, 검은 사각형 11.4 mm의 stage-cross 정합을 각 회전 뷰에 적용합니다. 저장된 각도별 기준면이나 네 방향 중 하나가 없으면 4방향 측정을 시작하지 않습니다. 기존 0°/180°만 지정한 2방향 작업도 계속 지원합니다.

기준면 등록에는 빈 스테이지의 네 방향 스캔 폴더를 지정합니다. 각 촬영은 PCB 대상 스캔과 같은 22개 패턴·노출·초점 설정을 사용해야 합니다. 프로그램은 각 방향의 유효 영역, 기준 평면 잔차, 국소 이상치 비율을 확인해 PCB 등 물체가 남은 기준면을 거부하며, 통과한 네 `absolute_phase` 배열을 `%LOCALAPPDATA%\PCB_FPP_Decoder\flat_stage_reference`에 저장합니다. 새 기준면 전체가 검증을 통과한 뒤에만 활성 기준을 교체합니다.

## 디버거 실행 (개발용)

프로젝트 루트의 `run_debugger.bat`를 실행하면 디버그 GUI가 열립니다. 처음 한 번만 필요한 Python 패키지를 `%LOCALAPPDATA%\PCB_FPP_Decoder\debugger_venv_py312`에 설치하고, 이후에는 그 환경을 재사용합니다. 따라서 프로젝트 폴더에는 `.venv`나 `dist`가 생성되지 않습니다.

기본 Python을 지정해야 하는 환경에서는 실행 전에 `DEBUGGER_PYTHON` 환경 변수에 Python 실행 파일 경로를 지정할 수 있습니다.

정리 도구 `scripts\clean_generated.py`는 기존 `dist` 실행 파일을 기본적으로 보존합니다. `dist`까지 삭제하려면 `--include-dist --execute`를 명시해야 합니다.

디버거 EXE를 포함한 배포본을 다시 만들려면 `build.bat`를 실행하세요.

의존성을 갱신해야 할 때만 아래처럼 실행합니다.

```bat
run_debugger.bat --refresh
```

## 실행 파일 빌드

다른 Windows PC에서 사용할 실행 파일이 필요하면 프로젝트 루트에서 다음 파일을 실행합니다.

```bat
build.bat
```

빌드 스크립트는 `.venv`를 만들고 `requirements.txt`와 PyInstaller를 설치한 뒤 그래픽 화면 실행 파일, 보조 명령줄 실행 파일, 디버그 GUI 실행 파일을 생성합니다. 이 절차는 다른 PC에 전달할 실행 파일이 필요할 때만 사용하세요.

```text
dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe
dist/PCB_FPP_Decoder_CLI/PCB_FPP_Decoder_CLI.exe
dist/PCB_FPP_Debugger/PCB_FPP_Debugger.exe
```

일반 사용자는 `dist/PCB_FPP_Decoder/PCB_FPP_Decoder.exe`를 더블 클릭하면 됩니다. 프로젝트 루트의 `PCB_FPP_Decoder.vbs`를 더블 클릭해도 같은 그래픽 화면이 실행됩니다. 다른 PC로 전달할 때는 `dist/PCB_FPP_Decoder` 폴더 전체를 복사하세요. 실행 PC에는 Python을 별도로 설치하지 않아도 됩니다.

## 출력 구조

아래 구조는 `--output-profile full` 기준입니다. 기본 `compact` 출력에서는 `corrected/`, `point_cloud/`, 대부분의 중간 `.npy` 파일과 중복 `height.npy` 별칭을 생략합니다.

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
  capture_diagnosis.txt
  decode_report.json
```

`decode_report.json`에는 `optical_setup` 항목이 기록됩니다. 여기서 기준 위상 차감 사용 여부, 기준 데이터 경로, `height/delta_phase.npy` 저장 여부, 위치별 보정 맵 로딩 여부를 확인할 수 있습니다.

산출 폴더를 다른 PC나 분석 환경으로 옮길 때도 촬영 조건을 함께 검토할 수 있도록, 디코더는 입력의 작은 부가 파일을 `capture_logs/`에 복사합니다. 단일 촬영은 `capture_logs/` 바로 아래에, 0/180 통합 촬영은 `capture_logs/deg_0/`, `capture_logs/deg_180/` 아래에 저장됩니다. 포함 대상은 `scan_log.json`, `quality_report.json`, `hdr_merge_report.json`, `blue_channel_histograms.png`와 (스캔 루트에 있는 경우) `stage_precalibration.json`입니다. 원본 pattern 이미지와 HDR exposure 이미지는 용량 때문에 복사하지 않습니다. `capture_logs/manifest.json`에서 실제로 포함·누락된 파일을 확인할 수 있습니다.

디코딩이 끝나면 출력 폴더의 `capture_diagnosis.txt`도 확인하세요. 이 메모는 White/Black 밝기와 대비, 과노출·암부 비율, Gray confidence, sine modulation, 최종 유효 픽셀 비율을 간단히 정리하고 노출·ISO·프로젝터 밝기·초점·반사각 중 무엇을 먼저 조정할지 제안합니다. ArUco 분석 ROI를 사용한 경우 PCB 영역 안의 픽셀만 집계합니다. 진단은 원인을 확정하는 기능이 아니라 현재 수치에 따른 촬영 점검 우선순위입니다.

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
# Phase-linear metric height and angle-specific references

`--height-mode phase_linear` converts signed reference-subtracted absolute phase
to millimeters using `phase_linear.phase_per_mm`, `offset_phase`, and
`height_sign` from the calibration JSON. For fused scans, use
`--reference-scan-0` and `--reference-scan-180` (or the corresponding
`--reference-phase-0/180` options) so each object view is paired with its own
flat reference. The legacy `--reference-scan` and `--reference-phase` options
remain supported.

Relative mode is non-metric and all reports and figures label it as
`relative phase (phase units)`. Metric fusion rejects weighted averaging when
the two view heights differ by `--fusion-max-height-difference-mm` or a cycle
slip is detected. `--fusion-inconsistent-policy` chooses the stronger view or
marks the pixel invalid. The selected phase convention and first/center-row
cosine diagnostic scores are recorded in `decode_report.json`.

## Validation and simulation suites

Synthetic self-consistency, deterministic equipment non-idealities, and
Blender/Cycles validation are documented separately in
[`docs/VALIDATION_LEVELS.md`](docs/VALIDATION_LEVELS.md). The validation harness
does not change production decoder thresholds, phase/height calculations, or
fusion defaults, and L0/L1 results must not be presented as real-equipment
accuracy.

Generate the ready-to-use procedural 4-view x 22-pattern inputs with
`tools/generate_ideal_dataset.py`. Generated images or arbitrary PCB photos are
not used directly as decoder inputs.

Run `run_validation_suite.bat` to generate the ideal, L0, and
clean/normal/hard/extreme L1 cases and open the comparison dashboard. Each case
shows the actual 4-view x 22-pattern decoder inputs, result overview, valid
ratio, phase MAE, and phase P95 together.

Run `run_validation_suite.bat --suite reference-board` for the source-informed Adafruit BME280,
Soldered Simple light sensor, and Soldered W5500 comparison suite. Applied board
dimensions, approximation limits, sources, and licenses are documented in
[`docs/SIMULATION_SOURCES.md`](docs/SIMULATION_SOURCES.md).

Run `run_validation_suite.bat --suite source-grounded` for the source-grounded audit. It downloads
and SHA-256 verifies three small physical HDR samples from scanner-sim, runs a
CS126MU manufacturer-bounded sensor case plus a separate case that applies the
measured physical `background.exr` as a bounded low-frequency image-domain proxy,
and opens a landing page linking the case-by-case simulation dashboard and the
physical/synthetic domain-gap report. The proxy is not a CS126MU PSF/gamma/noise
calibration. Large scanner-sim calibration archives and the GDD physical
fringe/height benchmark are opt-in and require an independently verified
`--sha256`.
The evidence hierarchy, accepted/rejected sources, and interpretation limits are
documented in [`docs/SOURCE_GROUNDED_VALIDATION.md`](docs/SOURCE_GROUNDED_VALIDATION.md).

## Attribution

Original author: [eriverOoO](https://github.com/eriverOoO). This notice is retained to
identify the original authorship of this repository.
