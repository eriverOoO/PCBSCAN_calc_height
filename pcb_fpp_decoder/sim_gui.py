from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
from pathlib import Path

try:
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
        StringVar,
        Tk,
        filedialog,
        messagebox,
        scrolledtext,
    )

    TK_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    TK_IMPORT_ERROR = exc

from .sim_cli import main as cli_main
from .simulator import PcbFppSimulator, SyntheticPcbConfig


_DONE_TOKEN = "__PCB_FPP_SIM_DONE__"


class SimulatorGui:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("PCB FPP Simulator")
        self.root.minsize(720, 620)
        self.output_var = StringVar(value=str(Path.cwd() / "simulations" / "virtual_pcb"))
        self.width_var = StringVar(value="320")
        self.height_var = StringVar(value="200")
        self.stripe_width_var = StringVar(value="5.0")
        self.height_scale_var = StringVar(value="1.0")
        self.noise_var = StringVar(value="0.0")
        self.blur_var = StringVar(value="0.0")
        self.seed_var = StringVar(value="7")
        self.median_filter_var = StringVar(value="0")
        self.max_points_var = StringVar(value="300000")
        self.inverted_gray_var = IntVar(value=1)
        self.defects_var = IntVar(value=0)
        self.boundary_var = IntVar(value=0)
        self.detrend_var = IntVar(value=0)
        self.messages: queue.Queue[str] = queue.Queue()
        self._build()
        self.root.after(100, self._poll_messages)

    def _build(self) -> None:
        outer = Frame(self.root, padx=10, pady=10)
        outer.pack(fill=BOTH, expand=True)

        folders = LabelFrame(outer, text="Output", padx=8, pady=6)
        folders.pack(fill="x", pady=(0, 8))
        self._folder_row(folders, "Output root", self.output_var, self._choose_output)

        scene = LabelFrame(outer, text="Synthetic Scene", padx=8, pady=6)
        scene.pack(fill="x", pady=(0, 8))
        self._entry_row(scene, "Width", self.width_var)
        self._entry_row(scene, "Height", self.height_var)
        self._entry_row(scene, "Stripe width px", self.stripe_width_var)
        self._entry_row(scene, "Height scale", self.height_scale_var)
        self._entry_row(scene, "Noise sigma", self.noise_var)
        self._entry_row(scene, "Blur sigma", self.blur_var)
        self._entry_row(scene, "Random seed", self.seed_var)

        decode = LabelFrame(outer, text="Decoder Settings", padx=8, pady=6)
        decode.pack(fill="x", pady=(0, 8))
        self._entry_row(decode, "Median filter", self.median_filter_var)
        self._entry_row(decode, "Max 3D points", self.max_points_var)

        options = Frame(decode)
        options.pack(fill="x", pady=4)
        Checkbutton(options, text="Inverted Gray", variable=self.inverted_gray_var).pack(
            side=LEFT
        )
        Checkbutton(options, text="Defects", variable=self.defects_var).pack(
            side=LEFT,
            padx=12,
        )
        Checkbutton(options, text="Boundary correction", variable=self.boundary_var).pack(
            side=LEFT,
            padx=12,
        )
        Checkbutton(options, text="Detrend", variable=self.detrend_var).pack(
            side=LEFT,
            padx=12,
        )

        actions = Frame(outer)
        actions.pack(fill="x", pady=(0, 8))
        self.run_button = Button(actions, text="Run simulation", command=self._run)
        self.run_button.pack(side=LEFT, fill="x", expand=True)
        Button(actions, text="Open output", command=self._open_output).pack(
            side=RIGHT,
            padx=(8, 0),
        )

        self.log = scrolledtext.ScrolledText(outer, height=12)
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
        Entry(row, textvariable=var, width=18).pack(side=LEFT)

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose simulation output root")
        if folder:
            self.output_var.set(folder)

    def _run(self) -> None:
        try:
            output_text = self.output_var.get().strip()
            if not output_text:
                raise ValueError("Output root is required.")
            output_root = Path(output_text)
            config = self._config_from_fields()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.run_button.config(state="disabled")
        thread = threading.Thread(
            target=self._worker,
            args=(output_root, config),
            daemon=True,
        )
        thread.start()

    def _config_from_fields(self) -> SyntheticPcbConfig:
        return SyntheticPcbConfig(
            width=int(self.width_var.get()),
            height=int(self.height_var.get()),
            stripe_width_px=float(self.stripe_width_var.get()),
            height_scale=float(self.height_scale_var.get()),
            noise_sigma=float(self.noise_var.get()),
            blur_sigma=float(self.blur_var.get()),
            random_seed=int(self.seed_var.get()),
            include_inverted_gray=bool(self.inverted_gray_var.get()),
            add_defects=bool(self.defects_var.get()),
            apply_half_period_correction=bool(self.boundary_var.get()),
            detrend=bool(self.detrend_var.get()),
            median_filter=int(self.median_filter_var.get()),
            max_point_cloud_points=int(self.max_points_var.get()),
        )

    def _worker(self, output_root: Path, config: SyntheticPcbConfig) -> None:
        self.messages.put(f"Generating synthetic scan in {output_root}\n")
        self.messages.put(
            f"Scene: {config.width}x{config.height}, "
            f"stripe={config.stripe_width_px}, noise={config.noise_sigma}\n"
        )
        try:
            result = PcbFppSimulator(config).run(output_root)
            height = result.report["metrics"]["height"]
            stripe = result.report["metrics"]["stripe_order"]
            self.messages.put(
                "Done.\n"
                f"Output: {result.output_root}\n"
                f"Truth maps: {result.truth_dir}\n"
                f"Decoded output: {result.processed_object_dir}\n"
                f"Report: {result.output_root / 'simulation_report.json'}\n"
                f"Height RMSE: {height['rmse']}\n"
                f"Height MAE: {height['mae']}\n"
                f"Stripe exact ratio: {stripe['exact_ratio']}\n"
                f"Error map: {result.output_root / 'accuracy' / 'height_error.png'}\n"
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
            messagebox.showinfo("Open output", "Output root is empty.")
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
    if TK_IMPORT_ERROR is not None:
        default_output = Path.cwd() / "simulations" / "virtual_pcb"
        args = sys.argv[1:] or ["--output", str(default_output)]
        print(
            "Tk GUI is not available in this Python runtime; "
            "running simulator CLI mode instead."
        )
        print(f"Tk import error: {TK_IMPORT_ERROR}")
        return cli_main(args)

    SimulatorGui().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
