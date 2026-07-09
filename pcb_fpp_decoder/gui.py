from __future__ import annotations

import queue
import re
import threading
import os
from dataclasses import dataclass
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    Button,
    Checkbutton,
    Entry,
    Frame,
    IntVar,
    Label,
    LabelFrame,
    OptionMenu,
    StringVar,
    Tk,
    filedialog,
    messagebox,
    scrolledtext,
)

from .decoder import DecodeConfig, PcbFppDecoder
from .fusion_registration import (
    FUSION_REGISTRATION_CHOICES,
    estimate_and_save_fusion_transform,
)
from .io import COLOR_INPUT_MODES, parse_crosstalk_matrix


_DONE_TOKEN = "__PCB_FPP_DECODE_DONE__"

_OPTION_LABELS = {
    "relative": "상대 높이",
    "reference": "기준 위상",
    "triangulation": "삼각측량",
    "inverse-linear": "역선형",
    "modulation-weighted": "변조 가중",
    "average": "평균",
    "rotation-180": "180도 회전",
    "aruco": "ArUco",
    "phase-correlation": "위상 상관",
    "homography": "호모그래피",
    "affine": "아핀",
    "smartphone_uv_blue": "스마트폰 UV(파랑)",
    "blue": "파랑",
    "green": "초록",
    "red": "빨강",
    "luminance": "밝기",
    "max_rgb": "RGB 최대값",
    "auto": "자동",
    "normal": "일반",
    "inverted_pair": "반전 쌍",
    "dynamic_raw": "동적(raw)",
    "normalized_0p5": "정규화 0.5",
    "default": "기본",
    "negated": "부호 반전",
    "swapped": "축 교체",
    "reverse": "역방향",
    "1": "+",
    "-1": "-",
}

_EXACT_ERROR_MESSAGES = {
    "Input scan folder is required.": "입력 스캔 폴더를 선택해 주세요.",
    "Output folder is required.": "출력 폴더를 선택해 주세요.",
    "Reference scan folder or reference phase file is required for non-relative height modes.": (
        "상대 높이가 아닌 모드에서는 기준 스캔 폴더 또는 기준 위상 파일이 필요합니다."
    ),
    "Calibration config is required for triangulation or inverse-linear height modes.": (
        "삼각측량 또는 역선형 높이 모드에서는 보정 설정 파일이 필요합니다."
    ),
    "At least one ArUco marker ID is required.": "ArUco 마커 ID를 하나 이상 입력해 주세요.",
    "Fusion center must be blank or two numbers: x,y": (
        "합성 중심은 비워 두거나 x,y 형식의 숫자 두 개로 입력해 주세요."
    ),
    "Fusion transform file cannot be combined with automatic fusion registration.": (
        "합성 변환 파일은 자동 합성 정합과 함께 사용할 수 없습니다."
    ),
    "color crosstalk matrix must contain 9 values, or 3 rows separated by ';'": (
        "크로스토크 행렬은 값 9개를 입력하거나 세미콜론(;)으로 구분한 3개 행으로 입력해 주세요."
    ),
    "each color crosstalk matrix row must contain 3 values": (
        "크로스토크 행렬의 각 행에는 값 3개가 필요합니다."
    ),
    "color crosstalk matrix must have 3 rows": "크로스토크 행렬은 3개 행이어야 합니다.",
    "color crosstalk matrix values must be numeric": (
        "크로스토크 행렬에는 숫자만 입력해 주세요."
    ),
    "color crosstalk matrix must be 3x3": "크로스토크 행렬은 3x3 형식이어야 합니다.",
    "color crosstalk matrix must contain finite values": (
        "크로스토크 행렬에는 유한한 숫자만 입력해 주세요."
    ),
    "color crosstalk matrix must be invertible": (
        "크로스토크 행렬의 역행렬을 계산할 수 없습니다. 값을 확인해 주세요."
    ),
    "gray_threshold_mode must be dynamic_raw or normalized_0p5": (
        "Gray 임계값 모드는 dynamic_raw 또는 normalized_0p5여야 합니다."
    ),
    "gray_decode_mode must be auto, normal, or inverted_pair": (
        "Gray 디코딩 모드는 auto, normal, inverted_pair 중 하나여야 합니다."
    ),
    "sine_source must be corrected or raw": "사인 입력 소스는 corrected 또는 raw여야 합니다.",
    "phase_direction must be normal or reverse": "위상 방향은 normal 또는 reverse여야 합니다.",
    "triangulation mode requires --calibration-config": (
        "삼각측량 모드에는 보정 설정 파일이 필요합니다."
    ),
    "inverse-linear mode requires --calibration-config": (
        "역선형 모드에는 보정 설정 파일이 필요합니다."
    ),
    "height_mode must be relative, reference, triangulation, or inverse-linear": (
        "높이 모드는 relative, reference, triangulation, inverse-linear 중 하나여야 합니다."
    ),
    "fusion_mode must be average or modulation-weighted": (
        "합성 모드는 average 또는 modulation-weighted여야 합니다."
    ),
    "phase correlation failed to produce a finite transform": (
        "위상 상관 정합에서 유효한 변환을 계산하지 못했습니다."
    ),
    "phase-correlation image has no finite pixels": (
        "위상 상관 이미지에 사용할 수 있는 픽셀이 없습니다."
    ),
    "phase-correlation image has no usable contrast; choose a textured frame": (
        "위상 상관 이미지의 대비가 부족합니다. 무늬가 있는 프레임을 선택해 주세요."
    ),
    "Could not estimate homography from detected markers": (
        "감지된 마커로 호모그래피 변환을 계산하지 못했습니다."
    ),
    "Could not estimate affine transform from detected markers": (
        "감지된 마커로 아핀 변환을 계산하지 못했습니다."
    ),
    "OpenCV is required for ArUco alignment": "ArUco 정합에는 OpenCV가 필요합니다.",
    "This OpenCV build does not include cv2.aruco": (
        "현재 OpenCV 빌드에는 cv2.aruco 모듈이 포함되어 있지 않습니다."
    ),
    "OpenCV is required for phase-correlation alignment": (
        "위상 상관 정합에는 OpenCV가 필요합니다."
    ),
    "OpenCV is required for custom fusion transforms; install opencv-python": (
        "사용자 지정 합성 변환에는 OpenCV가 필요합니다. opencv-python을 설치해 주세요."
    ),
    "calibration file must be .json or .npz": "보정 파일은 .json 또는 .npz 형식이어야 합니다.",
    "inverse-linear calibration .npz requires u, v, and w arrays": (
        "역선형 보정 .npz 파일에는 u, v, w 배열이 필요합니다."
    ),
}


def _option_label(value: str) -> str:
    return _OPTION_LABELS.get(value, value)


def _parse_float(label: str, text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}에는 숫자를 입력해 주세요.") from exc


def _parse_int(label: str, text: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}에는 정수를 입력해 주세요.") from exc


def _parse_crosstalk_matrix(text: str):
    try:
        return parse_crosstalk_matrix(text)
    except ValueError as exc:
        raise ValueError(_format_exception_for_user(exc)) from exc


def _format_exception_for_user(exc: BaseException) -> str:
    message = str(exc).strip()
    if re.search(r"[가-힣]", message):
        return message
    translated = _translate_error_message(message)
    if translated is not None:
        return translated
    if isinstance(exc, FileNotFoundError):
        return "파일 또는 폴더를 찾을 수 없습니다. 경로를 확인해 주세요."
    if isinstance(exc, NotADirectoryError):
        return "폴더 경로가 아닙니다. 입력 경로를 확인해 주세요."
    if isinstance(exc, PermissionError):
        return "권한이 없어 작업할 수 없습니다. 폴더 권한을 확인해 주세요."
    if isinstance(exc, ValueError):
        return "입력값을 처리할 수 없습니다. 설정값을 확인해 주세요."
    return f"처리 중 오류가 발생했습니다. 입력 파일과 설정값을 확인해 주세요. ({type(exc).__name__})"


def _translate_error_message(message: str) -> str | None:
    text = str(message).strip()
    if not text:
        return "알 수 없는 오류가 발생했습니다."

    exact = _EXACT_ERROR_MESSAGES.get(text)
    if exact is not None:
        return exact

    match = re.fullmatch(r"input folder does not exist: (.+)", text)
    if match:
        return f"입력 폴더를 찾을 수 없습니다: {match.group(1)}"

    match = re.fullmatch(r"input path is not a folder: (.+)", text)
    if match:
        return f"입력 경로가 폴더가 아닙니다: {match.group(1)}"

    match = re.fullmatch(
        r"missing required pattern image\(s\): (.+)\. Available pattern ids: (.+)\. "
        r"Expected required ids from scan_log\.json or filenames such as pattern_000\.png\.",
        text,
    )
    if match:
        return (
            "필수 패턴 이미지가 누락되었습니다. "
            f"누락 ID: {match.group(1)}, 현재 찾은 ID: {match.group(2)}. "
            "scan_log.json 또는 pattern_000.png 형식의 파일명을 확인해 주세요."
        )

    match = re.fullmatch(r"failed to read image (.+): (.+)", text)
    if match:
        reason = _translate_error_message(match.group(2)) or "이미지를 읽을 수 없습니다."
        return f"이미지를 읽지 못했습니다: {match.group(1)}\n원인: {reason}"

    match = re.fullmatch(r"cv2 could not decode image: (.+)", text)
    if match:
        return f"OpenCV가 이미지를 디코딩하지 못했습니다: {match.group(1)}"

    match = re.fullmatch(r"expected at least 3 color channels: (.+)", text)
    if match:
        return f"색상 이미지에는 최소 3개 채널이 필요합니다: {match.group(1)}"

    match = re.fullmatch(r"unsupported image shape (.+): (.+)", text)
    if match:
        return f"지원하지 않는 이미지 형태입니다: {match.group(1)} ({match.group(2)})"

    match = re.fullmatch(r"pattern (\d+) did not load as grayscale: (.+)", text)
    if match:
        return f"패턴 {match.group(1)} 이미지를 그레이스케일로 읽지 못했습니다: {match.group(2)}"

    match = re.fullmatch(r"image size mismatch for pattern (\d+): (.+) has (.+), expected (.+)", text)
    if match:
        return (
            f"패턴 {match.group(1)} 이미지 크기가 다릅니다: {match.group(2)}의 크기는 "
            f"{match.group(3)}이고, 기대 크기는 {match.group(4)}입니다."
        )

    match = re.fullmatch(r"input color mode must be one of: (.+)", text)
    if match:
        return f"입력 색상 모드는 다음 중 하나여야 합니다: {match.group(1)}"

    match = re.fullmatch(
        r"gray_decode_mode=inverted_pair requires inverted Gray pattern ids 14\.\.(\d+); missing (.+)",
        text,
    )
    if match:
        return (
            "반전 쌍 Gray 디코딩에는 반전 Gray 패턴 이미지가 필요합니다. "
            f"필요 범위: 14..{match.group(1)}, 누락 ID: {match.group(2)}"
        )

    match = re.fullmatch(
        r"(.+) height mode requires --reference-phase or --reference-scan\. "
        r"The flat reference phase is required to cancel projector keystone with "
        r"delta_phi = phi_object - phi_reference\.",
        text,
    )
    if match:
        return (
            f"{_option_label(match.group(1))} 높이 모드에는 기준 위상 파일 또는 기준 스캔 폴더가 "
            "필요합니다. 평면 기준 위상으로 프로젝터 키스톤을 보정합니다."
        )

    match = re.fullmatch(r"reference phase shape (.+) does not match object phase (.+)", text)
    if match:
        return (
            f"기준 위상 크기 {match.group(1)}이 대상 위상 크기 {match.group(2)}와 다릅니다."
        )

    match = re.fullmatch(r"reference phase file does not exist: (.+)", text)
    if match:
        return f"기준 위상 파일을 찾을 수 없습니다: {match.group(1)}"

    match = re.fullmatch(r"fusion transform file does not exist: (.+)", text)
    if match:
        return f"합성 변환 파일을 찾을 수 없습니다: {match.group(1)}"

    match = re.fullmatch(r"unsupported transform kind: (.+)", text)
    if match:
        return f"지원하지 않는 변환 종류입니다: {match.group(1)}"

    match = re.fullmatch(r"fusion registration must be one of (.+)", text)
    if match:
        return f"합성 정합 방식은 다음 중 하나여야 합니다: {match.group(1)}"

    match = re.fullmatch(
        r"phase-correlation alignment requires equal image shapes; "
        r"use ArUco/homography alignment for resized or perspective-shifted scans",
        text,
    )
    if match:
        return (
            "위상 상관 정합에는 두 이미지 크기가 같아야 합니다. 크기가 다르거나 원근 차이가 있으면 "
            "ArUco/호모그래피 정합을 사용해 주세요."
        )

    match = re.fullmatch(
        r"phase-correlation response ([\d.+-eE]+) is below --min-response ([\d.+-eE]+)",
        text,
    )
    if match:
        return (
            f"위상 상관 응답값 {match.group(1)}이 최소 기준 {match.group(2)}보다 낮습니다."
        )

    match = re.fullmatch(r"Could not read phase-correlation image: (.+)", text)
    if match:
        return f"위상 상관 이미지를 읽지 못했습니다: {match.group(1)}"

    match = re.fullmatch(r"Could not read marker detection image: (.+)", text)
    if match:
        return f"마커 감지 이미지를 읽지 못했습니다: {match.group(1)}"

    match = re.fullmatch(r"Unknown ArUco dictionary: (.+)", text)
    if match:
        return f"알 수 없는 ArUco 사전입니다: {match.group(1)}"

    match = re.fullmatch(
        r"Requested ArUco markers were not detected\. missing in 0-degree=(.+), "
        r"missing in rotated=(.+)",
        text,
    )
    if match:
        return (
            "요청한 ArUco 마커를 감지하지 못했습니다. "
            f"0도 스캔 누락: {match.group(1)}, 회전 스캔 누락: {match.group(2)}"
        )

    match = re.fullmatch(r"calibration file does not exist: (.+)", text)
    if match:
        return f"보정 파일을 찾을 수 없습니다: {match.group(1)}"

    match = re.fullmatch(r"calibration parameter '(.+)' shape (.+) cannot broadcast (.+)", text)
    if match:
        return (
            f"보정 파라미터 '{match.group(1)}'의 크기 {match.group(2)}를 "
            f"{match.group(3)}에 맞출 수 없습니다."
        )

    return None


def _format_estimated_transform_summary(estimated_transform) -> str:
    registration = _option_label(estimated_transform.registration)
    transform_kind = _option_label(estimated_transform.transform_kind)
    return f"{registration} 방식으로 {transform_kind} 변환을 추정했습니다."


@dataclass(frozen=True)
class FusionRegistrationSettings:
    mode: str
    aruco_ids: tuple[int, ...]
    aruco_dictionary: str
    aruco_method: str
    image_name: str


class DecoderGui:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("PCB FPP 디코더")
        self.root.minsize(760, 680)
        self._option_display_vars: list[StringVar] = []
        self.input_var = StringVar()
        self.input_180_var = StringVar()
        self.output_var = StringVar()
        self.min_signal_var = StringVar(value="20")
        self.saturation_var = StringVar(value="250")
        self.dark_var = StringVar(value="5")
        self.modulation_var = StringVar(value="0.05")
        self.input_color_mode_var = StringVar(value="smartphone_uv_blue")
        self.crosstalk_matrix_var = StringVar()
        self.median_filter_var = StringVar(value="3")
        self.gray_decode_var = StringVar(value="auto")
        self.gray_threshold_var = StringVar(value="dynamic_raw")
        self.gray_pair_contrast_var = StringVar(value="0.05")
        self.phase_convention_var = StringVar(value="default")
        self.phase_direction_var = StringVar(value="normal")
        self.height_mode_var = StringVar(value="relative")
        self.reference_scan_var = StringVar()
        self.reference_phase_var = StringVar()
        self.calibration_config_var = StringVar()
        self.height_sign_var = StringVar(value="1")
        self.fusion_mode_var = StringVar(value="modulation-weighted")
        self.fusion_registration_var = StringVar(value="rotation-180")
        self.fusion_center_var = StringVar()
        self.fusion_transform_var = StringVar()
        self.aruco_ids_var = StringVar(value="0,1")
        self.aruco_dictionary_var = StringVar(value="DICT_4X4_50")
        self.aruco_method_var = StringVar(value="homography")
        self.registration_image_var = StringVar(value="pattern_000.png")
        self.analysis_roi_var = StringVar(value="none")
        self.analysis_aruco_ids_var = StringVar(value="0,1,2,3")
        self.analysis_workspace_size_var = StringVar()
        self.pcb_size_var = StringVar()
        self.pcb_margin_var = StringVar(value="0")
        self.max_points_var = StringVar(value="300000")
        self.detrend_var = IntVar(value=1)
        self.correction_var = IntVar(value=1)
        self.messages: queue.Queue[str] = queue.Queue()
        self._build()
        self.root.after(100, self._poll_messages)

    def _build(self) -> None:
        outer = Frame(self.root, padx=10, pady=10)
        outer.pack(fill=BOTH, expand=True)

        folders = LabelFrame(outer, text="입력 / 출력", padx=8, pady=6)
        folders.pack(fill="x", pady=(0, 8))
        self._folder_row(folders, "입력 스캔 폴더", self.input_var, self._choose_input)
        self._folder_row(
            folders,
            "180도 스캔 폴더",
            self.input_180_var,
            self._choose_input_180,
        )
        self._folder_row(folders, "출력 폴더", self.output_var, self._choose_output)

        height = LabelFrame(outer, text="3D / 높이", padx=8, pady=6)
        height.pack(fill="x", pady=(0, 8))
        self._option_row(
            height,
            "높이 모드",
            self.height_mode_var,
            ("relative", "reference", "triangulation", "inverse-linear"),
        )
        self._folder_row(
            height,
            "기준 스캔",
            self.reference_scan_var,
            self._choose_reference_scan,
        )
        self._file_row(
            height,
            "기준 위상",
            self.reference_phase_var,
            self._choose_reference_phase,
        )
        self._file_row(
            height,
            "보정 설정",
            self.calibration_config_var,
            self._choose_calibration_config,
        )
        self._option_row(height, "높이 부호", self.height_sign_var, ("1", "-1"))
        self._option_row(
            height,
            "합성 모드",
            self.fusion_mode_var,
            ("modulation-weighted", "average"),
        )
        self._option_row(
            height,
            "합성 정합",
            self.fusion_registration_var,
            FUSION_REGISTRATION_CHOICES,
        )
        self._entry_row(height, "합성 중심 x,y", self.fusion_center_var)
        self._file_row(
            height,
            "합성 변환",
            self.fusion_transform_var,
            self._choose_fusion_transform,
        )
        self._entry_row(height, "ArUco ID", self.aruco_ids_var)
        self._option_row(height, "Analysis ROI", self.analysis_roi_var, ("none", "aruco"))
        self._entry_row(height, "ROI ArUco IDs", self.analysis_aruco_ids_var)
        self._entry_row(height, "Workspace W,H mm", self.analysis_workspace_size_var)
        self._entry_row(height, "PCB W,H mm", self.pcb_size_var)
        self._entry_row(height, "PCB margin mm", self.pcb_margin_var)
        self._option_row(
            height,
            "ArUco 사전",
            self.aruco_dictionary_var,
            ("DICT_4X4_50", "DICT_4X4_100", "DICT_5X5_50", "DICT_6X6_50"),
        )
        self._option_row(
            height,
            "ArUco 방식",
            self.aruco_method_var,
            ("homography", "affine"),
        )
        self._entry_row(height, "정합 이미지", self.registration_image_var)
        self._entry_row(height, "최대 3D 점 수", self.max_points_var)

        decode = LabelFrame(outer, text="디코딩 설정", padx=8, pady=6)
        decode.pack(fill="x", pady=(0, 8))
        self._option_row(
            decode,
            "입력 색상",
            self.input_color_mode_var,
            COLOR_INPUT_MODES,
        )
        self._entry_row(decode, "크로스토크 행렬", self.crosstalk_matrix_var)
        self._entry_row(decode, "최소 신호", self.min_signal_var)
        self._entry_row(decode, "포화 임계값", self.saturation_var)
        self._entry_row(decode, "암부 임계값", self.dark_var)
        self._entry_row(decode, "변조 임계값", self.modulation_var)
        self._entry_row(decode, "중앙값 필터", self.median_filter_var)
        self._option_row(
            decode,
            "Gray 디코딩",
            self.gray_decode_var,
            ("auto", "normal", "inverted_pair"),
        )
        self._option_row(
            decode,
            "Gray 임계값",
            self.gray_threshold_var,
            ("dynamic_raw", "normalized_0p5"),
        )
        self._entry_row(decode, "Gray 쌍 대비", self.gray_pair_contrast_var)
        self._option_row(
            decode,
            "위상 규칙",
            self.phase_convention_var,
            ("default", "negated", "swapped"),
        )
        self._option_row(
            decode,
            "위상 방향",
            self.phase_direction_var,
            ("normal", "reverse"),
        )

        options = Frame(decode)
        options.pack(fill="x", pady=4)
        Checkbutton(options, text="평면 추세 제거", variable=self.detrend_var).pack(side=LEFT)
        Checkbutton(
            options,
            text="경계 보정",
            variable=self.correction_var,
        ).pack(side=LEFT, padx=12)

        actions = Frame(outer)
        actions.pack(fill="x", pady=(0, 8))
        self.run_button = Button(actions, text="디코딩 실행", command=self._run_decode)
        self.run_button.pack(side=LEFT, fill="x", expand=True)
        Button(actions, text="출력 폴더 열기", command=self._open_output).pack(
            side=RIGHT, padx=(8, 0)
        )

        self.log = scrolledtext.ScrolledText(outer, height=10)
        self.log.pack(fill=BOTH, expand=True)

    def _folder_row(self, parent: Frame, label: str, var: StringVar, command) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=4)
        Label(row, text=label, width=18, anchor="w").pack(side=LEFT)
        Entry(row, textvariable=var).pack(side=LEFT, fill="x", expand=True)
        Button(row, text="찾아보기", command=command).pack(side=RIGHT, padx=(6, 0))

    def _entry_row(self, parent: Frame, label: str, var: StringVar) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=4)
        Label(row, text=label, width=18, anchor="w").pack(side=LEFT)
        Entry(row, textvariable=var, width=16).pack(side=LEFT)

    def _file_row(self, parent: Frame, label: str, var: StringVar, command) -> None:
        self._folder_row(parent, label, var, command)

    def _option_row(
        self, parent: Frame, label: str, var: StringVar, values: tuple[str, ...]
    ) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=4)
        Label(row, text=label, width=18, anchor="w").pack(side=LEFT)
        display_values = tuple(_option_label(value) for value in values)
        display_to_value = dict(zip(display_values, values))
        display_var = StringVar(value=_option_label(var.get()))
        self._option_display_vars.append(display_var)

        def select(display_value: str) -> None:
            var.set(display_to_value.get(display_value, display_value))

        OptionMenu(row, display_var, *display_values, command=select).pack(side=LEFT)

    def _choose_input(self) -> None:
        folder = filedialog.askdirectory(title="스캔 폴더 선택")
        if folder:
            self.input_var.set(folder)
            if not self.output_var.get():
                input_path = Path(folder)
                self.output_var.set(str(Path.cwd() / "processed" / input_path.parent.name / input_path.name))

    def _choose_input_180(self) -> None:
        folder = filedialog.askdirectory(title="180도 스캔 폴더 선택")
        if folder:
            self.input_180_var.set(folder)

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="출력 폴더 선택")
        if folder:
            self.output_var.set(folder)

    def _choose_reference_scan(self) -> None:
        folder = filedialog.askdirectory(title="기준 스캔 폴더 선택")
        if folder:
            self.reference_scan_var.set(folder)

    def _choose_reference_phase(self) -> None:
        filename = filedialog.askopenfilename(
            title="기준 absolute_phase.npy 선택",
            filetypes=(("NumPy 위상", "*.npy"), ("모든 파일", "*.*")),
        )
        if filename:
            self.reference_phase_var.set(filename)

    def _choose_calibration_config(self) -> None:
        filename = filedialog.askopenfilename(
            title="보정 설정 파일 선택",
            filetypes=(
                ("보정 파일", "*.json *.npz"),
                ("JSON", "*.json"),
                ("NumPy 아카이브", "*.npz"),
                ("모든 파일", "*.*"),
            ),
        )
        if filename:
            self.calibration_config_var.set(filename)

    def _choose_fusion_transform(self) -> None:
        filename = filedialog.askopenfilename(
            title="합성 변환 파일 선택",
            filetypes=(
                ("변환 파일", "*.json *.npy *.npz"),
                ("JSON", "*.json"),
                ("NumPy", "*.npy *.npz"),
                ("모든 파일", "*.*"),
            ),
        )
        if filename:
            self.fusion_transform_var.set(filename)

    def _run_decode(self) -> None:
        try:
            input_text = self.input_var.get().strip()
            output_text = self.output_var.get().strip()
            if not input_text:
                raise ValueError("입력 스캔 폴더를 선택해 주세요.")
            if not output_text:
                raise ValueError("출력 폴더를 선택해 주세요.")

            input_dir = Path(input_text)
            input_180_dir = self._optional_path(self.input_180_var)
            output_dir = Path(output_text)
            config = self._config_from_fields()
            registration = self._registration_from_fields()
        except Exception as exc:
            messagebox.showerror("설정 오류", _format_exception_for_user(exc))
            return

        self.run_button.config(state="disabled")
        thread = threading.Thread(
            target=self._decode_worker,
            args=(input_dir, input_180_dir, output_dir, config, registration),
            daemon=True,
        )
        thread.start()

    def _config_from_fields(self) -> DecodeConfig:
        height_mode = self.height_mode_var.get()
        reference_scan = self._optional_path(self.reference_scan_var)
        reference_phase = self._optional_path(self.reference_phase_var)
        calibration_config = self._optional_path(self.calibration_config_var)
        fusion_transform = self._optional_path(self.fusion_transform_var)
        fusion_center = self._parse_fusion_center()
        workspace_size = self._parse_size_pair(
            "Workspace W,H mm",
            self.analysis_workspace_size_var.get(),
        )
        pcb_size = self._parse_size_pair("PCB W,H mm", self.pcb_size_var.get())
        analysis_roi_mode = self.analysis_roi_var.get()
        if analysis_roi_mode == "none" and (workspace_size is not None or pcb_size is not None):
            analysis_roi_mode = "aruco"
        pcb_margin_mm = _parse_float("PCB margin mm", self.pcb_margin_var.get() or "0")

        if height_mode != "relative" and reference_scan is None and reference_phase is None:
            raise ValueError(
                "상대 높이가 아닌 모드에서는 기준 스캔 폴더 또는 기준 위상 파일이 필요합니다."
            )
        if height_mode in ("triangulation", "inverse-linear") and calibration_config is None:
            raise ValueError(
                "삼각측량 또는 역선형 높이 모드에서는 보정 설정 파일이 필요합니다."
            )

        return DecodeConfig(
            input_color_mode=self.input_color_mode_var.get(),
            color_crosstalk_matrix=_parse_crosstalk_matrix(self.crosstalk_matrix_var.get()),
            min_signal=_parse_float("최소 신호", self.min_signal_var.get()),
            saturation_threshold=_parse_float("포화 임계값", self.saturation_var.get()),
            dark_threshold=_parse_float("암부 임계값", self.dark_var.get()),
            modulation_threshold=_parse_float("변조 임계값", self.modulation_var.get()),
            gray_decode_mode=self.gray_decode_var.get(),
            gray_threshold_mode=self.gray_threshold_var.get(),
            gray_pair_min_contrast=_parse_float("Gray 쌍 대비", self.gray_pair_contrast_var.get()),
            phase_convention=self.phase_convention_var.get(),
            phase_direction=self.phase_direction_var.get(),
            apply_half_period_correction=bool(self.correction_var.get()),
            detrend=bool(self.detrend_var.get()),
            median_filter=_parse_int("중앙값 필터", self.median_filter_var.get()),
            height_mode=height_mode,
            reference_scan=reference_scan,
            reference_phase=reference_phase,
            calibration_config=calibration_config,
            height_sign=_parse_float("높이 부호", self.height_sign_var.get()),
            fusion_mode=self.fusion_mode_var.get(),
            fusion_center=fusion_center,
            fusion_transform=fusion_transform,
            analysis_roi_mode=analysis_roi_mode,
            analysis_aruco_dictionary=self.aruco_dictionary_var.get(),
            analysis_aruco_ids=self._parse_aruco_ids(self.analysis_aruco_ids_var.get()),
            analysis_aruco_image=self.registration_image_var.get().strip() or "pattern_000.png",
            analysis_workspace_width_mm=workspace_size[0] if workspace_size else None,
            analysis_workspace_height_mm=workspace_size[1] if workspace_size else None,
            pcb_width_mm=pcb_size[0] if pcb_size else None,
            pcb_height_mm=pcb_size[1] if pcb_size else None,
            pcb_margin_mm=pcb_margin_mm,
            max_point_cloud_points=_parse_int("최대 3D 점 수", self.max_points_var.get()),
        )

    def _registration_from_fields(self) -> FusionRegistrationSettings:
        mode = self.fusion_registration_var.get()
        marker_ids = self._parse_aruco_ids(self.aruco_ids_var.get()) if mode == "aruco" else (0, 1)
        image_name = self.registration_image_var.get().strip() or "pattern_000.png"
        return FusionRegistrationSettings(
            mode=mode,
            aruco_ids=marker_ids,
            aruco_dictionary=self.aruco_dictionary_var.get(),
            aruco_method=self.aruco_method_var.get(),
            image_name=image_name,
        )

    def _parse_aruco_ids(self, text: str) -> tuple[int, ...]:
        try:
            marker_ids = tuple(int(part.strip()) for part in text.split(",") if part.strip())
        except ValueError as exc:
            raise ValueError("ArUco ID에는 쉼표로 구분한 정수를 입력해 주세요.") from exc
        if not marker_ids:
            raise ValueError("ArUco 마커 ID를 하나 이상 입력해 주세요.")
        return marker_ids

    def _parse_fusion_center(self) -> tuple[float, float] | None:
        text = self.fusion_center_var.get().strip()
        if not text:
            return None
        normalized = text.replace(";", ",").replace(" ", ",")
        parts = [part for part in normalized.split(",") if part]
        if len(parts) != 2:
            raise ValueError("합성 중심은 비워 두거나 x,y 형식의 숫자 두 개로 입력해 주세요.")
        try:
            return float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise ValueError("합성 중심은 x,y 형식의 숫자 두 개로 입력해 주세요.") from exc

    def _parse_size_pair(self, label: str, text: str) -> tuple[float, float] | None:
        text = text.strip()
        if not text:
            return None
        normalized = text.replace(";", ",").replace(" ", ",").lower().replace("x", ",")
        parts = [part for part in normalized.split(",") if part]
        if len(parts) != 2:
            raise ValueError(f"{label} must use W,H format")
        try:
            width = float(parts[0])
            height = float(parts[1])
        except ValueError as exc:
            raise ValueError(f"{label} values must be numbers") from exc
        if width <= 0 or height <= 0:
            raise ValueError(f"{label} values must be positive")
        return width, height

    def _optional_path(self, var: StringVar) -> Path | None:
        text = var.get().strip()
        return Path(text) if text else None

    def _decode_worker(
        self,
        input_dir: Path,
        input_180_dir: Path | None,
        output_dir: Path,
        config: DecodeConfig,
        registration: FusionRegistrationSettings,
    ) -> None:
        self.messages.put(f"디코딩 중: {input_dir}\n")
        if input_180_dir is not None:
            self.messages.put(f"180도 스캔 합성 중: {input_180_dir}\n")
        self.messages.put(f"높이 모드: {_option_label(config.height_mode)}\n")
        if config.height_mode != "relative":
            self.messages.put("기준 위상 차감: 사용\n")
        try:
            if input_180_dir is None:
                result = PcbFppDecoder(config).decode(input_dir, output_dir)
                ratio = result.report["mask_coverage"]["combined_mask_ratio"]
                ratio_label = "통합 유효 비율"
            else:
                if registration.mode != "rotation-180":
                    if config.fusion_transform is not None:
                        raise ValueError(
                            "합성 변환 파일은 자동 합성 정합과 함께 사용할 수 없습니다."
                        )
                    estimated_transform = estimate_and_save_fusion_transform(
                        registration.mode,
                        input_dir,
                        input_180_dir,
                        output_dir,
                        fusion_center=config.fusion_center,
                        aruco_dictionary=registration.aruco_dictionary,
                        aruco_ids=registration.aruco_ids,
                        aruco_image=registration.image_name,
                        aruco_method=registration.aruco_method,
                        phase_correlation_image=registration.image_name,
                    )
                    if estimated_transform is not None:
                        config.fusion_transform = estimated_transform.path
                        self.messages.put(
                            f"{_format_estimated_transform_summary(estimated_transform)}\n"
                            f"합성 변환: {estimated_transform.path}\n"
                        )
                result = PcbFppDecoder(config).decode_fused(input_dir, input_180_dir, output_dir)
                ratio = result.report["fusion"]["coverage"]["fused_valid_ratio"]
                ratio_label = "합성 유효 비율"
            self.messages.put(
                "완료.\n"
                f"출력 폴더: {output_dir}\n"
                f"{ratio_label}: {ratio:.3f}\n"
                f"높이 히트맵: {output_dir / 'height' / 'height_heatmap.png'}\n"
                f"포인트 클라우드: {output_dir / 'point_cloud' / 'point_cloud.ply'}\n"
                f"3D 미리보기: {output_dir / 'point_cloud' / 'point_cloud_preview.png'}\n"
            )
        except Exception as exc:
            self.messages.put(f"오류가 발생했습니다.\n{_format_exception_for_user(exc)}\n")
        finally:
            self.messages.put(_DONE_TOKEN)

    def _poll_messages(self) -> None:
        while True:
            try:
                msg = self.messages.get_nowait()
            except queue.Empty:
                break
            if msg == _DONE_TOKEN:
                self.run_button.config(state="normal")
                continue
            self.log.insert(END, msg)
            self.log.see(END)
        self.root.after(100, self._poll_messages)

    def _open_output(self) -> None:
        output_text = self.output_var.get().strip()
        if not output_text:
            messagebox.showinfo("출력 폴더 열기", "출력 폴더가 비어 있습니다.")
            return
        output_dir = Path(output_text)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(output_dir))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("출력 폴더 열기 실패", _format_exception_for_user(exc))

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    DecoderGui().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
