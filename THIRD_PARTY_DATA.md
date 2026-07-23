# Third-party validation data

외부 dataset이나 model 자체는 이 저장소에 포함하지 않는다. 실제 사용 시 downloader가
생성하는 `LICENSE_AND_CITATION.json`과 upstream license를 함께 보관한다.

## Scanner-sim physical scans

- Dataset/paper: https://geometryprocessing.github.io/scanner-sim/ and
  https://openreview.net/forum?id=bNL5VlTfe3p
- Archive: https://archive.nyu.edu/handle/2451/63306
- License: CC BY 4.0
- Scope: 실제 HDR structured-light pattern/background의 영상 도메인 감사. physical
  archive 자체는 per-pixel 독립 height GT가 아니며, geometry GT는 synthetic archive에서
  별도로 다룬다.
- Local automatic sample: `img_40.exr`, `leo_010.exr`, `background.exr` 총 약 110 MB;
  catalog SHA-256와 대조한다.
- Limitation: 47-pattern 계열, 비PCB 장면, 다른 rig다. production 22-frame 입력으로
  rename하거나 실장비 높이 정확도의 정답으로 사용하지 않는다.

## Scanner-sim calibration archive

- Source: https://archive.nyu.edu/handle/2451/63307
- Scope: 실제 rig의 camera/projector intrinsic/extrinsic, vignetting, projector response,
  accuracy-test 자료를 opt-in external calibration 후보로 기록한다.
- 적용: `tools/fetch_external_fpp.py --dataset scanner_sim_calibration`에서 variant를
  고르고, 독립 확인한 `--sha256`를 지정한 경우에만 다운로드한다.
- Limitation: scanner-sim rig와 현재 CS126MU rig가 다르므로 수치를 자동으로 PSF/gamma/
  distortion 보정값으로 이식하지 않는다.

## Scanner-sim synthetic archive

- Source: https://archive.nyu.edu/handle/2451/63308
- Scope: 독립 scanner-sim renderer의 HDR/LDR sequence와 depth/mesh/point-cloud GT를
  geometry/renderer 교차검증 후보로 기록한다.
- Limitation: 47-pattern 비PCB 장면이며 수십 GB archive다. production 22-frame decoder
  입력으로 rename하지 않는다.

## Other held-out evidence candidates

- GDD physical FPP: https://zenodo.org/records/12771948 — 실제 fringe와 calibrated
  height map(최대 5 mm), CC BY 4.0. `gdd_physical` external height benchmark 경계만
  기록하며 CS126MU PCB 정답으로 쓰지 않는다.
- Skoltech3D: https://github.com/Skoltech-3D/sk3d_data — 실제 RGB/IR와 structured-light
  reference mesh를 geometry-only held-out 후보로 기록한다. 데이터 조건은 별도 확인한다.
- PCB DSLR: https://zenodo.org/records/3886553 — 실제 PCB 외관/조명 held-out 후보다.
  projector pattern이나 metric height GT가 없으므로 appearance-only로만 사용한다.

## PBRT structured-light dataset

- Source: https://zenodo.org/records/17826191
- License reported by the task specification: CC BY 4.0 (download 시 record 재확인)
- Size: smallest archive approximately 2.1 GB
- Scope: phase demodulation, unwrapping, mask/robustness submodule validation
- Limitation: Gray code + 6-step sine와 production exact 22-pattern sequence가 다르다.
  전체 decoder 입력으로 rename하지 않는다.

## FPP-ML-Bench

- Source: https://huggingface.co/datasets/aharoon/fpp-ml-bench
- Scope: external synthetic-domain test
- Limitation: 52 frames, matte materials, 960x960, 1.5–2.1 m. PCB 실측 대체물이 아니다.
- License: dataset card의 MIT 표기를 취득 시 다시 확인하고 provenance에 기록한다.

## HDR-Net real HDR FPP scenes

- Source: https://github.com/SHU-FLYMAN/HDR-NET
- Scope: 실제 plaster/metal 장면, 다중 노출 HDR FPP의 영상 도메인 참고
- Limitation: 배포 경로가 Baidu 중심이고 repository의 MIT 코드 license와 dataset 사용
  조건을 동일하다고 단정할 수 없다. dataset license를 별도로 확인하기 전에는 자동으로
  내려받거나 검증 입력에 넣지 않는다.

## 3DLF-Scan

- Publication: https://pmc.ncbi.nlm.nih.gov/articles/PMC12969299/
- Scope: 실제 structured-light depth/point cloud와 reference shape가 있는 외부 geometry
  비교 후보
- Limitation: production raw FPP 22-frame 입력이 아니며 archive의 정확한 license와
  registration 단위를 확인하기 전에는 자동 사용하지 않는다.

## KiCad/StepUp

- KiCad libraries: https://www.kicad.org/libraries/download/
- KiCad StepUp: https://www.kicad.org/external-tools/stepup/
- Scope: PCB 3D model 및 STEP→GLB/glTF 변환 경로
- License: 선택한 개별 library/model의 license와 원본 URL을 scene별 provenance에 기록한다.

인터넷의 일반 PCB 사진은 albedo 참고만 가능하다. 서로 다른 사진을 pattern sequence로
위장하거나 생성형 이미지 모델 결과를 decoder 입력으로 사용하지 않는다.
