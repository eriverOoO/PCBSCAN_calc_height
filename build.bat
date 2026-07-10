@echo off
setlocal EnableExtensions

chcp 65001 >nul
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "GUI_NAME=PCB_FPP_Decoder"
set "CLI_NAME=PCB_FPP_Decoder_CLI"
set "DEBUG_NAME=PCB_FPP_Debugger"
set "BUILD_DIR=%TEMP%\PCB_FPP_Decoder_pyinstaller_%RANDOM%"
set "DIST_DIR=dist"

echo.
echo PCB FPP Decoder EXE build
echo =========================
echo.

echo [1/4] Preparing Python virtual environment...
if not exist "%PYTHON_EXE%" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 goto :venv_error
)

echo [2/4] Installing build dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :pip_error
"%PYTHON_EXE%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :pip_error

echo [3/5] Building decoder no-console GUI executable...
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

set "PY_BASE_FILE=%BUILD_DIR%\python_base.txt"
"%PYTHON_EXE%" -c "import pathlib, sys; pathlib.Path(r'%PY_BASE_FILE%').write_text(str(pathlib.Path(sys.base_prefix)), encoding='utf-8')"
if errorlevel 1 goto :build_error
set /p "PY_BASE="<"%PY_BASE_FILE%"
if not defined PY_BASE goto :build_error
set "PYI_TK=--hidden-import tkinter --hidden-import tkinter.filedialog --hidden-import tkinter.font --hidden-import tkinter.messagebox --hidden-import tkinter.simpledialog --hidden-import tkinter.ttk --hidden-import tkinter.scrolledtext --add-binary %PY_BASE%\DLLs\_tkinter.pyd;. --add-binary %PY_BASE%\DLLs\tcl86t.dll;. --add-binary %PY_BASE%\DLLs\tk86t.dll;. --add-data %PY_BASE%\Lib\tkinter;tkinter --add-data %PY_BASE%\tcl\tcl8.6;_tcl_data --add-data %PY_BASE%\tcl\tk8.6;_tk_data --add-data %PY_BASE%\tcl\tcl8.6;lib\tcl8.6 --add-data %PY_BASE%\tcl\tk8.6;lib\tk8.6"
set "PYI_COMMON=--noconfirm --onedir --distpath %DIST_DIR% --workpath %BUILD_DIR% --specpath %BUILD_DIR% --collect-data matplotlib --hidden-import matplotlib.backends.backend_agg --hidden-import mpl_toolkits.mplot3d --hidden-import scipy.ndimage --hidden-import PIL.Image --hidden-import PIL.ImageTk --hidden-import cv2 %PYI_TK% --exclude-module=pytest --exclude-module=matplotlib.tests --exclude-module=scipy.tests"

"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%GUI_NAME%" --windowed "scripts\run_gui.py"
if errorlevel 1 goto :build_error

echo [4/5] Building decoder CLI executable...
"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%CLI_NAME%" --console "scripts\decode_scan.py"
if errorlevel 1 goto :build_error

echo [5/5] Building debugger no-console GUI executable...
"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%DEBUG_NAME%" --windowed "scripts\run_debug_gui.py"
if errorlevel 1 goto :build_error

echo.
echo Build complete.
echo GUI EXE: %DIST_DIR%\%GUI_NAME%\%GUI_NAME%.exe
echo CLI EXE: %DIST_DIR%\%CLI_NAME%\%CLI_NAME%.exe
echo Debug EXE: %DIST_DIR%\%DEBUG_NAME%\%DEBUG_NAME%.exe
echo.
echo Normal users should run:
echo   %DIST_DIR%\%GUI_NAME%\%GUI_NAME%.exe
echo Debugging tool:
echo   %DIST_DIR%\%DEBUG_NAME%\%DEBUG_NAME%.exe
echo or double-click:
echo   PCB_FPP_Decoder.vbs
echo.
exit /b 0

:venv_error
echo.
echo ERROR: Could not create .venv. Install Python 3.10+ and try again.
exit /b 1

:pip_error
echo.
echo ERROR: Dependency installation failed. Check your internet connection or pip access.
exit /b 1

:build_error
echo.
echo ERROR: PyInstaller build failed. See the messages above.
exit /b 1
