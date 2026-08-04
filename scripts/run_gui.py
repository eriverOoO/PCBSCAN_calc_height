from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _configure_frozen_tcl_tk() -> None:
    """Point a PyInstaller build at the bundled Tcl/Tk data directories."""
    if not getattr(sys, "frozen", False):
        return

    executable_dir = Path(sys.executable).resolve().parent
    internal_dir = Path(getattr(sys, "_MEIPASS", executable_dir / "_internal"))
    search_roots = (internal_dir, executable_dir)
    for environment_name, directory_name, marker_name in (
        ("TCL_LIBRARY", "_tcl_data", "init.tcl"),
        ("TK_LIBRARY", "_tk_data", "tk.tcl"),
    ):
        candidates = [root / directory_name for root in search_roots] + [
            root / "lib" / ("tcl8.6" if environment_name == "TCL_LIBRARY" else "tk8.6")
            for root in search_roots
        ]
        for candidate in candidates:
            if (candidate / marker_name).exists():
                os.environ[environment_name] = str(candidate)
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

from pcb_fpp_decoder.gui import main


if __name__ == "__main__":
    raise SystemExit(main())
