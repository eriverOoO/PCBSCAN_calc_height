# Height Map 계산 이론

이 문서는 현재 디코더에서 **사전에 높이를 알고 있는 시편 없이 사용할 수 있는 두 가지 로직**만 설명합니다.

```text
형상 변화만 보기    -> 기준 시편 없이 가능(relative)
평면 대비 변화 보기 -> 평평한 기준면 필요(reference)
```

여기서 말하는 height map은 물리 단위 높이(mm)가 아니라, 구조광 phase를 높이처럼 시각화한 상대 map입니다.

## 전체 계산 흐름

구조광/FPP(Fringe Projection Profilometry)에서는 프로젝터가 PCB 위에 여러 장의 패턴을 투사하고, 카메라가 그 패턴을 촬영합니다. 현재 구현은 Gray code와 4-step phase shifting을 함께 사용합니다.

두 로직의 공통 전처리 흐름은 다음과 같습니다.

```text
패턴 이미지
→ 단일 intensity 이미지 변환
→ White/Black 보정
→ Gray code로 stripe index k 계산
→ 4-step sine 패턴으로 wrapped phase phi 계산
→ absolute phase Phi = 2*pi*k + phi
```

그 다음 목적에 따라 두 갈래로 나뉩니다.

```text
relative 모드:
Phi 자체를 height map처럼 사용

reference 모드:
delta_phi = Phi_object - Phi_reference 를 height map처럼 사용
```

## 기호 정의

| 기호 | 의미 |
| --- | --- |
| `I_w` | White 패턴 촬영 이미지 |
| `I_b` | Black 패턴 촬영 이미지 |
| `I_n` | n번째 패턴 촬영 이미지 |
| `S` | White/Black 차이로 추정한 신호 세기 |
| `T` | Gray code 이진화를 위한 threshold |
| `G_i` | i번째 Gray code bit 이미지 |
| `G_i_inv` | i번째 반전 Gray code bit 이미지 |
| `b_i` | i번째 Gray bit의 이진값 |
| `k` | Gray code에서 얻은 stripe index |
| `I_0, I_90, I_180, I_270` | 4-step sine phase shifting 이미지 |
| `phi` | 한 주기 안의 wrapped phase |
| `Phi` | Gray code와 sine phase를 결합한 absolute phase |
| `Phi_object` | 대상 scan의 absolute phase |
| `Phi_reference` | 평면 기준 scan의 absolute phase |
| `delta_phi` | 대상 scan과 기준 scan의 phase 차이 |
| `h_relative` | relative 모드의 phase 기반 height map |
| `h_reference` | reference 모드의 기준 평면 대비 phase 차이 map |

## 1. 입력 intensity 변환

카메라 이미지가 흑백이면 그대로 float intensity로 사용합니다. RGB 이미지이면 설정된 입력 색상 모드에 따라 단일 intensity 이미지로 변환합니다.

대표적인 변환은 다음과 같습니다.

```text
blue mode:
I = B

red mode:
I = R

green mode:
I = G

luminance mode:
I = 0.299R + 0.587G + 0.114B

max_rgb mode:
I = max(R, G, B)
```

색상 cross-talk 보정 행렬이 주어지면 먼저 RGB 벡터를 분리합니다. 촬영 RGB가 실제 RGB에 3x3 행렬 `K`가 곱해진 결과라고 보면 다음과 같습니다.

```text
captured_rgb = K * true_rgb
true_rgb = inverse(K) * captured_rgb
```

그 뒤 원하는 채널을 선택해 이후 계산에 사용합니다.

## 2. White/Black 보정

카메라 영상에는 조명 불균일, 렌즈 비네팅, PCB 반사율 차이, 카메라 offset이 섞여 있습니다. White와 Black 패턴은 이 영향을 줄이기 위해 사용합니다.

각 픽셀의 신호 세기는 다음처럼 정의합니다.

```text
S = I_w - I_b
```

Gray code 이진화를 위한 기본 threshold는 White와 Black의 중간값입니다.

```text
T = (I_w + I_b) / 2
```

각 패턴 이미지는 다음처럼 0..1 범위로 정규화합니다.

```text
I_corr = clip((I_n - I_b) / max(S, epsilon), 0, 1)
```

여기서 `epsilon`은 0 나눗셈을 막기 위한 작은 값입니다.

유효 픽셀 mask는 다음 조건으로 만듭니다.

```text
valid_signal = S > min_signal
saturation_pass = I_w < saturation_threshold
dark_pass = I_w > dark_threshold

valid_white_black = valid_signal AND saturation_pass AND dark_pass
```

즉 White와 Black 차이가 너무 작거나, White가 포화됐거나, White가 너무 어두운 픽셀은 신뢰하지 않습니다.

## 3. Gray code로 stripe index 계산

Sine phase만 사용하면 phase가 `0..2*pi` 범위에서 반복되므로 전체 패턴 중 어느 주기인지 알 수 없습니다. Gray code는 이 주기 번호를 정수 `k`로 찾기 위해 사용합니다.

### 일반 Gray code 모드

반전 Gray 패턴이 없으면 각 Gray 이미지를 threshold와 비교합니다.

```text
b_i = 1 if G_i > T else 0
```

또는 White/Black 보정 후 0.5를 기준으로 이진화할 수 있습니다.

```text
b_i = 1 if G_i_corr > 0.5 else 0
```

### 반전 Gray pair 모드

14..21번 반전 Gray 패턴이 있으면 정상 Gray와 반전 Gray를 직접 비교합니다.

```text
diff_i = G_i_corr - G_i_inv_corr
b_i = 1 if diff_i > 0 else 0
confidence_i = abs(diff_i)
```

현재 구현에서는 모든 bit의 confidence 중 최솟값을 해당 픽셀의 Gray confidence로 사용합니다.

```text
confidence = min_i(confidence_i)
```

반전 Gray pair 모드에서는 이 값이 `gray_pair_min_contrast`보다 작으면 Gray code가 불안정한 픽셀로 판단합니다.

```text
valid_gray = confidence >= gray_pair_min_contrast
```

### Gray code 정수 변환

Gray bit들은 MSB-first 순서로 정수화합니다.

```text
gray_value = b_0 * 2^(N-1) + b_1 * 2^(N-2) + ... + b_(N-1)
```

이 값은 Gray code 정수이므로 binary 정수로 변환해야 합니다. Gray code는 인접 stripe 사이에서 bit 하나만 바뀌도록 설계된 코드입니다. binary 변환은 prefix XOR로 표현할 수 있습니다.

```text
binary_0 = gray_0
binary_i = binary_(i-1) XOR gray_i
```

최종 stripe index는 다음과 같습니다.

```text
k = gray_to_binary(gray_value)
```

## 4. 4-step phase shifting

Gray code가 정수 주기 번호를 준다면, phase shifting은 한 주기 내부의 연속 위치를 줍니다. 현재 구현은 4-step PSP(Phase Shifting Profilometry)를 사용합니다.

한 픽셀의 sine intensity는 이상적으로 다음처럼 쓸 수 있습니다.

```text
I(theta) = A + B * cos(phi + theta)
```

여기서:

```text
A = 평균 밝기
B = modulation amplitude
phi = 찾고 싶은 phase
theta = 투사한 phase shift
```

4-step에서는 `theta = 0, pi/2, pi, 3*pi/2`에 해당하는 네 장을 사용합니다.

```text
I_0
I_90
I_180
I_270
```

현재 기본 convention은 다음입니다.

```text
y = I_0 - I_180
x = I_270 - I_90

phi_wrapped = atan2(y, x)
```

`atan2` 결과는 `[-pi, pi]` 범위이므로, 이후 `[0, 2*pi)` 범위로 변환합니다.

```text
phi = phi_wrapped mod 2*pi
```

설정에 따라 phase convention을 바꿀 수 있습니다.

```text
default:
phi_wrapped = atan2(I_0 - I_180, I_270 - I_90)

negated:
phi_wrapped = -atan2(I_0 - I_180, I_270 - I_90)

swapped:
phi_wrapped = atan2(I_270 - I_90, I_0 - I_180)
```

프로젝터 좌표 방향이 반대로 해석될 때는 `phase_direction=reverse`를 사용합니다.

```text
k_reverse = max_k - k
phi_reverse = (2*pi - phi) mod 2*pi
```

## 5. Modulation과 sine 유효성

4-step phase shifting에서 modulation은 sine 신호가 얼마나 뚜렷한지를 나타냅니다.

현재 구현의 modulation은 다음과 같습니다.

```text
quadrature = I_270 - I_90
in_phase = I_0 - I_180

M = 0.5 * sqrt(quadrature^2 + in_phase^2)
```

평균 밝기로 정규화한 modulation도 계산합니다.

```text
I_mean = (I_0 + I_90 + I_180 + I_270) / 4
M_norm = M / max(I_mean, epsilon)
```

height map에 쓰는 유효성 판정은 기본적으로 절대 modulation `M`을 사용합니다.

```text
valid_modulation = M > modulation_threshold
```

PCB의 검은 부품, 그림자, 포화된 납땜부처럼 sine 변화가 거의 보이지 않는 영역은 이 조건에서 제외될 수 있습니다.

## 6. Absolute phase 생성

Gray code의 `k`는 몇 번째 `2*pi` 구간인지 알려주고, sine phase `phi`는 그 구간 안의 위치를 알려줍니다. 따라서 absolute phase는 다음과 같습니다.

```text
Phi_raw = 2*pi*k + phi
```

최종 phase 유효 mask는 여러 조건의 교집합입니다.

```text
valid_phase =
    valid_white_black
    AND valid_modulation
    AND valid_gray
    AND isfinite(Phi_raw)
```

유효하지 않은 픽셀의 `Phi`는 `NaN`으로 처리합니다.

```text
Phi = Phi_raw if valid_phase else NaN
```

## 7. Gray/phase 경계 보정

Gray code 경계와 sine phase 경계가 픽셀 단위에서 정확히 맞지 않으면 absolute phase가 `2*pi`만큼 튀는 현상이 생길 수 있습니다. 현재 구현에는 선택 사항으로 휴리스틱 경계 보정이 들어 있습니다.

후보 픽셀은 다음 두 조건을 만족하는 곳입니다.

```text
phi < boundary_margin
OR
phi > 2*pi - boundary_margin
```

그리고 주변에서 stripe index `k`가 바뀌는 경계 근처여야 합니다.

후보 픽셀에 대해 `k-1`, `k`, `k+1`을 비교하고, 주변 3x3 median absolute phase와 가장 가까운 값을 선택합니다.

```text
Phi_candidate(k') = 2*pi*k' + phi
k' in {k-1, k, k+1}

choose k' minimizing abs(Phi_candidate(k') - local_median)
```

이 보정은 정확한 unwrap 알고리즘이라기보다 Gray 경계 주변의 국소적인 `2*pi` 점프를 줄이기 위한 안전장치입니다.

## 8. Relative 모드: 형상 변화만 보기

`relative` 모드는 기준 시편이나 기준 평면 없이 실행할 수 있습니다. 이 모드에서는 absolute phase 자체를 height map처럼 사용합니다.

```text
h_relative = Phi
```

이 값은 실제 높이(mm)가 아닙니다. 단위는 phase입니다. 따라서 `relative` 결과는 다음 목적에 적합합니다.

- 입력 패턴이 정상적으로 촬영됐는지 확인
- Gray code와 sine phase가 잘 결합되는지 확인
- 표면의 상대적인 형상 변화, 경향, 불연속 영역 확인
- 기준 평면이나 보정 데이터가 없을 때의 빠른 preview

하지만 다음 해석에는 적합하지 않습니다.

- 실제 높이 mm 계산
- 두 장비 또는 두 촬영 조건 사이의 절대 높이 비교
- 프로젝터 기울기나 keystone 성분이 제거된 높이 해석

`relative` 모드의 결과에는 평평한 판을 찍어도 투영 기하 때문에 phase 기울기가 남을 수 있습니다. 즉 표면 높이 변화와 시스템 기하 성분이 함께 섞여 있습니다.

## 9. Reference 모드: 평면 대비 변화 보기

`reference` 모드는 평평한 기준면 scan이 필요합니다. 기준면의 실제 높이를 정확히 알고 있을 필요는 없지만, 대상 scan과 같은 카메라/프로젝터 자세, 초점, 노출 조건에서 촬영된 평면이어야 합니다.

기준 평면 absolute phase를 다음처럼 둡니다.

```text
Phi_reference(x, y)
```

대상 scan의 absolute phase는 다음입니다.

```text
Phi_object(x, y)
```

reference 모드는 두 phase의 차이를 계산합니다.

```text
delta_phi(x, y) = Phi_object(x, y) - Phi_reference(x, y)
```

최종 map은 다음과 같습니다.

```text
h_reference = sign * delta_phi
```

여기서 `sign`은 `--height-sign` 설정입니다.

이 모드의 의미는 “기준 평면 대비 phase 차이”입니다. 평평한 기준면에서 이미 존재하던 프로젝터 기울기, 사다리꼴 투영, 큰 배경 phase 성분을 상당 부분 제거할 수 있습니다.

```text
relative:
h = Phi_object

reference:
h = Phi_object - Phi_reference
```

따라서 `reference` 모드는 다음 목적에 적합합니다.

- 평면 기준 대비 PCB 표면 변화 보기
- 프로젝터 기울기/keystone에 의한 배경 phase 제거
- 같은 장비 조건에서 object scan끼리 더 안정적으로 비교
- 실제 mm 보정 전 단계의 상대 높이 분석

하지만 `reference` 모드도 실제 높이(mm)는 아닙니다. 기준 평면을 뺐더라도 `delta_phi`를 물리 높이로 바꾸는 보정 모델은 적용하지 않기 때문입니다.

## 10. 두 모드의 차이

| 항목 | relative | reference |
| --- | --- | --- |
| 기준 평면 scan | 필요 없음 | 필요 |
| 높이를 아는 시편 | 필요 없음 | 필요 없음 |
| 출력 의미 | absolute phase preview | 기준 평면 대비 phase 차이 |
| 물리 단위(mm) | 아님 | 아님 |
| 투영 기하 성분 제거 | 안 됨 | 상당 부분 제거 |
| 추천 용도 | 빠른 확인, 형상 경향 보기 | 평면 대비 변화 보기 |

정리하면 다음과 같습니다.

```text
relative:
형상 변화만 빠르게 보고 싶을 때 사용
사전 기준 시편 없음
평면 기준 scan 없음

reference:
평면 대비 변화를 보고 싶을 때 사용
사전 높이 시편은 필요 없음
단, 같은 조건의 평평한 기준면 scan은 필요
```

## 11. Analysis ROI의 역할

ArUco 기반 analysis ROI를 켜면 전체 이미지 중 실제 분석 대상 영역만 height 계산에 사용합니다. 수식 자체는 바뀌지 않지만 mask가 추가로 곱해집니다.

```text
valid_white_black = valid_white_black AND roi_mask
valid_gray = valid_gray AND roi_mask
valid_modulation = valid_modulation AND roi_mask
valid_phase = valid_phase AND roi_mask
```

PCB 주변의 종이, 마커, 배경이 height map에 섞이지 않도록 제외하는 용도입니다. `relative`와 `reference` 모두 같은 방식으로 ROI mask가 적용됩니다.

## 12. 후처리

### Median filter

`median_filter`가 1보다 크면 height map에 median filter를 적용합니다. 이는 고립된 salt-and-pepper 잡음을 줄입니다.

```text
h_filtered(x, y) = median(h in local window)
```

mask 밖 픽셀은 계속 `NaN`으로 유지합니다.

### Plane detrend

`detrend`를 켜면 유효 픽셀 전체에 평면을 최소제곱으로 맞춘 뒤 제거합니다.

평면 모델은 다음입니다.

```text
z_plane(x, y) = a*x + b*y + c
```

유효 픽셀의 height 값 `h(x, y)`에 대해 최소제곱 문제를 풉니다.

```text
minimize sum((h(x, y) - (a*x + b*y + c))^2)
```

그 다음:

```text
h_detrended = h - z_plane
```

이 기능은 전체 기울기를 제거해 국소 표면 변화를 보기 좋게 만드는 용도입니다. 특히 `relative` 모드에서는 투영 기하에 의한 큰 기울기가 남을 수 있으므로 preview 개선에 도움이 될 수 있습니다. 다만 절대적인 기준면 대비 phase 차이를 그대로 보고 싶다면 `detrend` 사용 여부를 해석에 반영해야 합니다.

## 13. 유효하지 않은 픽셀이 생기는 주요 이유

height map에서 `NaN` 또는 mask 제외 픽셀이 생기는 것은 계산 실패라기보다 신뢰할 수 없는 측정값을 제거한 결과입니다. 대표적인 원인은 다음과 같습니다.

- White/Black 차이가 너무 작아 패턴 contrast가 부족함
- White 이미지가 포화됨
- 대상 영역이 너무 어두움
- sine modulation이 threshold보다 낮음
- Gray code와 반전 Gray pair의 차이가 작음
- reference 모드에서 기준 phase가 없거나 대상 phase와 shape가 맞지 않음
- analysis ROI 밖에 있는 픽셀임

## 구현 관점의 요약

공통 phase 계산은 다음 네 줄로 요약할 수 있습니다.

```text
k = GrayToBinary(GrayBits)
phi = atan2(I_0 - I_180, I_270 - I_90) mod 2*pi
Phi = 2*pi*k + phi
valid_phase = valid_white_black AND valid_modulation AND valid_gray
```

두 height map 로직은 다음입니다.

```text
relative:
h_relative = Phi

reference:
delta_phi = Phi_object - Phi_reference
h_reference = sign * delta_phi
```

이 두 모드에서 정확한 결과를 얻기 위해 중요한 조건은 다음입니다.

1. White/Black contrast가 충분해야 합니다.
2. Gray code bit가 안정적으로 분리되어야 합니다.
3. Sine modulation이 충분해야 합니다.
4. reference 모드에서는 기준 평면 scan이 대상 scan과 같은 기하 조건에서 촬영되어야 합니다.
5. 기준 평면 자체는 가능한 한 평평하고, 대상 scan과 같은 위치/초점/노출 조건을 가져야 합니다.
