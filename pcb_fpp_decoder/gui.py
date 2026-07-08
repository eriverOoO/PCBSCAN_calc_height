from __future__ import annotations

import queue
import threading
import traceback
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


_DONE_TOKEN = "__PCB_FPP_DECODE_DONE__"


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
        self.root.title("PCB FPP Decoder")
        self.root.minsize(760, 680)
        self.input_var = StringVar()
        self.input_180_var = StringVar()
        self.output_var = StringVar()
        self.min_signal_var = StringVar(value="20")
        self.saturation_var = StringVar(value="250")
        self.dark_var = StringVar(value="5")
        self.modulation_var = StringVar(value="0.05")
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
        self.max_points_var = StringVar(value="300000")
        self.detrend_var = IntVar(value=1)
        self.correction_var = IntVar(value=1)
        self.messages: queue.Queue[str] = queue.Queue()
        self._build()
        self.root.after(100, self._poll_messages)

    def _build(self) -> None:
        outer = Frame(self.root, padx=10, pady=10)
        outer.pack(fill=BOTH, expand=True)

        folders = LabelFrame(outer, text="Input / Output", padx=8, pady=6)
        folders.pack(fill="x", pady=(0, 8))
        self._folder_row(folders, "Input scan folder", self.input_var, self._choose_input)
        self._folder_row(
            folders,
            "180 scan folder",
            self.input_180_var,
            self._choose_input_180,
        )
        self._folder_row(folders, "Output folder", self.output_var, self._choose_output)

        height = LabelFrame(outer, text="3D / Height", padx=8, pady=6)
        height.pack(fill="x", pady=(0, 8))
        self._option_row(
            height,
            "Height mode",
            self.height_mode_var,
            ("relative", "reference", "triangulation", "inverse-linear"),
        )
        self._folder_row(
            height,
            "Reference scan",
            self.reference_scan_var,
            self._choose_reference_scan,
        )
        self._file_row(
            height,
            "Reference phase",
            self.reference_phase_var,
            self._choose_reference_phase,
        )
        self._file_row(
            height,
            "Calibration config",
            self.calibration_config_var,
            self._choose_calibration_config,
        )
        self._option_row(height, "Height sign", self.height_sign_var, ("1", "-1"))
        self._option_row(
            height,
            "Fusion mode",
            self.fusion_mode_var,
            ("modulation-weighted", "average"),
        )
        self._option_row(
            height,
            "Fusion registration",
            self.fusion_registration_var,
            FUSION_REGISTRATION_CHOICES,
        )
        self._entry_row(height, "Fusion center x,y", self.fusion_center_var)
        self._file_row(
            height,
            "Fusion transform",
            self.fusion_transform_var,
            self._choose_fusion_transform,
        )
        self._entry_row(height, "ArUco IDs", self.aruco_ids_var)
        self._option_row(
            height,
            "ArUco dictionary",
            self.aruco_dictionary_var,
            ("DICT_4X4_50", "DICT_4X4_100", "DICT_5X5_50", "DICT_6X6_50"),
        )
        self._option_row(
            height,
            "ArUco method",
            self.aruco_method_var,
            ("homography", "affine"),
        )
        self._entry_row(height, "Registration image", self.registration_image_var)
        self._entry_row(height, "Max 3D points", self.max_points_var)

        decode = LabelFrame(outer, text="Decode Settings", padx=8, pady=6)
        decode.pack(fill="x", pady=(0, 8))
        self._entry_row(decode, "Min signal", self.min_signal_var)
        self._entry_row(decode, "Saturation threshold", self.saturation_var)
        self._entry_row(decode, "Dark threshold", self.dark_var)
        self._entry_row(decode, "Modulation threshold", self.modulation_var)
        self._entry_row(decode, "Median filter", self.median_filter_var)
        self._option_row(
            decode,
            "Gray decode",
            self.gray_decode_var,
            ("auto", "normal", "inverted_pair"),
        )
        self._option_row(
            decode,
            "Gray threshold",
            self.gray_threshold_var,
            ("dynamic_raw", "normalized_0p5"),
        )
        self._entry_row(decode, "Gray pair contrast", self.gray_pair_contrast_var)
        self._option_row(
            decode,
            "Phase convention",
            self.phase_convention_var,
            ("default", "negated", "swapped"),
        )
        self._option_row(
            decode,
            "Phase direction",
            self.phase_direction_var,
            ("normal", "reverse"),
        )

        options = Frame(decode)
        options.pack(fill="x", pady=4)
        Checkbutton(options, text="Detrend", variable=self.detrend_var).pack(side=LEFT)
        Checkbutton(
            options,
            text="Boundary correction",
            variable=self.correction_var,
        ).pack(side=LEFT, padx=12)

        actions = Frame(outer)
        actions.pack(fill="x", pady=(0, 8))
        self.run_button = Button(actions, text="Run decode", command=self._run_decode)
        self.run_button.pack(side=LEFT, fill="x", expand=True)
        Button(actions, text="Open output", command=self._open_output).pack(
            side=RIGHT, padx=(8, 0)
        )

        self.log = scrolledtext.ScrolledText(outer, height=10)
        self.log.pack(fill=BOTH, expand=True)

    def _folder_row(self, parent: Frame, label: str, var: StringVar, command) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=4)
        Label(row, text=label, width=18, anchor="w").pack(side=LEFT)
        Entry(row, textvariable=var).pack(side=LEFT, fill="x", expand=True)
        Button(row, text="Browse", command=command).pack(side=RIGHT, padx=(6, 0))

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
        OptionMenu(row, var, *values).pack(side=LEFT)

    def _choose_input(self) -> None:
        folder = filedialog.askdirectory(title="Choose scan folder")
        if folder:
            self.input_var.set(folder)
            if not self.output_var.get():
                input_path = Path(folder)
                self.output_var.set(str(Path.cwd() / "processed" / input_path.parent.name / input_path.name))

    def _choose_input_180(self) -> None:
        folder = filedialog.askdirectory(title="Choose 180-degree scan folder")
        if folder:
            self.input_180_var.set(folder)

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_var.set(folder)

    def _choose_reference_scan(self) -> None:
        folder = filedialog.askdirectory(title="Choose reference scan folder")
        if folder:
            self.reference_scan_var.set(folder)

    def _choose_reference_phase(self) -> None:
        filename = filedialog.askopenfilename(
            title="Choose reference absolute_phase.npy",
            filetypes=(("NumPy phase", "*.npy"), ("All files", "*.*")),
        )
        if filename:
            self.reference_phase_var.set(filename)

    def _choose_calibration_config(self) -> None:
        filename = filedialog.askopenfilename(
            title="Choose calibration config",
            filetypes=(
                ("Calibration files", "*.json *.npz"),
                ("JSON", "*.json"),
                ("NumPy archive", "*.npz"),
                ("All files", "*.*"),
            ),
        )
        if filename:
            self.calibration_config_var.set(filename)

    def _choose_fusion_transform(self) -> None:
        filename = filedialog.askopenfilename(
            title="Choose fusion transform",
            filetypes=(
                ("Transform files", "*.json *.npy *.npz"),
                ("JSON", "*.json"),
                ("NumPy", "*.npy *.npz"),
                ("All files", "*.*"),
            ),
        )
        if filename:
            self.fusion_transform_var.set(filename)

    def _run_decode(self) -> None:
        try:
            input_text = self.input_var.get().strip()
            output_text = self.output_var.get().strip()
            if not input_text:
                raise ValueError("Input scan folder is required.")
            if not output_text:
                raise ValueError("Output folder is required.")

            input_dir = Path(input_text)
            input_180_dir = self._optional_path(self.input_180_var)
            output_dir = Path(output_text)
            config = self._config_from_fields()
            registration = self._registration_from_fields()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
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

        if height_mode != "relative" and reference_scan is None and reference_phase is None:
            raise ValueError(
                "Reference scan folder or reference phase file is required for non-relative height modes."
            )
        if height_mode in ("triangulation", "inverse-linear") and calibration_config is None:
            raise ValueError(
                "Calibration config is required for triangulation or inverse-linear height modes."
            )

        return DecodeConfig(
            min_signal=float(self.min_signal_var.get()),
            saturation_threshold=float(self.saturation_var.get()),
            dark_threshold=float(self.dark_var.get()),
            modulation_threshold=float(self.modulation_var.get()),
            gray_decode_mode=self.gray_decode_var.get(),
            gray_threshold_mode=self.gray_threshold_var.get(),
            gray_pair_min_contrast=float(self.gray_pair_contrast_var.get()),
            phase_convention=self.phase_convention_var.get(),
            phase_direction=self.phase_direction_var.get(),
            apply_half_period_correction=bool(self.correction_var.get()),
            detrend=bool(self.detrend_var.get()),
            median_filter=int(self.median_filter_var.get()),
            height_mode=height_mode,
            reference_scan=reference_scan,
            reference_phase=reference_phase,
            calibration_config=calibration_config,
            height_sign=float(self.height_sign_var.get()),
            fusion_mode=self.fusion_mode_var.get(),
            fusion_center=fusion_center,
            fusion_transform=fusion_transform,
            max_point_cloud_points=int(self.max_points_var.get()),
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
        marker_ids = tuple(int(part.strip()) for part in text.split(",") if part.strip())
        if not marker_ids:
            raise ValueError("At least one ArUco marker ID is required.")
        return marker_ids

    def _parse_fusion_center(self) -> tuple[float, float] | None:
        text = self.fusion_center_var.get().strip()
        if not text:
            return None
        normalized = text.replace(";", ",").replace(" ", ",")
        parts = [part for part in normalized.split(",") if part]
        if len(parts) != 2:
            raise ValueError("Fusion center must be blank or two numbers: x,y")
        return float(parts[0]), float(parts[1])

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
        self.messages.put(f"Decoding {input_dir}\n")
        if input_180_dir is not None:
            self.messages.put(f"Fusing 180-degree scan: {input_180_dir}\n")
        self.messages.put(f"Height mode: {config.height_mode}\n")
        if config.height_mode != "relative":
            self.messages.put("Reference phase subtraction: enabled\n")
        try:
            if input_180_dir is None:
                result = PcbFppDecoder(config).decode(input_dir, output_dir)
                ratio = result.report["mask_coverage"]["combined_mask_ratio"]
                ratio_label = "Combined valid ratio"
            else:
                if registration.mode != "rotation-180":
                    if config.fusion_transform is not None:
                        raise ValueError(
                            "Fusion transform file cannot be combined with automatic fusion registration."
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
                            f"{estimated_transform.summary}\n"
                            f"Fusion transform: {estimated_transform.path}\n"
                        )
                result = PcbFppDecoder(config).decode_fused(input_dir, input_180_dir, output_dir)
                ratio = result.report["fusion"]["coverage"]["fused_valid_ratio"]
                ratio_label = "Fused valid ratio"
            self.messages.put(
                "Done.\n"
                f"Output: {output_dir}\n"
                f"{ratio_label}: {ratio:.3f}\n"
                f"Heat map: {output_dir / 'height' / 'height_heatmap.png'}\n"
                f"Point cloud: {output_dir / 'point_cloud' / 'point_cloud.ply'}\n"
                f"3D preview: {output_dir / 'point_cloud' / 'point_cloud_preview.png'}\n"
            )
        except Exception:
            self.messages.put(traceback.format_exc() + "\n")
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
            messagebox.showinfo("Open output", "Output folder is empty.")
            return
        output_dir = Path(output_text)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(output_dir))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Open output failed", str(exc))

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    DecoderGui().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
