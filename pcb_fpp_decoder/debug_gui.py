from __future__ import annotations

import os
import queue
import threading
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
    Listbox,
    StringVar,
    Tk,
    filedialog,
    messagebox,
)
from tkinter import ttk

from PIL import Image, ImageTk

from .debug_tools import (
    DebugStep,
    FusionDebugSettings,
    generate_scan_debug,
    generate_single_image_pattern_debug,
)
from .decoder import DecodeConfig
from .io import COLOR_INPUT_MODES, parse_crosstalk_matrix


_DONE_TOKEN = "__PCB_FPP_DEBUG_DONE__"


class DebuggerGui:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("PCB FPP Debugger")
        self.root.minsize(1040, 720)

        self.mode_var = StringVar(value="scan-sequence")
        self.image_var = StringVar()
        self.scan_var = StringVar()
        self.scan_180_var = StringVar()
        self.output_var = StringVar()
        self.reference_scan_var = StringVar()
        self.reference_phase_var = StringVar()
        self.calibration_var = StringVar()
        self.color_mode_var = StringVar(value="smartphone_uv_blue")
        self.background_sigma_var = StringVar(value="25")
        self.min_signal_var = StringVar(value="20")
        self.saturation_var = StringVar(value="250")
        self.dark_var = StringVar(value="5")
        self.modulation_var = StringVar(value="0.05")
        self.median_filter_var = StringVar(value="3")
        self.height_mode_var = StringVar(value="relative")
        self.fusion_mode_var = StringVar(value="modulation-weighted")
        self.registration_rotation_var = IntVar(value=0)
        self.registration_aruco_var = IntVar(value=1)
        self.registration_phase_var = IntVar(value=0)
        self.registration_image_var = StringVar(value="pattern_000.png")
        self.aruco_ids_var = StringVar(value="0,1,2,3")
        self.aruco_dictionary_var = StringVar(value="DICT_4X4_50")
        self.aruco_method_var = StringVar(value="homography")
        self.crosstalk_matrix_var = StringVar()
        self.detrend_var = IntVar(value=1)
        self.boundary_correction_var = IntVar(value=1)

        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.steps: list[DebugStep] = []
        self.current_step_index: int | None = None
        self._preview_image: ImageTk.PhotoImage | None = None
        self._last_preview_path: Path | None = None
        self.run_buttons: list[Button] = []

        self._build()
        self.root.after(100, self._poll_messages)

    def _build(self) -> None:
        outer = Frame(self.root, padx=10, pady=10)
        outer.pack(fill=BOTH, expand=True)

        left = Frame(outer)
        left.pack(side=LEFT, fill="y")

        right = Frame(outer)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        target = LabelFrame(left, text="Target", padx=8, pady=6)
        target.pack(fill="x", pady=(0, 8))
        self._option_row(target, "Mode", self.mode_var, ("scan-sequence", "single-image"))
        self._file_row(target, "Image", self.image_var, self._choose_image)
        self._folder_row(target, "Scan folder", self.scan_var, self._choose_scan)
        self._folder_row(target, "180 folder", self.scan_180_var, self._choose_scan_180)
        self._folder_row(target, "Output", self.output_var, self._choose_output)
        self._action_row(target)

        decode = LabelFrame(left, text="Decode", padx=8, pady=6)
        decode.pack(fill="x", pady=(0, 8))
        self._option_row(decode, "Color mode", self.color_mode_var, COLOR_INPUT_MODES)
        self._entry_row(decode, "Crosstalk 3x3", self.crosstalk_matrix_var)
        self._entry_row(decode, "Background sigma", self.background_sigma_var)
        self._entry_row(decode, "Min signal", self.min_signal_var)
        self._entry_row(decode, "Saturation", self.saturation_var)
        self._entry_row(decode, "Dark", self.dark_var)
        self._entry_row(decode, "Modulation", self.modulation_var)
        self._entry_row(decode, "Median filter", self.median_filter_var)
        checks = Frame(decode)
        checks.pack(fill="x", pady=4)
        Checkbutton(checks, text="Detrend", variable=self.detrend_var).pack(side=LEFT)
        Checkbutton(
            checks,
            text="Boundary fix",
            variable=self.boundary_correction_var,
        ).pack(side=LEFT, padx=(10, 0))

        height = LabelFrame(left, text="Height / Fusion", padx=8, pady=6)
        height.pack(fill="x", pady=(0, 8))
        self._option_row(
            height,
            "Height mode",
            self.height_mode_var,
            ("relative", "reference", "triangulation", "inverse-linear"),
        )
        self._folder_row(height, "Reference scan", self.reference_scan_var, self._choose_reference_scan)
        self._file_row(height, "Reference phase", self.reference_phase_var, self._choose_reference_phase)
        self._file_row(height, "Calibration", self.calibration_var, self._choose_calibration)
        self._option_row(height, "Fusion mode", self.fusion_mode_var, ("modulation-weighted", "average"))
        self._registration_check_row(height)
        self._entry_row(height, "Reg image", self.registration_image_var)
        self._entry_row(height, "ArUco IDs", self.aruco_ids_var)
        self._option_row(
            height,
            "ArUco dict",
            self.aruco_dictionary_var,
            ("DICT_4X4_50", "DICT_4X4_100", "DICT_5X5_50", "DICT_6X6_50"),
        )
        self._option_row(height, "ArUco method", self.aruco_method_var, ("homography", "affine"))

        actions = Frame(left)
        actions.pack(fill="x")
        run_button = Button(actions, text="Run debug", command=self._run_debug)
        run_button.pack(side=LEFT, fill="x", expand=True)
        self.run_buttons.append(run_button)
        Button(actions, text="Open output", command=self._open_output).pack(side=RIGHT, padx=(8, 0))

        step_frame = LabelFrame(right, text="Steps", padx=8, pady=6)
        step_frame.pack(side=LEFT, fill="y")
        self.step_list = Listbox(step_frame, width=34, exportselection=False)
        self.step_list.pack(fill=BOTH, expand=True)
        self.step_list.bind("<<ListboxSelect>>", self._on_step_select)

        preview_frame = LabelFrame(right, text="Preview", padx=8, pady=6)
        preview_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))
        self.preview_label = Label(preview_frame, bg="#111318")
        self.preview_label.pack(fill=BOTH, expand=True)
        self.preview_label.bind("<Configure>", self._on_preview_resize)
        self.status_label = Label(preview_frame, text="", anchor="w", justify=LEFT)
        self.status_label.pack(fill="x", pady=(8, 0))

    def _folder_row(self, parent: Frame, label: str, var: StringVar, command) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=3)
        Label(row, text=label, width=15, anchor="w").pack(side=LEFT)
        Entry(row, textvariable=var, width=28).pack(side=LEFT, fill="x", expand=True)
        Button(row, text="...", command=command, width=3).pack(side=RIGHT, padx=(4, 0))

    def _file_row(self, parent: Frame, label: str, var: StringVar, command) -> None:
        self._folder_row(parent, label, var, command)

    def _entry_row(self, parent: Frame, label: str, var: StringVar) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=3)
        Label(row, text=label, width=15, anchor="w").pack(side=LEFT)
        Entry(row, textvariable=var, width=18).pack(side=LEFT, fill="x", expand=True)

    def _option_row(
        self,
        parent: Frame,
        label: str,
        var: StringVar,
        values: tuple[str, ...],
    ) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=3)
        Label(row, text=label, width=15, anchor="w").pack(side=LEFT)
        combo = ttk.Combobox(row, textvariable=var, values=values, state="readonly", width=24)
        combo.pack(side=LEFT, fill="x", expand=True)

    def _registration_check_row(self, parent: Frame) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=3)
        Label(row, text="Registration", width=15, anchor="w").pack(side=LEFT)
        Checkbutton(row, text="180", variable=self.registration_rotation_var).pack(side=LEFT)
        Checkbutton(row, text="ArUco", variable=self.registration_aruco_var).pack(
            side=LEFT,
            padx=(8, 0),
        )
        Checkbutton(row, text="Phase corr", variable=self.registration_phase_var).pack(
            side=LEFT,
            padx=(8, 0),
        )

    def _action_row(self, parent: Frame) -> None:
        row = Frame(parent)
        row.pack(fill="x", pady=(8, 2))
        run_button = Button(row, text="Run debug", command=self._run_debug)
        run_button.pack(side=LEFT, fill="x", expand=True)
        self.run_buttons.append(run_button)
        Button(row, text="Open output", command=self._open_output).pack(side=RIGHT, padx=(8, 0))

    def _choose_image(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select image",
            filetypes=(
                ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ),
        )
        if filename:
            self.mode_var.set("single-image")
            self.image_var.set(filename)
            self._fill_default_output(Path(filename))

    def _choose_scan(self) -> None:
        folder = filedialog.askdirectory(title="Select scan folder")
        if folder:
            self.mode_var.set("scan-sequence")
            self.scan_var.set(folder)
            self._fill_default_output(Path(folder))

    def _choose_scan_180(self) -> None:
        folder = filedialog.askdirectory(title="Select 180 scan folder")
        if folder:
            self.scan_180_var.set(folder)

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_var.set(folder)

    def _choose_reference_scan(self) -> None:
        folder = filedialog.askdirectory(title="Select reference scan")
        if folder:
            self.reference_scan_var.set(folder)

    def _choose_reference_phase(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select reference absolute_phase.npy",
            filetypes=(("NumPy", "*.npy"), ("All files", "*.*")),
        )
        if filename:
            self.reference_phase_var.set(filename)

    def _choose_calibration(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select calibration",
            filetypes=(
                ("Calibration", "*.json *.npz"),
                ("JSON", "*.json"),
                ("NumPy", "*.npz"),
                ("All files", "*.*"),
            ),
        )
        if filename:
            self.calibration_var.set(filename)

    def _fill_default_output(self, source: Path) -> None:
        if self.output_var.get().strip():
            return
        name = source.stem if source.is_file() else source.name
        self.output_var.set(str(source.parent / f"{name}_debug"))

    def _run_debug(self) -> None:
        try:
            mode = self.mode_var.get()
            output = self._required_path(self.output_var, "Output")
            if mode == "single-image":
                target = self._required_path(self.image_var, "Image")
                args = (mode, target, output, None, None, None)
            else:
                target = self._required_path(self.scan_var, "Scan folder")
                input_180 = self._optional_path(self.scan_180_var)
                config = self._config_from_fields()
                fusion_settings = self._fusion_settings_from_fields()
                args = (mode, target, output, input_180, config, fusion_settings)
        except Exception as exc:
            messagebox.showerror("Debug setup error", str(exc))
            return

        self._set_busy(True)
        self._clear_steps()
        thread = threading.Thread(target=self._worker, args=args, daemon=True)
        thread.start()

    def _worker(
        self,
        mode: str,
        target: Path,
        output: Path,
        input_180: Path | None,
        config: DecodeConfig | None,
        fusion_settings: FusionDebugSettings | None,
    ) -> None:
        try:
            self.messages.put(("status", f"Running: {target}"))
            if mode == "single-image":
                steps = generate_single_image_pattern_debug(
                    target,
                    output,
                    color_mode=self.color_mode_var.get(),
                    background_sigma=self._parse_float(
                        "Background sigma",
                        self.background_sigma_var.get(),
                    ),
                )
            else:
                assert config is not None
                steps = generate_scan_debug(
                    target,
                    output,
                    config,
                    input_180_dir=input_180,
                    fusion_settings=fusion_settings,
                )
            self.messages.put(("steps", steps))
            self.messages.put(("status", f"Done: {output}"))
        except Exception as exc:
            self.messages.put(("error", str(exc)))
        finally:
            self.messages.put((_DONE_TOKEN, None))

    def _config_from_fields(self) -> DecodeConfig:
        return DecodeConfig(
            input_color_mode=self.color_mode_var.get(),
            color_crosstalk_matrix=parse_crosstalk_matrix(self.crosstalk_matrix_var.get()),
            min_signal=self._parse_float("Min signal", self.min_signal_var.get()),
            saturation_threshold=self._parse_float("Saturation", self.saturation_var.get()),
            dark_threshold=self._parse_float("Dark", self.dark_var.get()),
            modulation_threshold=self._parse_float("Modulation", self.modulation_var.get()),
            median_filter=self._parse_int("Median filter", self.median_filter_var.get()),
            height_mode=self.height_mode_var.get(),
            reference_scan=self._optional_path(self.reference_scan_var),
            reference_phase=self._optional_path(self.reference_phase_var),
            calibration_config=self._optional_path(self.calibration_var),
            fusion_mode=self.fusion_mode_var.get(),
            apply_half_period_correction=bool(self.boundary_correction_var.get()),
            detrend=bool(self.detrend_var.get()),
        )

    def _fusion_settings_from_fields(self) -> FusionDebugSettings:
        selected = [
            ("rotation-180", bool(self.registration_rotation_var.get())),
            ("aruco", bool(self.registration_aruco_var.get())),
            ("phase-correlation", bool(self.registration_phase_var.get())),
        ]
        enabled = [mode for mode, is_enabled in selected if is_enabled]
        if not enabled:
            raise ValueError("Select one 180 registration method")
        if len(enabled) > 1:
            raise ValueError("Select only one automatic 180 registration method")
        return FusionDebugSettings(
            registration=enabled[0],
            aruco_ids=self._parse_aruco_ids(self.aruco_ids_var.get()),
            aruco_dictionary=self.aruco_dictionary_var.get(),
            aruco_method=self.aruco_method_var.get(),
            registration_image=self.registration_image_var.get().strip() or "pattern_000.png",
        )

    def _parse_aruco_ids(self, text: str) -> tuple[int, ...]:
        try:
            values = tuple(int(part.strip()) for part in text.split(",") if part.strip())
        except ValueError as exc:
            raise ValueError("ArUco IDs must be comma-separated integers") from exc
        if not values:
            raise ValueError("At least one ArUco ID is required")
        return values

    def _required_path(self, var: StringVar, label: str) -> Path:
        text = var.get().strip()
        if not text:
            raise ValueError(f"{label} is required")
        return Path(text)

    def _optional_path(self, var: StringVar) -> Path | None:
        text = var.get().strip()
        return Path(text) if text else None

    def _parse_float(self, label: str, text: str) -> float:
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number") from exc

    def _parse_int(self, label: str, text: str) -> int:
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer") from exc

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == _DONE_TOKEN:
                self._set_busy(False)
            elif kind == "steps":
                self._load_steps(list(payload))  # type: ignore[arg-type]
            elif kind == "error":
                messagebox.showerror("Debug failed", str(payload))
                self.status_label.config(text=str(payload))
            elif kind == "status":
                self.status_label.config(text=str(payload))
        self.root.after(100, self._poll_messages)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for button in self.run_buttons:
            button.config(state=state)

    def _clear_steps(self) -> None:
        self.steps = []
        self.current_step_index = None
        self._last_preview_path = None
        self.step_list.delete(0, END)
        self.preview_label.config(image="", text="")
        self.status_label.config(text="")

    def _load_steps(self, steps: list[DebugStep]) -> None:
        self._clear_steps()
        self.steps = steps
        for index, step in enumerate(steps, start=1):
            label = f"{index:02d}. {step.title}"
            if step.group:
                label += f" [{step.group}]"
            self.step_list.insert(END, label)
        if steps:
            self.step_list.selection_set(0)
            self._show_step(0)

    def _on_step_select(self, _event=None) -> None:
        selection = self.step_list.curselection()
        if not selection:
            return
        self._show_step(int(selection[0]))

    def _show_step(self, index: int) -> None:
        if index < 0 or index >= len(self.steps):
            return
        self.current_step_index = index
        step = self.steps[index]
        self._last_preview_path = step.path
        self._render_preview(step.path)
        note = f"{step.title} | {step.path}"
        if step.note:
            note += f" | {step.note}"
        self.status_label.config(text=note)

    def _on_preview_resize(self, _event=None) -> None:
        if self._last_preview_path is not None:
            self._render_preview(self._last_preview_path)

    def _render_preview(self, path: Path) -> None:
        if not Path(path).exists():
            self.preview_label.config(text="Missing preview", image="")
            return
        width = max(self.preview_label.winfo_width() - 12, 240)
        height = max(self.preview_label.winfo_height() - 12, 180)
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((width, height), Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image)
        self.preview_label.config(image=self._preview_image, text="")

    def _open_output(self) -> None:
        text = self.output_var.get().strip()
        if not text:
            messagebox.showinfo("Open output", "Output is empty")
            return
        output_dir = Path(text)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(output_dir))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Open output failed", str(exc))

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    DebuggerGui().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
