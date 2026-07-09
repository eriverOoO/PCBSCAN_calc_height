from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _configure_frozen_tcl_tk() -> None:
    if not getattr(sys, "frozen", False):
        return

    executable_dir = Path(sys.executable).resolve().parent
    internal_dir = Path(getattr(sys, "_MEIPASS", executable_dir / "_internal"))
    search_roots = (internal_dir, executable_dir)
    tcl_candidates = [
        root / "_tcl_data" for root in search_roots
    ] + [
        root / "lib" / "tcl8.6" for root in search_roots
    ]
    tk_candidates = [
        root / "_tk_data" for root in search_roots
    ] + [
        root / "lib" / "tk8.6" for root in search_roots
    ]

    for candidate in tcl_candidates:
        if (candidate / "init.tcl").exists():
            os.environ["TCL_LIBRARY"] = str(candidate)
            break
    for candidate in tk_candidates:
        if (candidate / "tk.tcl").exists():
            os.environ["TK_LIBRARY"] = str(candidate)
            break


_configure_frozen_tcl_tk()

if "--self-test" in sys.argv:
    import tkinter
    from PIL import ImageTk

    root = tkinter.Tk()
    root.withdraw()
    root.destroy()
    print(f"tk={tkinter.TkVersion} imagetk={ImageTk.__name__}")
    raise SystemExit(0)

from pcb_fpp_decoder.debug_gui import main


if __name__ == "__main__":
    raise SystemExit(main())
