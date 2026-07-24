# XIMEA 실사 참고 held-out 검증

## 목적

기존 ideal generator와 decoder가 같은 수학적 가정을 공유해 정확도가 과대평가되는
`inverse crime` 위험을 줄이기 위한 별도 L1 stress 프로파일이다. 사용자가 제공한
XIMEA TIFF 9장은 패턴 순서, 카메라 자세, 초점과 실제 높이가 통제되지 않았으므로
phase/height ground truth로 사용하지 않는다. 관측 가능한 영상-domain 특성만
held-out seed의 nuisance 분포에 반영하며 production decoder threshold는 바꾸지 않는다.

## 관측 자료와 적용 범위

원본은 모두 1936 x 1216, mono `uint8`이다. TIFF metadata에는 다음 정보가 있다.

- camera: `MC023MG-SY-UB`, serial `CAMAU2240014`
- black level: 2 DN, gain: 0, auto exposure: off
- `gammaY=0.47`, sharpening: 0, binning/decimation: 1
- 2--9번 exposure: 13970, 1번 exposure: 39417
- `sequenceIdx=-1`, `sequenceLength=0`

파일 번호는 실제 촬영 시간의 역순이며 유효한 camera sequence가 선언되어 있지 않다.
따라서 파일 번호를 pattern/phase 순서로 해석하지 않는다.

관측된 2% full-scale 이하 픽셀은 약 56.8--84.0%, sensor maximum 픽셀은
0--11.1%였다. 줄무늬 경계의 end-to-end blur proxy는 대략 sigma 0.5--3 px,
암부 residual은 약 0.3--0.5 DN이었다. 이 값은 각각 projector defocus, camera PSF,
표면, clipping의 합과 8-bit 양자화가 섞인 결과다. 개별 광학/센서 파라미터의
측정값으로 부르지 않는다.

`ximea_observed` 프로파일은 다음만 옮긴다.

- 8-bit output quantization과 2 DN 부근 black floor
- frame 내부가 아닌 scan/sequence 단위 exposure 및 blur 변화
- 중앙 projection footprint와 큰 암부 점유율
- 저주파 조명 불균일과 다중 스케일 표면 texture
- 국부 shadow/highlight 및 saturation stress
- 양자화가 포함된 dark residual proxy

관측된 큰 frame 간 이동은 정상 phase-step 내부 jitter로 넣지 않는다. 최종 rig
pose와 sample 간 pose 분포가 확정되지 않았고, 현재 합성 GT를 일관되게 변환하는
camera model도 없기 때문이다. reorder/drop/large-motion은 추후 복원 정확도가 아니라
sequence rejection을 평가하는 별도 adversarial test로 다룬다.

PSF, gamma/response curve, shot/read noise, lens distortion, camera/projector geometry와
metric height는 이 자료에서 식별하지 않는다. 특히 TIFF의 `gammaY=0.47`은 설정
anchor일 뿐 projector와 camera response를 분리한 측정치가 아니므로 주 프로파일에
그 값으로 고정하지 않는다.

## 실행

분석용 사본을 기본 위치에 둔 경우 다음 BAT 하나로 실사 특성 감사, clean 비교,
XIMEA-observed 시뮬레이션과 한 페이지 결과를 모두 만든다.

```powershell
.\run_ximea_observed_suite.bat
```

다른 위치를 직접 지정할 수도 있다.

```powershell
.\.venv\Scripts\python.exe tools\run_ximea_observed_suite.py `
  --capture-root "\\LEELAB\5-9. Non-Planer\0724pic" `
  --open
```

시작 화면은
`validation_results/ximea_observed/ximea_observed_index.html`이다. 원본 TIFF와
생성된 validation data/results는 `.gitignore` 대상이며, config에는 원본별 SHA-256과
전이 범위만 남는다.

## 해석

clean 대비 valid ratio가 크게 하락하거나 phase error가 증가하면 실제 영상-domain
특성에 대한 취약 가능성을 의미한다. 그래도 결과는 합성 GT에 대한 강건성 평가이며
실제 장비의 mm 정확도는 아니다. 최종 주장은 고정 카메라/프로젝터에서 정상 22-frame
sequence, dark/flat/PSF calibration capture와 등록된 높이/3D ground truth를 별도
held-out board로 취득한 뒤에만 할 수 있다.
