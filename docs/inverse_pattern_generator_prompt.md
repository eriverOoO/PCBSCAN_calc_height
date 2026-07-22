# PCB 구조광 역 패턴 이미지 생성기 — 독립 레포지토리 구현 프롬프트

## 개요

이 문서는 **PCB 구조광 역 패턴 이미지 생성기**를 **독립된 새 레포지토리**로 구현하기 위한 프롬프트입니다.

> **중요**: 이 프로그램은 기존 `Non-planar_calc`(`pcb_fpp_decoder`) 레포지토리와 **별도의 독립 프로젝트**로 생성합니다. `pcb_fpp_decoder`를 import하지 않으며, 필요한 수학 공식과 패턴 생성 로직은 자체 구현합니다.

### 목적

구조광(Structured Light) / FPP(Fringe Projection Profilometry) 시스템에서 프로젝터는 일반적으로 **평면 패턴**(Gray code, 4-step PSP sine)을 투사합니다. PCB 표면에 높이 변화가 있으면 카메라에서 촬영된 패턴이 왜곡되고, 이를 디코딩하여 높이 지도를 복원합니다.

이 역 생성기는 **반대 방향**으로 동작합니다:

- **입력**: 실제 PCB 이미지(높이 맵 또는 실물 PCB 사진) + 광학 기하 파라미터
- **출력**: PCB의 높이 프로파일을 고려하여 **왜곡이 역보정된 프로젝터 투사용 패턴 이미지** 22장

이 이미지들을 프로젝터로 투사하면, PCB 표면의 비평면 높이 변화에 의한 왜곡이 상쇄되어 카메라에서 촬영했을 때 **이상적인 평면 패턴과 동일한 결과**를 얻을 수 있습니다.

---

## 참조: 기존 디코더 시스템 (Non-planar_calc)

이 생성기는 아래 디코더와 **호환되는 출력**을 만드는 것이 목표이지만, 코드 의존성은 없습니다. 아래는 호환을 위해 알아야 할 정보입니다.

### 패턴 규약 (22장)

기존 디코더가 기대하는 입력 패턴 순서입니다. 역 생성기도 이 규약을 정확히 따라야 합니다.

```text
ID  Label           설명
──  ──────────────  ─────────────────────────
00  White           전체 밝은 이미지
01  Black           전체 어두운 이미지
02  Gray0 (MSB)     Gray code bit plane 0 (최상위 비트)
03  Gray1           Gray code bit plane 1
04  Gray2           Gray code bit plane 2
05  Gray3           Gray code bit plane 3
06  Gray4           Gray code bit plane 4
07  Gray5           Gray code bit plane 5
08  Gray6           Gray code bit plane 6
09  Gray7 (LSB)     Gray code bit plane 7 (최하위 비트)
10  Sine_000        4-step PSP, phase shift = 0°
11  Sine_090        4-step PSP, phase shift = 90°
12  Sine_180        4-step PSP, phase shift = 180°
13  Sine_270        4-step PSP, phase shift = 270°
14  Gray0_inv       Gray0의 논리 반전
15  Gray1_inv       Gray1의 논리 반전
16  Gray2_inv       Gray2의 논리 반전
17  Gray3_inv       Gray3의 논리 반전
18  Gray4_inv       Gray4의 논리 반전
19  Gray5_inv       Gray5의 논리 반전
20  Gray6_inv       Gray6의 논리 반전
21  Gray7_inv       Gray7의 논리 반전
```

### 디코더 호환 파일 명명 규약

디코더는 다음 파일명을 인식합니다. 역 생성기의 `all/` 폴더 출력은 이 규약을 따라야 합니다.

```text
pattern_000.png  ~  pattern_021.png
```

### 높이 계산 공식 (삼각측량)

디코더가 사용하는 삼각측량 공식입니다. 역 생성기는 이 공식을 **역방향**으로 사용합니다.

```text
h = sign × (Δφ × p × d) / (Δφ × p + 2π × l)

여기서:
  h  = PCB 표면 높이 (mm, 기준면 대비)
  Δφ = φ_object - φ_reference  (대상 위상 - 기준 평면 위상)
  d  = 카메라-기준면 거리 (mm)
  l  = 카메라-프로젝터 기선 거리 (mm)
  p  = 프로젝터 줄무늬 주기 (프로젝터 px 또는 등가 위상-높이 주기)
  sign = 높이 부호 (+1 또는 -1, 기하 구성에 따라 결정)
```

### 기존 디코더 보정 설정 파일 형식

기존 디코더는 JSON 보정 설정 파일을 사용합니다. 역 생성기도 이 형식을 읽을 수 있어야 합니다.

```json
{
  "geometry": {
    "d": 300.0,
    "l": 120.0,
    "p": 5.0
  },
  "projector": {
    "tilt_degrees": 30.0
  }
}
```

키 탐색 순서 (`d`의 예):
1. `geometry.d`
2. `d`
3. `distance_d`
4. `geometry.distance_d`

---

## 레포지토리 구조

```text
PCB_Inverse_Pattern_Generator/          ← 새 독립 레포지토리
├── inverse_pattern_generator/          ← Python 패키지
│   ├── __init__.py                    ← 패키지 초기화, 공개 API
│   ├── generator.py                   ← 핵심 역 패턴 생성 파이프라인
│   ├── height_loader.py               ← 높이 맵 로딩 (npy, png, PCB 이미지)
│   ├── pattern_templates.py           ← 이상적 평면 패턴 22장 생성
│   ├── distortion.py                  ← 높이→왜곡 맵 계산 (역 삼각측량)
│   ├── calibration_loader.py          ← 보정 설정 JSON/NPZ 로딩
│   ├── cli.py                         ← 명령줄 인터페이스
│   ├── gui.py                         ← tkinter 그래픽 인터페이스
│   └── io.py                          ← 이미지 저장, 폴더 분류
├── scripts/
│   ├── generate_inverse_patterns.py   ← CLI 진입점
│   └── run_inverse_gui.py             ← GUI 진입점
├── tests/
│   ├── test_pattern_templates.py      ← 패턴 생성 테스트
│   ├── test_distortion.py             ← 왜곡 계산 테스트
│   ├── test_generator.py              ← 통합 테스트
│   └── test_io.py                     ← 저장/로딩 테스트
├── examples/
│   └── calibration_config.example.json ← 보정 설정 예시
├── build.bat                          ← PyInstaller EXE 빌드 스크립트
├── requirements.txt                   ← Python 의존성
├── .gitignore
└── README.md                          ← 사용 설명서
```

---

## 구현 요구사항

### 1. `requirements.txt`

```text
numpy>=1.23
pillow>=9.0
matplotlib>=3.6
scipy>=1.9
opencv-contrib-python>=4.7
pytest>=7.0
```

> 기존 `pcb_fpp_decoder`와 동일한 의존성이지만 `pcb_fpp_decoder` 자체는 의존하지 않습니다.

### 2. `.gitignore`

```text
__pycache__/
*.pyc
*.pyo
.venv/
dist/
build/
*.egg-info/
*.spec
inverse_patterns/
```

### 3. 핵심 모듈 상세

#### 3.1 `pattern_templates.py` — 이상적 평면 패턴 생성

프로젝터 해상도(기본 1280×800)에 맞는 이상적인 평면 패턴 22장을 생성합니다.

```python
"""이상적 구조광 패턴 22장을 프로젝터 해상도에 맞게 생성합니다."""

from __future__ import annotations
import math
import numpy as np

PATTERN_LABELS = {
    0: "white", 1: "black",
    2: "gray0", 3: "gray1", 4: "gray2", 5: "gray3",
    6: "gray4", 7: "gray5", 8: "gray6", 9: "gray7",
    10: "sine_000", 11: "sine_090", 12: "sine_180", 13: "sine_270",
    14: "gray0_inv", 15: "gray1_inv", 16: "gray2_inv", 17: "gray3_inv",
    18: "gray4_inv", 19: "gray5_inv", 20: "gray6_inv", 21: "gray7_inv",
}


def binary_to_gray(n: int) -> int:
    """이진수를 Gray code로 변환합니다."""
    return n ^ (n >> 1)


def generate_flat_patterns(
    projector_width: int = 1280,
    projector_height: int = 800,
    gray_bits: int = 8,
    sine_periods: int | None = None,
) -> dict[int, np.ndarray]:
    """
    프로젝터 해상도에 맞는 이상적 평면 패턴 22장을 생성합니다.

    Parameters
    ----------
    projector_width : int
        프로젝터 가로 해상도 (기본 1280).
    projector_height : int
        프로젝터 세로 해상도 (기본 800).
    gray_bits : int
        Gray code 비트 수 (기본 8). 2^gray_bits 개의 줄무늬를 생성합니다.
    sine_periods : int or None
        PSP sine 패턴의 주기 수. None이면 2^gray_bits와 동일하게 설정합니다.

    Returns
    -------
    dict[int, np.ndarray]
        pattern_id -> float32 이미지 (0.0~1.0 범위) 딕셔너리.
        패턴 22장: White(0), Black(1), Gray0-7(2-9),
        Sine 0/90/180/270(10-13), Gray0_inv-Gray7_inv(14-21).
    """
    if sine_periods is None:
        sine_periods = 1 << gray_bits   # 2^gray_bits

    patterns: dict[int, np.ndarray] = {}

    # 00: White — 전체 1.0
    patterns[0] = np.ones((projector_height, projector_width), dtype=np.float32)

    # 01: Black — 전체 0.0
    patterns[1] = np.zeros((projector_height, projector_width), dtype=np.float32)

    # 02..09: Gray code bit planes (MSB → LSB)
    num_stripes = 1 << gray_bits
    col_indices = np.arange(projector_width, dtype=np.uint32)
    stripe_k = np.clip(
        (col_indices * num_stripes) // projector_width, 0, num_stripes - 1
    )
    gray_values = np.vectorize(binary_to_gray)(stripe_k)

    for bit_idx in range(gray_bits):
        bit_position = gray_bits - 1 - bit_idx   # MSB first
        bit_plane_1d = ((gray_values >> bit_position) & 1).astype(np.float32)
        patterns[2 + bit_idx] = np.tile(
            bit_plane_1d[np.newaxis, :], (projector_height, 1)
        )

    # 10..13: 4-step PSP sine patterns
    x = np.arange(projector_width, dtype=np.float32)
    base_phase = 2.0 * math.pi * sine_periods * x / projector_width
    for i, shift in enumerate([0.0, math.pi / 2, math.pi, 3 * math.pi / 2]):
        sine_1d = 0.5 + 0.5 * np.cos(base_phase + shift)
        patterns[10 + i] = np.tile(
            sine_1d.astype(np.float32)[np.newaxis, :], (projector_height, 1)
        )

    # 14..21: 반전 Gray code (논리 NOT)
    for bit_idx in range(gray_bits):
        patterns[14 + bit_idx] = 1.0 - patterns[2 + bit_idx]

    return patterns
```

구현 포인트:
- `stripe_k = (col × num_stripes) // W` — 각 프로젝터 열의 stripe 인덱스
- Gray code: `binary_to_gray(k) = k ^ (k >> 1)`
- Sine: `I = 0.5 + 0.5 × cos(2π × periods × x / W + shift)`
- 반전 Gray: `1.0 - pattern`

#### 3.2 `calibration_loader.py` — 보정 설정 로딩 (자체 구현)

기존 디코더의 JSON/NPZ 보정 파일 형식을 자체적으로 읽습니다.

```python
"""보정 설정 파일에서 광학 기하 파라미터를 로딩합니다.

기존 PCB FPP Decoder의 calibration JSON/NPZ 형식과 호환됩니다.
pcb_fpp_decoder를 import하지 않고 자체 구현합니다.
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class GeometryParams:
    """삼각측량에 필요한 광학 기하 파라미터."""
    d: float          # 카메라-기준면 거리 (mm)
    l: float          # 카메라-프로젝터 기선 거리 (mm)
    p: float          # 프로젝터 줄무늬 주기
    tilt_degrees: float | None = None  # 프로젝터 기울기 (도)


def load_geometry_from_file(path: Path) -> GeometryParams | None:
    """
    JSON 또는 NPZ 보정 파일에서 d, l, p를 로딩합니다.

    JSON 키 탐색 순서 (d의 예):
      geometry.d → d → distance_d → geometry.distance_d

    Parameters
    ----------
    path : Path
        보정 설정 파일 (.json 또는 .npz).

    Returns
    -------
    GeometryParams or None
        d, l, p가 모두 발견되면 GeometryParams, 아니면 None.
    """
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"보정 파일이 존재하지 않습니다: {path}")

    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        d = _find_float(data, "geometry.d", "d", "distance_d", "geometry.distance_d")
        l = _find_float(data, "geometry.l", "l", "baseline_l", "geometry.baseline_l")
        p = _find_float(
            data, "geometry.p", "p", "pattern_period_p",
            "pattern_period", "geometry.pattern_period_p",
        )
        tilt = _find_float(
            data, "projector.tilt_degrees", "projector_tilt_degrees",
            "optics.projector_tilt_degrees",
        )
        if d is not None and l is not None and p is not None:
            return GeometryParams(d=d, l=l, p=p, tilt_degrees=tilt)
        return None

    if path.suffix.lower() == ".npz":
        with np.load(path) as npz:
            arrays = {key: np.asarray(npz[key]) for key in npz.files}
        # NPZ에서 스칼라 값 추출
        d = _npz_scalar(arrays, "d")
        l = _npz_scalar(arrays, "l")
        p = _npz_scalar(arrays, "p")
        if d is not None and l is not None and p is not None:
            return GeometryParams(d=d, l=l, p=p)
        return None

    raise ValueError(f"지원하지 않는 보정 파일 형식: {path.suffix}")


def _find_float(data: dict[str, Any], *dotted_keys: str) -> float | None:
    """중첩 딕셔너리에서 점 구분 키 경로를 탐색합니다."""
    for key in dotted_keys:
        value = _deep_get(data, key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _deep_get(data: dict[str, Any], dotted_key: str) -> Any:
    """점(.)으로 구분된 키 경로를 따라 값을 찾습니다."""
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _npz_scalar(arrays: dict[str, np.ndarray], key: str) -> float | None:
    """NPZ 배열에서 스칼라 값을 추출합니다."""
    if key not in arrays:
        return None
    arr = np.asarray(arrays[key], dtype=np.float64)
    if arr.ndim == 0:
        return float(arr)
    return float(np.mean(arr))
```

#### 3.3 `height_loader.py` — 높이 맵 로딩

```python
"""다양한 소스에서 높이 맵을 로딩합니다.

지원 입력:
  - .npy: 디코더 출력의 height_mm.npy 등
  - .npz: 'height' 키를 가진 archive
  - .png/.jpg/.bmp/.tif: 그레이스케일 이미지 → 밝기를 높이로 매핑
  - 디렉토리: 디코더 출력 폴더 (height/ 하위 자동 검색)
"""

from __future__ import annotations
from pathlib import Path
import numpy as np


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

# 디코더 출력 폴더에서 높이 맵을 찾는 우선순위
_HEIGHT_FILE_CANDIDATES = [
    "height/height_mm.npy",
    "height/height_relative.npy",
    "height/height_fused.npy",
    "height/height.npy",
]


def load_height_map(
    path: Path,
    projector_width: int = 1280,
    projector_height: int = 800,
    max_height_mm: float = 5.0,
) -> np.ndarray:
    """
    높이 맵을 로딩하고 프로젝터 해상도에 맞게 리사이즈합니다.

    Parameters
    ----------
    path : Path
        높이 맵 파일 또는 디코더 출력 디렉토리.
    projector_width, projector_height : int
        최종 리사이즈 타겟 해상도.
    max_height_mm : float
        그레이스케일 이미지를 높이로 변환할 때의 최대 높이 (mm).

    Returns
    -------
    np.ndarray
        float32, shape (projector_height, projector_width), 단위 mm.
    """
    path = Path(path).expanduser().resolve()

    if path.is_dir():
        # 디코더 출력 폴더 자동 검색
        for candidate in _HEIGHT_FILE_CANDIDATES:
            candidate_path = path / candidate
            if candidate_path.exists():
                return _load_and_resize(
                    candidate_path, projector_width, projector_height, max_height_mm
                )
        raise FileNotFoundError(
            f"디코더 출력 폴더에서 높이 맵을 찾을 수 없습니다: {path}\n"
            f"다음 파일 중 하나가 필요합니다: {_HEIGHT_FILE_CANDIDATES}"
        )

    return _load_and_resize(path, projector_width, projector_height, max_height_mm)


def _load_and_resize(
    path: Path,
    target_w: int,
    target_h: int,
    max_height_mm: float,
) -> np.ndarray:
    """파일을 로딩하고 리사이즈합니다."""
    height = _load_raw(path, max_height_mm)
    height = np.where(np.isfinite(height), height, 0.0).astype(np.float32)

    if height.shape == (target_h, target_w):
        return height

    import cv2
    return cv2.resize(
        height, (target_w, target_h), interpolation=cv2.INTER_LINEAR
    ).astype(np.float32)


def _load_raw(path: Path, max_height_mm: float) -> np.ndarray:
    """파일 형식에 따라 높이 맵을 로딩합니다."""
    suffix = path.suffix.lower()

    if suffix == ".npy":
        return np.load(path).astype(np.float32)

    if suffix == ".npz":
        with np.load(path) as npz:
            for key in ("height", "height_mm", "height_relative", "z"):
                if key in npz:
                    return np.asarray(npz[key], dtype=np.float32)
            first_key = next(iter(npz.files))
            return np.asarray(npz[first_key], dtype=np.float32)

    if suffix in IMAGE_EXTENSIONS:
        return _image_to_height(path, max_height_mm)

    raise ValueError(f"지원하지 않는 파일 형식: {suffix}")


def _image_to_height(path: Path, max_height_mm: float) -> np.ndarray:
    """
    그레이스케일 이미지의 밝기를 높이로 선형 매핑합니다.

    밝기 0 → 높이 0 mm, 밝기 max → 높이 max_height_mm.
    실제 PCB 이미지를 넣으면 밝은 영역(납땜, 실크)이 높은 곳,
    어두운 영역(기판)이 낮은 곳으로 매핑됩니다.
    """
    from PIL import Image
    with Image.open(path) as img:
        gray = np.asarray(img.convert("L"), dtype=np.float32)
    # 0~255 → 0.0~max_height_mm
    return (gray / 255.0 * max_height_mm).astype(np.float32)
```

구현 포인트:
- **디코더 출력 폴더 자동 검색**: `height/height_mm.npy` → `height_relative.npy` → `height_fused.npy` → `height.npy` 순서
- **PCB 이미지 입력**: 실제 PCB 사진(컬러/그레이)을 넣으면 밝기→높이 선형 매핑 (`밝은 = 높음`)
- **리사이즈**: 프로젝터 해상도에 맞게 `cv2.resize`
- **NaN 처리**: `np.where(np.isfinite, h, 0.0)`

#### 3.4 `distortion.py` — 높이 기반 왜곡 맵 계산

```python
"""높이 맵에서 프로젝터 패턴 왜곡 맵을 계산합니다.

삼각측량 공식을 역으로 적용하여 높이 h에서 프로젝터 x 방향 이동량을 계산합니다.
"""

from __future__ import annotations
import math
import numpy as np


def compute_distortion_map(
    height_map: np.ndarray,
    d: float = 300.0,
    l: float = 120.0,
    p: float = 5.0,
    sign: float = 1.0,
    projector_tilt_degrees: float = 30.0,
) -> np.ndarray:
    """
    높이 맵에서 프로젝터 x 방향 픽셀 이동량(displacement map)을 계산합니다.

    역 삼각측량 공식:
        Δφ = 2π × l × h / (sign × p × d − h × p)
        Δx_inverse = −Δφ × p / (2π)

    Parameters
    ----------
    height_map : np.ndarray
        float32, shape (H, W), 단위 mm.
    d, l, p : float
        삼각측량 기하 파라미터.
    sign : float
        높이 부호.
    projector_tilt_degrees : float
        프로젝터 기울기 (메타데이터용).

    Returns
    -------
    np.ndarray
        float32, shape (H, W). 프로젝터 x 방향 이동량 (프로젝터 픽셀 단위).
    """
    h = np.asarray(height_map, dtype=np.float64)
    h = np.where(np.isfinite(h), h, 0.0)

    # 역 삼각측량: Δφ = 2π × l × h / (sign × p × d − h × p)
    denominator = sign * p * d - h * p
    safe_denom = np.where(np.abs(denominator) < 1e-9, np.nan, denominator)
    delta_phi = 2.0 * math.pi * l * h / safe_denom

    # 프로젝터 픽셀 이동량 (역보정이므로 부호 반전)
    displacement = -(delta_phi / (2.0 * math.pi)) * p

    displacement = np.where(np.isfinite(displacement), displacement, 0.0)
    return displacement.astype(np.float32)


def apply_distortion(
    pattern: np.ndarray,
    displacement_map: np.ndarray,
) -> np.ndarray:
    """
    패턴 이미지에 왜곡 맵을 적용합니다 (cv2.remap 기반).

    각 출력 픽셀 (y, x)는 입력 패턴의 (y, x + displacement[y, x]) 에서
    bilinear 보간합니다.

    Parameters
    ----------
    pattern : np.ndarray
        float32, shape (H, W), 이상적 평면 패턴 (0.0~1.0).
    displacement_map : np.ndarray
        float32, shape (H, W), x 방향 이동량.

    Returns
    -------
    np.ndarray
        float32, shape (H, W), 왜곡 적용된 패턴 (0.0~1.0).
    """
    import cv2

    H, W = pattern.shape[:2]
    map_y, map_x = np.indices((H, W), dtype=np.float32)
    map_x = map_x + displacement_map.astype(np.float32)

    warped = cv2.remap(
        pattern.astype(np.float32),
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return np.clip(warped, 0.0, 1.0).astype(np.float32)
```

**역 공식 유도**:

```text
원래 공식:  h = sign × (Δφ × p × d) / (Δφ × p + 2π × l)

Δφ에 대해 풀기:
  h × (Δφ × p + 2π × l)  = sign × Δφ × p × d
  h × Δφ × p + h × 2π × l = sign × Δφ × p × d
  Δφ × p × (sign × d − h) = h × 2π × l
  Δφ = (2π × l × h) / (p × (sign × d − h))
     = (2π × l × h) / (sign × p × d − h × p)

프로젝터 픽셀 이동:
  1 줄무늬 주기 = p 프로젝터 픽셀 = 2π 위상
  Δx = Δφ × p / (2π)

역보정(pre-distortion):  Δx_inverse = −Δx
```

#### 3.5 `io.py` — 폴더 분류 저장

```python
"""패턴 이미지를 분류별 폴더에 저장합니다."""

from __future__ import annotations
from pathlib import Path
import numpy as np
from PIL import Image

from .pattern_templates import PATTERN_LABELS

# 패턴 분류 그룹
FOLDER_CLASSIFICATION = {
    "white_black": [0, 1],
    "gray_code": [2, 3, 4, 5, 6, 7, 8, 9],
    "gray_code_inv": [14, 15, 16, 17, 18, 19, 20, 21],
    "psp_sine": [10, 11, 12, 13],
}


def save_pattern_set(
    patterns: dict[int, np.ndarray],
    output_dir: Path,
    bit_depth: int = 8,
) -> None:
    """
    패턴 이미지를 분류별 폴더에 저장합니다.

    출력 구조:
        output_dir/
        ├── all/                       ← 전체 패턴 (디코더 입력 호환)
        │   ├── pattern_000.png
        │   └── ... (22장)
        ├── white_black/
        │   ├── 00_white.png
        │   └── 01_black.png
        ├── gray_code/
        │   ├── 02_gray0.png ~ 09_gray7.png
        ├── gray_code_inv/
        │   ├── 14_gray0_inv.png ~ 21_gray7_inv.png
        └── psp_sine/
            ├── 10_sine_000.png ~ 13_sine_270.png
    """
    output_dir = Path(output_dir).expanduser().resolve()

    # all/ 폴더 (디코더 호환)
    all_dir = output_dir / "all"
    all_dir.mkdir(parents=True, exist_ok=True)

    # 분류 폴더 생성
    for folder_name in FOLDER_CLASSIFICATION:
        (output_dir / folder_name).mkdir(parents=True, exist_ok=True)

    # 저장
    for pid in sorted(patterns.keys()):
        pattern = patterns[pid]
        label = PATTERN_LABELS.get(pid, f"pattern_{pid:03d}")

        # all/ — 디코더 호환 이름
        _save_image(all_dir / f"pattern_{pid:03d}.png", pattern, bit_depth)

        # 분류 폴더 — 라벨 이름
        for folder_name, pid_list in FOLDER_CLASSIFICATION.items():
            if pid in pid_list:
                _save_image(
                    output_dir / folder_name / f"{pid:02d}_{label}.png",
                    pattern, bit_depth,
                )
                break


def _save_image(path: Path, image: np.ndarray, bit_depth: int = 8) -> None:
    """float32 (0.0~1.0) 이미지를 PNG로 저장합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.clip(image, 0.0, 1.0)
    if bit_depth == 16:
        Image.fromarray((arr * 65535).astype(np.uint16), mode="I;16").save(path)
    else:
        Image.fromarray((arr * 255).astype(np.uint8), mode="L").save(path)


def save_debug_outputs(
    debug_dir: Path,
    height_map: np.ndarray,
    displacement_map: np.ndarray,
    flat_patterns: dict[int, np.ndarray],
) -> None:
    """진단용 중간 산출물을 저장합니다."""
    debug_dir = Path(debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    np.save(debug_dir / "height_map.npy", height_map)
    np.save(debug_dir / "displacement_map.npy", displacement_map)

    # 높이 맵 미리보기
    _save_normalized_preview(debug_dir / "height_map_preview.png", height_map)

    # displacement 맵 미리보기 (0 = 중간 회색)
    d = np.where(np.isfinite(displacement_map), displacement_map, 0.0)
    d_abs_max = max(abs(float(np.min(d))), abs(float(np.max(d))), 1e-9)
    d_norm = (d / d_abs_max * 0.5 + 0.5).astype(np.float32)
    _save_image(debug_dir / "displacement_map_preview.png", d_norm, 8)

    # 이상적 평면 패턴
    flat_dir = debug_dir / "flat_patterns"
    flat_dir.mkdir(exist_ok=True)
    for pid, pat in flat_patterns.items():
        label = PATTERN_LABELS.get(pid, f"pattern_{pid:03d}")
        _save_image(flat_dir / f"{pid:02d}_{label}.png", pat, 8)


def _save_normalized_preview(path: Path, array: np.ndarray) -> None:
    """배열을 0~255로 정규화하여 미리보기 PNG를 저장합니다."""
    arr = np.where(np.isfinite(array), array, 0.0).astype(np.float32)
    lo, hi = float(np.min(arr)), float(np.max(arr))
    if abs(hi - lo) > 1e-9:
        norm = ((arr - lo) / (hi - lo) * 255).astype(np.uint8)
    else:
        norm = np.zeros_like(arr, dtype=np.uint8)
    Image.fromarray(norm, mode="L").save(path)
```

#### 3.6 `generator.py` — 핵심 생성 파이프라인

```python
"""역 패턴 생성 파이프라인을 조율합니다."""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .pattern_templates import PATTERN_LABELS


@dataclass
class InversePatternConfig:
    """역 패턴 생성기 설정."""
    # 프로젝터 해상도
    projector_width: int = 1280
    projector_height: int = 800
    gray_bits: int = 8
    sine_periods: int | None = None

    # 광학 기하 파라미터 (직접 지정용)
    d: float = 300.0
    l: float = 120.0
    p: float = 5.0
    height_sign: float = 1.0
    projector_tilt_degrees: float = 30.0

    # 높이 맵 소스
    height_source: Path | None = None
    max_height_mm: float = 5.0

    # 보정 설정 파일 (지정하면 d/l/p를 이 파일에서 우선 로딩)
    calibration_config: Path | None = None

    # 출력
    output_dir: Path = Path("inverse_patterns")
    output_bit_depth: int = 8

    # 진단
    save_debug: bool = False


class InversePatternGenerator:
    """높이 맵에서 역왜곡 패턴 22장을 생성합니다."""

    def __init__(self, config: InversePatternConfig):
        self.config = config

    def run(self) -> Path:
        """
        전체 파이프라인 실행:
          1. 높이 맵 로딩
          2. 보정 파라미터 결정
          3. 왜곡 맵(displacement) 계산
          4. 이상적 평면 패턴 22장 생성
          5. 각 패턴에 왜곡 적용
          6. 분류별 폴더에 저장
          7. 리포트 저장
        """
        from .height_loader import load_height_map
        from .pattern_templates import generate_flat_patterns
        from .distortion import compute_distortion_map, apply_distortion
        from .io import save_pattern_set, save_debug_outputs

        # 1. 높이 맵
        height_map = load_height_map(
            self.config.height_source,
            projector_width=self.config.projector_width,
            projector_height=self.config.projector_height,
            max_height_mm=self.config.max_height_mm,
        )

        # 2. 보정 파라미터
        d, l_val, p, sign = self._resolve_geometry()

        # 3. 왜곡 맵
        displacement_map = compute_distortion_map(
            height_map, d=d, l=l_val, p=p, sign=sign,
            projector_tilt_degrees=self.config.projector_tilt_degrees,
        )

        # 4. 이상적 평면 패턴
        flat_patterns = generate_flat_patterns(
            projector_width=self.config.projector_width,
            projector_height=self.config.projector_height,
            gray_bits=self.config.gray_bits,
            sine_periods=self.config.sine_periods,
        )

        # 5. 왜곡 적용
        distorted: dict[int, np.ndarray] = {}
        for pid, pattern in flat_patterns.items():
            distorted[pid] = apply_distortion(pattern, displacement_map)

        # 6. 저장
        out = Path(self.config.output_dir).expanduser().resolve()
        save_pattern_set(distorted, out, bit_depth=self.config.output_bit_depth)

        # 디버그 출력
        if self.config.save_debug:
            save_debug_outputs(out / "debug", height_map, displacement_map, flat_patterns)

        # 7. 리포트
        self._save_report(out, height_map, displacement_map)
        return out

    def _resolve_geometry(self) -> tuple[float, float, float, float]:
        """보정 파일 또는 직접 지정값에서 d, l, p, sign을 결정합니다."""
        if self.config.calibration_config is not None:
            from .calibration_loader import load_geometry_from_file
            params = load_geometry_from_file(self.config.calibration_config)
            if params is not None:
                return params.d, params.l, params.p, self.config.height_sign
        return self.config.d, self.config.l, self.config.p, self.config.height_sign

    def _save_report(
        self, output_dir: Path,
        height_map: np.ndarray,
        displacement_map: np.ndarray,
    ) -> None:
        """생성 리포트를 JSON으로 저장합니다."""
        h_f = height_map[np.isfinite(height_map)]
        d_f = displacement_map[np.isfinite(displacement_map)]
        report = {
            "generator": "InversePatternGenerator",
            "config": {
                "projector_width": self.config.projector_width,
                "projector_height": self.config.projector_height,
                "gray_bits": self.config.gray_bits,
                "d": self.config.d, "l": self.config.l, "p": self.config.p,
                "height_sign": self.config.height_sign,
                "projector_tilt_degrees": self.config.projector_tilt_degrees,
                "height_source": str(self.config.height_source),
                "calibration_config": (
                    str(self.config.calibration_config)
                    if self.config.calibration_config else None
                ),
                "output_bit_depth": self.config.output_bit_depth,
            },
            "height_map_stats": {
                "shape": list(height_map.shape),
                "min_mm": float(np.min(h_f)) if h_f.size else None,
                "max_mm": float(np.max(h_f)) if h_f.size else None,
                "mean_mm": float(np.mean(h_f)) if h_f.size else None,
            },
            "displacement_stats": {
                "min_px": float(np.min(d_f)) if d_f.size else None,
                "max_px": float(np.max(d_f)) if d_f.size else None,
                "mean_px": float(np.mean(d_f)) if d_f.size else None,
            },
            "pattern_count": 22,
            "pattern_labels": {str(k): v for k, v in PATTERN_LABELS.items()},
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / "inverse_generation_report.json").open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
```

#### 3.7 `cli.py` — 명령줄 인터페이스

```python
"""역 패턴 생성기 CLI."""

from __future__ import annotations
import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PCB 높이 맵에서 역왜곡 구조광 패턴 이미지 22장을 생성합니다."
    )
    parser.add_argument(
        "--height-source", required=True, type=Path,
        help="높이 맵 소스: .npy / .npz / 이미지(.png .jpg 등) / 디코더 출력 폴더",
    )
    parser.add_argument("--output", required=True, type=Path, help="출력 디렉토리")
    parser.add_argument("--projector-width", type=int, default=1280)
    parser.add_argument("--projector-height", type=int, default=800)
    parser.add_argument("--gray-bits", type=int, default=8)
    parser.add_argument("--d", type=float, default=300.0, help="카메라-기준면 거리 (mm)")
    parser.add_argument("--l", type=float, default=120.0, help="기선 거리 (mm)")
    parser.add_argument("--p", type=float, default=5.0, help="줄무늬 주기")
    parser.add_argument("--height-sign", type=float, default=1.0)
    parser.add_argument("--projector-tilt-degrees", type=float, default=30.0)
    parser.add_argument("--calibration-config", type=Path, help="보정 설정 JSON/NPZ 파일")
    parser.add_argument("--max-height-mm", type=float, default=5.0,
                        help="이미지→높이 변환 시 최대 높이 (mm)")
    parser.add_argument("--bit-depth", type=int, choices=(8, 16), default=8)
    parser.add_argument("--save-debug", action="store_true",
                        help="중간 산출물을 debug/ 폴더에 저장")
    return parser


def main() -> None:
    from .generator import InversePatternConfig, InversePatternGenerator

    args = build_parser().parse_args()
    config = InversePatternConfig(
        projector_width=args.projector_width,
        projector_height=args.projector_height,
        gray_bits=args.gray_bits,
        d=args.d, l=args.l, p=args.p,
        height_sign=args.height_sign,
        projector_tilt_degrees=args.projector_tilt_degrees,
        height_source=args.height_source,
        max_height_mm=args.max_height_mm,
        calibration_config=args.calibration_config,
        output_dir=args.output,
        output_bit_depth=args.bit_depth,
        save_debug=args.save_debug,
    )
    output_path = InversePatternGenerator(config).run()
    print(f"\n역 패턴 이미지 생성 완료: {output_path}")
    print(f"  전체 패턴 (디코더 호환): {output_path / 'all'}")
    print(f"  리포트: {output_path / 'inverse_generation_report.json'}")
```

#### 3.8 `gui.py` — tkinter 그래픽 인터페이스

```python
"""역 패턴 생성기 GUI (tkinter)."""

# 구현 요구사항:
#
# 1. 메인 윈도우 레이아웃:
#    ┌──────────────────────────────────────────────┐
#    │  PCB 역 패턴 생성기                          │
#    ├──────────────────────────────────────────────┤
#    │  [높이 소스]  __________ [Browse...]         │
#    │  [보정 설정]  __________ [Browse...] [선택]  │
#    │  d: ___  l: ___  p: ___  sign: ___          │
#    │  프로젝터: W ___ × H ___  Gray bits: ___    │
#    │  최대 높이(mm): ___  비트 깊이: [8/16]      │
#    │  [출력 폴더]  __________ [Browse...]         │
#    │  ☐ 디버그 출력 저장                          │
#    ├──────────────────────────────────────────────┤
#    │  [미리보기 영역: 높이 맵 / displacement 맵] │
#    ├──────────────────────────────────────────────┤
#    │  [Generate]              [진행 표시줄]       │
#    │  상태: 대기 중                               │
#    │  [결과 폴더 열기]                            │
#    └──────────────────────────────────────────────┘
#
# 2. 높이 소스로 이미지 파일을 선택하면 미리보기에 밝기→높이 변환 결과를 표시합니다.
# 3. 보정 설정 JSON을 선택하면 d/l/p 값을 자동으로 읽어와 입력 필드에 채웁니다.
# 4. "Generate" 버튼 클릭 시 별도 스레드에서 생성을 실행하고 진행 표시줄을 갱신합니다.
# 5. 완료 후 "결과 폴더 열기" 버튼으로 탐색기를 엽니다.
# 6. 오류 발생 시 messagebox로 표시합니다.
```

#### 3.9 `__init__.py`

```python
"""PCB 구조광 역 패턴 이미지 생성기."""

from .generator import InversePatternConfig, InversePatternGenerator

__all__ = ["InversePatternConfig", "InversePatternGenerator"]
```

### 4. 스크립트 진입점

#### `scripts/generate_inverse_patterns.py`

```python
"""역 패턴 이미지 생성 CLI 진입점."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inverse_pattern_generator.cli import main

if __name__ == "__main__":
    main()
```

#### `scripts/run_inverse_gui.py`

```python
"""역 패턴 이미지 생성 GUI 진입점."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inverse_pattern_generator.gui import main

if __name__ == "__main__":
    main()
```

### 5. 예시 보정 설정 파일

#### `examples/calibration_config.example.json`

```json
{
  "description": "예시 기하 파라미터. 실제 리그에 맞게 수정하세요.",
  "projector": {
    "tilt_degrees": 30.0,
    "focus_compensation": "Scheimpflug/manual focus",
    "keystone_compensation": "reference phase subtraction"
  },
  "units": {
    "d": "mm",
    "l": "mm",
    "p": "projector pixels or equivalent period"
  },
  "geometry": {
    "d": 300.0,
    "l": 120.0,
    "p": 5.0
  },
  "notes": [
    "삼각측량: h = sign × (Δφ × p × d) / (Δφ × p + 2π × l)",
    "역생성: Δφ = 2π × l × h / (sign × p × d − h × p)",
    "이 파일은 기존 PCB FPP Decoder의 calibration_config.example.json과 호환됩니다."
  ]
}
```

### 6. EXE 빌드 스크립트

#### `build.bat`

```bat
@echo off
setlocal EnableExtensions

chcp 65001 >nul
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "GUI_NAME=PCB_Inverse_Pattern_Generator"
set "CLI_NAME=PCB_Inverse_Pattern_CLI"
set "BUILD_DIR=%TEMP%\PCB_Inverse_Pattern_pyinstaller_%RANDOM%"
set "DIST_DIR=dist"
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

echo.
echo PCB Inverse Pattern Generator EXE build
echo ========================================
echo.

echo [1/4] Preparing Python virtual environment...
if not exist "%PYTHON_EXE%" (
    if exist "%VENV_DIR%" (
        echo Existing .venv is not a Windows venv; recreating...
        rmdir /s /q "%VENV_DIR%"
        if errorlevel 1 goto :venv_error
    )
    if exist "%BUNDLED_PY%" (
        "%BUNDLED_PY%" -m venv "%VENV_DIR%"
    ) else (
        where py >nul 2>nul
        if not errorlevel 1 (
            py -3 -m venv "%VENV_DIR%"
        ) else (
            python -m venv "%VENV_DIR%"
        )
    )
    if errorlevel 1 goto :venv_error
)

echo [2/4] Installing build dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :pip_error
"%PYTHON_EXE%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :pip_error

echo [3/4] Building inverse pattern generator GUI executable...
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

set "PY_BASE_FILE=%BUILD_DIR%\python_base.txt"
"%PYTHON_EXE%" -c "import pathlib, sys; pathlib.Path(r'%PY_BASE_FILE%').write_text(str(pathlib.Path(sys.base_prefix)), encoding='utf-8')"
if errorlevel 1 goto :build_error
set /p "PY_BASE="<"%PY_BASE_FILE%"
if not defined PY_BASE goto :build_error
set "PYI_TK=--hidden-import tkinter --hidden-import tkinter.filedialog --hidden-import tkinter.font --hidden-import tkinter.messagebox --hidden-import tkinter.simpledialog --hidden-import tkinter.ttk --hidden-import tkinter.scrolledtext --add-binary="%PY_BASE%\DLLs\_tkinter.pyd;." --add-binary="%PY_BASE%\DLLs\tcl86t.dll;." --add-binary="%PY_BASE%\DLLs\tk86t.dll;." --add-data="%PY_BASE%\Lib\tkinter;tkinter" --add-data="%PY_BASE%\tcl\tcl8.6;_tcl_data" --add-data="%PY_BASE%\tcl\tk8.6;_tk_data" --add-data="%PY_BASE%\tcl\tcl8.6;lib\tcl8.6" --add-data="%PY_BASE%\tcl\tk8.6;lib\tk8.6""
set "PYI_COMMON=--noconfirm --onedir --distpath %DIST_DIR% --workpath %BUILD_DIR% --specpath %BUILD_DIR% --collect-data matplotlib --hidden-import matplotlib.backends.backend_agg --hidden-import scipy.ndimage --hidden-import PIL.Image --hidden-import PIL.ImageTk --hidden-import cv2 %PYI_TK% --exclude-module=pytest"

"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%GUI_NAME%" --windowed "scripts\run_inverse_gui.py"
if errorlevel 1 goto :build_error

echo [4/4] Building inverse pattern generator CLI executable...
"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%CLI_NAME%" --console "scripts\generate_inverse_patterns.py"
if errorlevel 1 goto :build_error

echo.
echo Build complete.
echo GUI EXE: %DIST_DIR%\%GUI_NAME%\%GUI_NAME%.exe
echo CLI EXE: %DIST_DIR%\%CLI_NAME%\%CLI_NAME%.exe
echo.
exit /b 0

:venv_error
echo.
echo ERROR: Could not create .venv. Install Python 3.10+ and try again.
exit /b 1

:pip_error
echo.
echo ERROR: Dependency installation failed.
exit /b 1

:build_error
echo.
echo ERROR: PyInstaller build failed. See the messages above.
exit /b 1
```

### 7. `README.md`

```markdown
# PCB 구조광 역 패턴 이미지 생성기

PCB 표면의 높이 프로파일에 따라 왜곡이 역보정된 프로젝터 투사용
구조광 패턴 이미지 22장(Gray code 8쌍 + PSP 4장 + White/Black)을
생성합니다.

## 빠른 시작

### CLI 실행

python scripts/generate_inverse_patterns.py \
  --height-source "path/to/pcb_image.png" \
  --output "inverse_patterns/my_pcb" \
  --max-height-mm 3.0 \
  --d 300 --l 120 --p 5

### GUI 실행

python scripts/run_inverse_gui.py

### EXE 빌드

build.bat

## 높이 소스

| 형식 | 설명 |
|------|------|
| `.npy` | 디코더 출력의 height_mm.npy 등 (물리 단위) |
| `.npz` | 'height' 키를 가진 NumPy archive |
| `.png/.jpg` | 그레이스케일 이미지 → 밝기를 높이로 매핑 |
| 디렉토리 | PCB FPP Decoder 출력 폴더 (자동 검색) |

## 출력 구조

output/
├── all/                  ← 디코더 입력 호환 (22장)
├── white_black/          ← White, Black
├── gray_code/            ← Gray0 ~ Gray7
├── gray_code_inv/        ← Gray0_inv ~ Gray7_inv
├── psp_sine/             ← Sine 0°/90°/180°/270°
├── debug/                ← --save-debug 시 생성
└── inverse_generation_report.json
```

---

## 출력 폴더 구조 (최종)

```text
inverse_patterns/<scan_id>/
├── all/                               ← 전체 22장 (디코더 입력 호환 형식)
│   ├── pattern_000.png                ← White (역왜곡 적용)
│   ├── pattern_001.png                ← Black
│   ├── pattern_002.png ~ 009.png      ← Gray0 ~ Gray7
│   ├── pattern_010.png ~ 013.png      ← Sine 0/90/180/270
│   └── pattern_014.png ~ 021.png      ← Gray0_inv ~ Gray7_inv
├── white_black/
│   ├── 00_white.png
│   └── 01_black.png
├── gray_code/
│   ├── 02_gray0.png ~ 09_gray7.png
├── gray_code_inv/
│   ├── 14_gray0_inv.png ~ 21_gray7_inv.png
├── psp_sine/
│   ├── 10_sine_000.png ~ 13_sine_270.png
├── debug/                             ← --save-debug 시
│   ├── height_map.npy
│   ├── height_map_preview.png
│   ├── displacement_map.npy
│   ├── displacement_map_preview.png
│   └── flat_patterns/
│       └── 00_white.png ~ 21_gray7_inv.png
└── inverse_generation_report.json
```

---

## CLI 사용 예

### 디코더 출력 폴더에서 역 패턴 생성 (보정 설정 사용)

```powershell
python scripts\generate_inverse_patterns.py `
  --height-source "C:\path\to\processed\scan_001\deg_0" `
  --output "inverse_patterns\scan_001" `
  --calibration-config "examples\calibration_config.example.json" `
  --save-debug
```

### 실제 PCB 이미지에서 역 패턴 생성 (직접 파라미터 지정)

```powershell
python scripts\generate_inverse_patterns.py `
  --height-source "C:\path\to\pcb_photos\my_pcb.png" `
  --output "inverse_patterns\my_pcb" `
  --max-height-mm 3.0 `
  --d 300 --l 120 --p 5 `
  --projector-width 1280 --projector-height 800 `
  --save-debug
```

### 높이 맵 .npy 파일에서 역 패턴 생성

```powershell
python scripts\generate_inverse_patterns.py `
  --height-source "processed\scan_001\deg_0\height\height_mm.npy" `
  --output "inverse_patterns\scan_001" `
  --d 300 --l 120 --p 5
```

### EXE 빌드 후 사용

```powershell
.\build.bat

# GUI
dist\PCB_Inverse_Pattern_Generator\PCB_Inverse_Pattern_Generator.exe

# CLI
dist\PCB_Inverse_Pattern_CLI\PCB_Inverse_Pattern_CLI.exe `
  --height-source "my_pcb.png" `
  --output "inverse_patterns\my_pcb" `
  --d 300 --l 120 --p 5
```

---

## 테스트

```bash
pytest tests/ -v
```

### 테스트 항목

| 파일 | 내용 |
|------|------|
| `test_pattern_templates.py` | `generate_flat_patterns()`가 정확히 22장을 반환하는지, 각 패턴 shape이 올바른지, White=1.0/Black=0.0인지, Gray+Gray_inv=1.0인지 |
| `test_distortion.py` | 높이 0에서 displacement=0인지, 균일 높이에서 displacement가 균일한지, 역 공식이 정방향과 일치하는지 |
| `test_generator.py` | 전체 파이프라인이 22장을 생성하는지, 출력 폴더 구조가 올바른지, 리포트 JSON이 유효한지 |
| `test_io.py` | `save_pattern_set()`이 5개 폴더를 생성하는지, `all/` 파일 수가 22개인지, 8bit/16bit 저장이 정상인지 |

### 왕복 검증 (Round-trip)

```text
1. 알려진 높이 맵 H로 역 패턴 22장 생성
2. 시뮬레이션: 역 패턴에 같은 높이 맵 H로 정방향 왜곡 적용
   (카메라에서 보이는 이미지 모사)
3. 기존 PCB FPP Decoder로 시뮬레이션 이미지 디코딩
4. 복원된 높이가 거의 0에 가까운지 확인 (역보정 성공 = 평면 결과)
```

---

## 수학적 배경

### 정방향 (촬영 → 높이)

```text
프로젝터 패턴(평면) → PCB 표면 투사 → 카메라 촬영
                                        ↓
                             Gray code + PSP 디코딩
                                        ↓
                             절대 위상 φ_object
                                        ↓
                             Δφ = φ_object - φ_reference
                                        ↓
                             h = sign × (Δφ × p × d) / (Δφ × p + 2π × l)
```

### 역방향 (높이 → 역 패턴)

```text
높이 맵 h (기지)
     ↓
Δφ = 2π × l × h / (sign × p × d − h × p)     ← 삼각측량 역
     ↓
Δx = −Δφ × p / (2π)                            ← 프로젝터 픽셀 이동량 (부호 반전)
     ↓
이상적 패턴에 cv2.remap:  out(y,x) = pattern(y, x + Δx(y,x))
     ↓
프로젝터 투사용 역왜곡 패턴 22장
```

### 역 공식 유도

```text
원래:  h = sign × (Δφ × p × d) / (Δφ × p + 2π × l)

Δφ에 대해 풀기:
  h × (Δφ × p + 2π × l) = sign × Δφ × p × d
  h × Δφ × p + h × 2π × l = sign × Δφ × p × d
  Δφ × p × (sign × d − h) = h × 2π × l
  Δφ = (2π × l × h) / (p × (sign × d − h))
     = (2π × l × h) / (sign × p × d − h × p)

프로젝터 이동량:
  1 줄무늬 주기 = p 프로젝터 px = 2π 위상
  Δx = Δφ × p / (2π)
  역보정:  Δx_inverse = −Δx
```

---

## 주의사항

1. **독립 프로젝트**: 이 레포지토리는 `pcb_fpp_decoder`를 import하지 않습니다. 필요한 수학 공식과 보정 로딩은 자체 구현합니다.
2. **보정 호환**: `examples/calibration_config.example.json`은 기존 디코더와 동일한 형식입니다. 같은 파일을 양쪽에서 사용할 수 있습니다.
3. **PCB 이미지 입력**: 밝기→높이 매핑은 근사적입니다. 정확한 결과를 원하면 디코더로 먼저 높이 맵을 추출하세요.
4. **프로젝터 기울기**: 30도 기울기의 2D 기하 효과는 현재 1D x 방향만 보정합니다. 필요시 y 방향 displacement도 확장 가능합니다.
5. **White/Black**: 균일 값(1.0/0.0)이므로 왜곡 후에도 값이 변하지 않지만, 일관성을 위해 같은 파이프라인을 통과시킵니다.
6. **비트 깊이**: PRO4500은 8비트 입력이 기본입니다. 16비트는 특수 용도에만 사용하세요.
