from __future__ import annotations

import queue
import threading
import traceback
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
    StringVar,
    Tk,
    filedialog,
    messagebox,
    scrolledtext,
)

from .decoder import DecodeConfig, PcbFppDecoder


class DecoderGui:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("PCB FPP Decoder")
        self.input_var = StringVar()
        self.output_var = StringVar()
        self.min_signal_var = StringVar(value="20")
        self.modulation_var = StringVar(value="0.05")
        self.detrend_var = IntVar(value=1)
        self.correction_var = IntVar(value=1)
        self.messages: queue.Queue[str] = queue.Queue()
        self._build()
        self.root.after(100, self._poll_messages)

    def _build(self) -> None:
        outer = Frame(self.root, padx=10, pady=10)
        outer.pack(fill=BOTH, expand=True)

        self._folder_row(outer, "Input scan folder", self.input_var, self._choose_input)
        self._folder_row(outer, "Output folder", self.output_var, self._choose_output)
        self._entry_row(outer, "Min signal", self.min_signal_var)
        self._entry_row(outer, "Modulation threshold", self.modulation_var)

        options = Frame(outer)
        options.pack(fill="x", pady=4)
        Checkbutton(options, text="Detrend", variable=self.detrend_var).pack(side=LEFT)
        Checkbutton(
            options,
            text="Boundary correction",
            variable=self.correction_var,
        ).pack(side=LEFT, padx=12)

        Button(outer, text="Run decode", command=self._run_decode).pack(fill="x", pady=8)
        self.log = scrolledtext.ScrolledText(outer, height=14)
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

    def _choose_input(self) -> None:
        folder = filedialog.askdirectory(title="Choose scan folder")
        if folder:
            self.input_var.set(folder)
            if not self.output_var.get():
                input_path = Path(folder)
                self.output_var.set(str(Path.cwd() / "processed" / input_path.parent.name / input_path.name))

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_var.set(folder)

    def _run_decode(self) -> None:
        try:
            input_dir = Path(self.input_var.get())
            output_dir = Path(self.output_var.get())
            config = DecodeConfig(
                min_signal=float(self.min_signal_var.get()),
                modulation_threshold=float(self.modulation_var.get()),
                detrend=bool(self.detrend_var.get()),
                apply_half_period_correction=bool(self.correction_var.get()),
            )
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        thread = threading.Thread(
            target=self._decode_worker, args=(input_dir, output_dir, config), daemon=True
        )
        thread.start()

    def _decode_worker(self, input_dir: Path, output_dir: Path, config: DecodeConfig) -> None:
        self.messages.put(f"Decoding {input_dir}\n")
        try:
            result = PcbFppDecoder(config).decode(input_dir, output_dir)
            ratio = result.report["mask_coverage"]["combined_mask_ratio"]
            self.messages.put(f"Done. Output: {output_dir}\nCombined valid ratio: {ratio:.3f}\n")
        except Exception:
            self.messages.put(traceback.format_exc() + "\n")

    def _poll_messages(self) -> None:
        while True:
            try:
                msg = self.messages.get_nowait()
            except queue.Empty:
                break
            self.log.insert(END, msg)
            self.log.see(END)
        self.root.after(100, self._poll_messages)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    DecoderGui().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
