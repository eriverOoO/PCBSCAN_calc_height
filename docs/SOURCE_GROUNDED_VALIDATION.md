# 출처 기반 검증 설계

## 목적

절차 생성기가 디코더와 같은 가정을 공유해 정확도가 과대평가되는 inverse-crime 위험을
줄인다. 외부 자료는 신뢰도뿐 아니라 **production 22-frame 입력과 무엇을 검증할 수
있는지**에 따라 분리한다. 다른 패턴군이나 장면을 파일명만 바꿔 end-to-end 정답처럼
사용하지 않는다.

## 증거 계층과 적용 상태

| 자료 | 증거 | 현재 적용 | 적용하지 않는 주장 |
|---|---|---|---|
| [scanner-sim physical](https://geometryprocessing.github.io/scanner-sim/) / [NYU archive](https://archive.nyu.edu/handle/2451/63306) | 실제 스캐너 HDR pattern/background, CC BY 4.0 | 실제 `img_40.exr`, `leo_010.exr`, `background.exr`의 SHA-256 검증·영상 통계 감사와 별도 low-frequency background proxy | physical archive 자체의 독립 height GT, production 22-frame 호환, PCB mm 높이 정확도 |
| [scanner-sim calibration archive](https://archive.nyu.edu/handle/2451/63307) | camera/projector vignetting·response·intrinsic/extrinsic calibration 자료, CC BY 4.0 | checksum을 명시한 경우에만 opt-in 다운로드/transfer manifest 지원 | 다른 rig의 수치를 CS126MU PSF·gamma·distortion으로 자동 이식하지 않음 |
| [scanner-sim synthetic archive](https://archive.nyu.edu/handle/2451/63308) | 독립 scanner-sim renderer, depth/mesh/point-cloud GT, CC BY 4.0 | `scanner_sim_synthetic` external adapter로 geometry/renderer 교차검증 경계 기록 | 47-pattern을 production 22-frame으로 변환하지 않음 |
| [Thorlabs CS126MU 공식 사양](https://www.thorlabs.com/newgrouppage9.cfm?objectgroup_id=13255) | 4096×3000, 3.45 µm, 12-bit ADC, global shutter, full well ≥10,650 e-, read noise <2.5 e- RMS | full-well 하한과 read-noise 상한을 보수적으로 사용하고 12-bit 양자화 적용 | 장착 렌즈 PSF, camera software gamma, distortion, unit-specific FPN |
| [FPP-ML-Bench](https://huggingface.co/datasets/aharoon/fpp-ml-bench) | 독립 VIRTUS-FPP/Isaac Sim 계열, object-level held-out split, MIT 표기 | 외부 synthetic 후보 catalog와 `submodule_only` 정책 | 52장을 production 22장으로 변환, 근거리 PCB 실측 대체 |
| [HDR-Net](https://github.com/SHU-FLYMAN/HDR-NET) | 실제 HDR FPP plaster/metal scene | license 확인 대기 catalog | MIT 코드 license를 dataset license로 간주하거나 자동 다운로드 |
| [3DLF-Scan 논문/데이터 기술](https://pmc.ncbi.nlm.nih.gov/articles/PMC12969299/) | 실제 structured-light geometry와 reference shape | 외부 geometry 후보 catalog | raw 22-frame 이미지 검증, archive license 미확인 상태의 자동 사용 |
| [GDD physical FPP](https://zenodo.org/records/12771948) | 실제 fringe와 calibrated height map, CC BY 4.0 | `gdd_physical` external real-capture/height benchmark 경계 기록 | 다른 rig·해상도·패턴, 최대 5 mm target이므로 CS126MU PCB 높이 정답 아님 |
| [Skoltech3D](https://github.com/Skoltech-3D/sk3d_data) | 실제 RGB/IR와 structured-light reference mesh | `sk3d` geometry-only held-out 후보 catalog | production fringe 입력·PCB 높이 GT, dataset 조건 미확인 상태의 자동 사용 |
| [PCB DSLR dataset](https://zenodo.org/records/3886553) | 165개 PCB의 실제 외관/조명·held-out board 후보 | `pcb_dslr` appearance-only catalog | projector pattern, metric 3D/height GT |
| 일반 PCB 사진/생성형 이미지 | 외관 참고 | 사용하지 않음 | 위상·높이 ground truth 또는 pattern sequence |

scanner-sim 전체 physical scan은 개체당 수십 GB일 수 있어 기본 실행은 공식 페이지가
제공하는 약 110 MB sample 3개만 받는다. downloader는 각 파일의 고정 SHA-256을 검사하고
`LICENSE_AND_CITATION.json`을 함께 쓴다.

Calibration/synthetic archive와 GDD 원본은 수백 MB에서 수십 GB이므로 저장소에 넣거나
자동 다운로드하지 않는다. catalog에 있는 archive는 `--variant`와 독립적으로 확인한
`--sha256`를 함께 지정할 때만 받도록 막아, 변조·불완전 전송을 조용히 검증 데이터로
쓰지 않게 했다.

## 실제로 바뀐 시뮬레이션 항목

`configs/validation_l1_cs126mu.yaml`은 제조사 공개 사양으로 직접 경계를 설정할 수 있는
항목만 활성화한다.

- shot noise 전자 수: full-well의 공개 하한 `10,650 e-` 사용
- read noise: 공개 상한 `2.5 e- RMS / 10,650 e-` 사용
- ADC: 12-bit, 최대 4,096 level로 양자화한 뒤 mono16 컨테이너로 저장
- global shutter: rolling-shutter 왜곡을 주입하지 않음

PSF, 감마, 왜곡, row/column/FPN, 표면 반사, 재장착 오차는 해당 rig에서 측정되지 않았기
때문에 이 profile에서는 0으로 둔다. 따라서 이 profile은 **CS126MU 센서 사양 한정
검사**이고 정상/고난도 전체 환경 stress profile을 대체하지 않는다.

scanner-sim 실제 HDR sample은 선형 quantile, dynamic range tail, normalized gradient
RMS를 계산한다. 단일 장면으로는 PSF·감마·read noise·saturation을 서로 분리해 식별할
수 없으므로 이 값을 시뮬레이터 parameter에 역으로 맞추지 않는다. 보고서는 domain-gap
sentinel이며 decoder threshold 조정에도 사용하지 않는다.

`configs/validation_l1_source_empirical.yaml`은 위 physical `background.exr`의 넓은
저주파 공간장만 0.75–1.25 범위의 gain proxy로 만들어 모든 pattern에 동일하게 적용한다.
이는 실제 조명/비네팅 도메인 차이를 재현하기 위한 image-domain 입력이며, manifest에
원본 SHA-256·resize·blur·clipping·식별 불가 경고를 남긴다. PSF, gamma, read noise,
saturation, geometric distortion을 scanner-sim 한 장면에서 추정하지 않는다.

source-grounded와 기본 procedural v2 fixture는 `reference_board_max_height_mm=1.9`로
생성되며, generic component archetype도 이 상한에서 잘린다. 기존 v1 산출물은 과거
생성물일 수 있으므로 새 실행은 v2 output root를 사용한다.

## 원클릭 실행

프로젝트 루트에서 다음 BAT를 더블클릭한다.

```text
run_source_grounded_suite.bat
```

또는 PowerShell에서 실행한다.

```powershell
.venv\Scripts\python.exe tools\run_source_grounded_suite.py --open
```

순서는 다음과 같다.

1. 공식 scanner-sim sample 3개를 다운로드하거나 기존 파일의 SHA-256을 재검사한다.
2. 독립 output root에 ideal 4-view × 22-frame fixture를 만든다.
3. CS126MU sensor-bound case와 physical-background proxy case를 각각 생성하고 production decoder로 실행한다.
4. 실제 HDR/합성 frame 기술 통계와 모든 해시를 JSON/HTML로 쓴다.
5. `validation_results/source_grounded/source_grounded_index.html`을 연다.

오프라인에서 검증된 sample이 이미 있으면 `--no-download`를 사용한다. quick seed 두 개를
모두 실행하려면 `--seeds-per-profile 2`를 추가한다.

## 대용량 calibration/held-out 자료를 받을 때

원본 calibration과 독립 benchmark는 저장소에 자동으로 넣지 않는다. 먼저 목록을 확인하고,
원하는 archive의 해시를 별도 경로에서 확인한 뒤에만 받는다.

```powershell
.venv\Scripts\python.exe tools\fetch_external_fpp.py `
  --dataset scanner_sim_calibration --list-variants

.venv\Scripts\python.exe tools\fetch_external_fpp.py `
  --dataset scanner_sim_calibration `
  --variant camera_vignetting.zip `
  --sha256 <independently-verified-sha256> --yes
```

`camera_intrinsics`, `projector_intrinsics`, `projector_extrinsic`, `projector_response`,
`projector_vignetting`, `accuracy_test`도 같은 방식이다. archive 페이지에 고정 SHA-256이
제공되지 않는 항목은 `--sha256` 없이는 downloader가 거부한다. scanner-sim rig의 값을
현재 CS126MU rig의 calibration으로 자동 복사하지 않고, provenance/compatibility 검토가
끝난 별도 external case에서만 사용할 수 있다.

## 아직 필요한 실제 장비 데이터

최종적으로 mm 단위 실장비 정확도와 강건성을 주장하려면 같은 camera-projector rig에서
다음을 별도로 취득해야 한다.

- 여러 exposure의 반복 dark frame과 균일 flat frame: read/shot/FPN 분리
- slanted-edge 또는 point target: 위치·초점별 camera/projector PSF
- raw linear ramp: camera/projector response와 gamma
- calibration target: lens/projector distortion 및 camera-projector geometry
- 알고리즘 설계자가 보지 않은 PCB와 등록된 정밀 3D scan/CMM: metric height GT
- object/reference의 반복 탈착 촬영: registration과 시간 변화

이 데이터가 없을 때 generated report의 phase MAE는 합성 GT에 대한 값이며 실제 높이
정확도로 해석하지 않는다.
