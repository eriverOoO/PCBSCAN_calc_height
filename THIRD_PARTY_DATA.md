# Third-party validation data

외부 dataset이나 model 자체는 이 저장소에 포함하지 않는다. 실제 사용 시 downloader가
생성하는 `LICENSE_AND_CITATION.json`과 upstream license를 함께 보관한다.

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
- License: dataset card의 현재 license를 download/사용 시 확인하고 provenance에 기록한다.

## KiCad/StepUp

- KiCad libraries: https://www.kicad.org/libraries/download/
- KiCad StepUp: https://www.kicad.org/external-tools/stepup/
- Scope: PCB 3D model 및 STEP→GLB/glTF 변환 경로
- License: 선택한 개별 library/model의 license와 원본 URL을 scene별 provenance에 기록한다.

인터넷의 일반 PCB 사진은 albedo 참고만 가능하다. 서로 다른 사진을 pattern sequence로
위장하거나 생성형 이미지 모델 결과를 decoder 입력으로 사용하지 않는다.
