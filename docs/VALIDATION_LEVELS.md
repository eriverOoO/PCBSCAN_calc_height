# L0/L1/L2 검증 인프라

이 디렉터리의 검증은 production decoder와 분리되어 있다. 합성 결과는 실제 장비
정확도나 하드웨어 정확도를 뜻하지 않는다. L0 보고서 첫 문구는 항상
`decoder-generator self consistency only`, L1은 `uncalibrated stress envelope`이다.

## 공통 원칙

- production의 threshold, 위상 부호, height 식, 보정계수, fusion 규칙과 기본값은
  검증 결과를 맞추기 위해 바꾸지 않는다.
- runner는 object/reference를 전부 decode한 뒤에만 `gt/`를 읽는다. GT는 decoder나
  calibration inference 인자가 될 수 없다.
- 실패는 결과 폴더의 `failures.json`과 `known_failures/`에 seed, profile, impairment,
  mask 경로, 재실행 명령과 함께 남긴다. stress 점수가 낮아도 decoder를 자동으로
  수정하지 않는다.
- 데이터 위치는 CLI, YAML 또는 `PCB_FPP_VALIDATION_ROOT`로 지정한다. 사용자별 절대
  경로는 코드에 없다.
- `validation_data/`, `validation_results/`, PNG/NPY, Blender/외부 archive는 Git에서
  제외된다. `.gitkeep`, 설정, manifest와 작은 테스트 fixture만 커밋한다.

## L0 — ideal_self_consistency

L0는 22장 매핑/dtype/shape, Gray normal/inverse, sine `[10,11,12,13]` 순서와 위상
convention, 동일 reference 차감의 대수적 항등성, mask/NaN 및 파일 출력 배선을
검사한다. 같은 합성 scene에서 얻은 보정값을 실제 정확도의 근거로 사용하지 않는다.

### 절차적 ideal 데이터셋 생성

생성기는 사진 합성이나 생성형 이미지 모델을 사용하지 않는다. 고정된 PCB geometry,
재질별 albedo, component height와 projector coordinate에서 Gray/4-step sine를 직접
계산한다. 출력은 `object_0`, `object_180`, `reference_0`, `reference_180` 각 22장의
mono 16-bit PNG와 view별 height/phase/material/mask GT다. reference는 PCB가 없는
빈 stage이고, 180도 view는 camera/projector가 아니라 PCB scene만 회전한다.

제공된 비정렬·비초점 촬영 사진은 low-frequency illumination, defocus, 국소 포화가
발생할 수 있다는 정성적 참고로만 기록한다. 사진의 각도, 초점, 배율 또는 pixel 값을
geometry/calibration에 사용하지 않으며 이러한 비이상성은 ideal이 아닌 L1 profile에서
주입한다.

```powershell
.venv\Scripts\python.exe tools\generate_ideal_dataset.py `
  --output-root validation_data\ideal\procedural_pcb_v1 `
  --width 512 `
  --height 320 `
  --seed 17
```

실제 camera 해상도 크기가 필요하면 `--width 1936 --height 1216`로 별도 폴더에
생성한다. 생성물은 Git ignore 대상이고 manifest/config/generator만 커밋한다.

```powershell
.venv\Scripts\python.exe tools\run_accuracy_matrix.py `
  --level l0 `
  --dataset-root <ideal-22-frame-folder> `
  --output-root validation_results\l0 `
  --seed 17 `
  --generator-commit <generator-commit>
```

전체 `1936x1216` 두 view fixture는 다음 위치를 사용한다. 없는 경우 정확한 준비 경로와
함께 skip한다.

```powershell
$env:PCB_FPP_VALIDATION_ROOT = "D:\fpp-validation"
.venv\Scripts\python.exe -m pytest -m integration -q
```

## L1 — deterministic stress synthesis

입력은 수정하지 않고 `case_<seed>/views/{object_0,object_180,reference_0,reference_180}`에
새 16-bit PNG를 쓴다. 각 view는 정확한 22장이다. 한 case에서는 PCB/albedo/sensor가
고정되고 FPN, hot/dead pixel map도 모든 frame/view에서 공유된다. shot/read noise는
frame마다 다르지만 seed로 재현된다.

구현된 effect:

1. pattern별 gain (`clean 0`, `normal ±3%`, `hard ±7%`, `extreme ±10%`)
2. gamma와 sine 2/3차 고조파
3. 분리된 projector/camera PSF와 위치별 defocus
4. Poisson/read/row/column/FPN noise
5. hot/dead pixel과 cluster defect
6. clipping, saturation, blooming
7. 저주파 illumination, vignette, flare
8. object/reference 재장착 translation/rotation
9. 180도 중심 오차와 추가 rotation
10. shadow 확장과 저반사 영역 modulation 감소
11. bright-pad multipath/halo 근사
12. Gray boundary bit ambiguity/flip
13. half/whole-cycle sine/Gray 불일치

기하 warp와 인위적 Gray/cycle-slip은 manifest에 `approximation: image_domain`으로,
나머지 radiometry/noise는 `linear_radiance_domain`으로 표시한다. 모든 pattern gain,
view transform, impairment 설정, mask 이름과 source/output SHA-256도 manifest에 남는다.

```powershell
.venv\Scripts\python.exe tools\generate_stress_cases.py `
  --input-root <ideal-dataset> `
  --output-root validation_data\stress\held_out `
  --profile configs\validation_l1_hard.yaml `
  --partition held_out `
  --seed 2000

.venv\Scripts\python.exe tools\run_accuracy_matrix.py `
  --dataset-root validation_data\stress\held_out `
  --output-root validation_results\l1
```

calibration seed는 `1000..1099`, held-out seed는 `2000..2099`이며 겹치지 않는다.
각 profile은 CI quick seed 2개와 nightly seed 10개를 가진다. calibration seed에서 얻은
계수나 threshold를 held-out 생성에 역으로 적용하는 경로는 없다.

영역별 report는 전체 PCB, 평면 기판, 전체/1 mm 이상 부품, 저/고반사, saturation,
shadow, Gray 경계, 주입 hot pixel/bit flip/cycle-slip, overlap/single-view를 분리한다.
각 영역에는 valid ratio, bias, MAE/RMSE/median/P95/P99/max가 기록되고 phase(rad)와
metric height(mm)는 별도 key이다. cycle-slip과 fusion rejection은 precision/recall/F1로
기록한다. 출력은 `summary.json`, `summary.csv`, `failures.json`, `overview.png`와 case별
impairment mask다.

## L2 — Blender/Cycles와 PBRT adapter 경계

`render_pbr_cases.py`는 실제 0..13 pattern을 읽고 Gray 2..9의 complement만 14..21로
생성한다. 최종 mapping과 각 SHA-256이 scene manifest에 남는다. 공통 manifest에는
XIMEA IMX174 기준 `1936x1216`, 5.86 µm, 35 mm camera, 독립 projector, 고정
camera/projector, PCB만 0/180도 회전, PCB를 제거한 별도 matte-stage reference,
재질별 mesh/PBR material, 요구 GT pass가 선언되어 있다.

현재 저장소에는 Blender-side procedural PCB mesh와 material/Cycles pass를 만드는
backend scaffold가 있다. 이 개발 환경에서는 Blender가 확인되지 않았으므로 projector
gobo node의 실제 texture 투사와 depth/normal/material pass 산출물은 검증 완료로
간주하지 않는다. PBRT는 동일 manifest를 받는 adapter 경계만 있고 backend는 미구현이다.
실제 22-frame render를 승인하기 전에는 `--manifest-only`로 mapping/scene을 검증한다.

```powershell
.venv\Scripts\python.exe tools\render_pbr_cases.py `
  --pattern-root <actual-14-bmp-folder> `
  --output-root validation_data\pbr\case_3000 `
  --seed 3000 `
  --manifest-only
```

Blender 4.x를 설치한 뒤 `--blender C:\path\to\blender.exe`를 주거나
`BLENDER_EXECUTABLE`을 설정한다. Blender가 없으면 PBR test는 설치 명령과 함께 skip한다.
KiCad STEP는 Blender가 직접 읽지 못할 수 있으므로 KiCad GLB export 또는
FreeCAD/KiCad StepUp 변환 후 GLB/glTF importer 경계를 사용한다.

## 공개 데이터

다운로더는 dataset과 exact variant를 명시해야 하며 예상 크기와 license/제약을 먼저
출력한다. `--yes` 없이는 다운로드하지 않고, CI에서는 항상 다운로드를 금지한다.
`.part` resume, SHA-256, archive traversal/link 차단, license/citation 저장을 지원한다.

```powershell
.venv\Scripts\python.exe tools\fetch_external_fpp.py `
  --dataset pbrt_zenodo `
  --output-root validation_data\external `
  --list-variants
```

PBRT dataset의 Gray+6-step sine와 FPP-ML-Bench의 52 frame은 production 22 frame으로
파일명만 바꾸지 않는다. `validation_harness.external` adapter manifest는 이를
`submodule_only`로 강제한다. 출처와 용도는 루트의 `THIRD_PARTY_DATA.md`에 있다.

## 테스트 정책

```powershell
# 작은 L0/L1 fixture만
.venv\Scripts\python.exe -m pytest -q

# 실제 44-frame dataset (없으면 준비 안내와 skip)
.venv\Scripts\python.exe -m pytest -m integration -q

# 네 profile × profile별 10 seeds
.venv\Scripts\python.exe -m pytest -m slow -q

# Blender backend (없으면 setup 안내와 skip)
.venv\Scripts\python.exe -m pytest -m pbr -q
```

clean은 wiring 회귀를 엄격히 검사한다. normal/hard/extreme 수치는 실측 합격 기준이
아니며 관찰용 stress envelope다. 실장비 calibration, 재질 분포, exposure/noise/PSF,
pass/fail mm threshold는 실제 rig 측정 전에는 결정할 수 없다.
