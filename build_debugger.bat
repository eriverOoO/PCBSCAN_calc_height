@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "CACHE_ROOT=%LOCALAPPDATA%\PCB_FPP_Decoder"
if "%LOCALAPPDATA%"=="" set "CACHE_ROOT=%USERPROFILE%\AppData\Local\PCB_FPP_Decoder"
set "VENV_DIR=%CACHE_ROOT%\debugger_venv_py312"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%VENV_DIR%\bin\python.exe"

if not exist "%PYTHON_EXE%" (
    call run_debugger.bat --prepare
    if errorlevel 1 exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo ERROR: Debugger runtime was not prepared.
    exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller in the external debugger runtime...
    "%PYTHON_EXE%" -m pip install --no-cache-dir pyinstaller
    if errorlevel 1 goto :pip_error
)

set "DEBUG_NAME=PCB_FPP_Debugger"
set "DIST_DIR=dist"
set "BUILD_DIR=%TEMP%\PCB_FPP_Debugger_pyinstaller_%RANDOM%"
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

set "PY_BASE_FILE=%BUILD_DIR%\python_base.txt"
"%PYTHON_EXE%" -c "import pathlib, sys; pathlib.Path(r'%PY_BASE_FILE%').write_text(str(pathlib.Path(sys.base_prefix)), encoding='utf-8')"
if errorlevel 1 goto :build_error
set /p "PY_BASE="<"%PY_BASE_FILE%"
if not defined PY_BASE goto :build_error

set "PY_TK_FILE=%BUILD_DIR%\python_tk_paths.txt"
"%PYTHON_EXE%" -c "import _tkinter, pathlib, sys, sysconfig; base=pathlib.Path(sys.base_prefix); stdlib=pathlib.Path(sysconfig.get_paths().get('stdlib') or base/'Lib'); candidates=[base/'tcl', base/'share', base/'lib']; names=('tcl8.6','tk8.6'); vals={'TKINTER_PYD': pathlib.Path(_tkinter.__file__), 'TKINTER_LIB': stdlib/'tkinter'}; [vals.setdefault(n.upper().replace('.','_') + '_DATA', d/n) for d in candidates for n in names if (d/n).exists()]; [vals.setdefault('TCL_DLL', p) for p in [base/'DLLs'/'tcl86t.dll', base/'DLLs'/'tcl86.dll', base/'bin'/'tcl86t.dll', base/'bin'/'tcl86.dll'] if p.exists()]; [vals.setdefault('TK_DLL', p) for p in [base/'DLLs'/'tk86t.dll', base/'DLLs'/'tk86.dll', base/'bin'/'tk86t.dll', base/'bin'/'tk86.dll'] if p.exists()]; pathlib.Path(r'%PY_TK_FILE%').write_text(''.join(f'{k}={v}\n' for k,v in vals.items()), encoding='utf-8')"
if errorlevel 1 goto :build_error
for /f "usebackq tokens=1,* delims==" %%A in ("%PY_TK_FILE%") do set "%%A=%%B"
if not defined TKINTER_PYD goto :build_error
if not defined TKINTER_LIB goto :build_error
if not defined TCL8_6_DATA goto :build_error
if not defined TK8_6_DATA goto :build_error

set "PYI_TK=--hidden-import tkinter --hidden-import tkinter.filedialog --hidden-import tkinter.font --hidden-import tkinter.messagebox --hidden-import tkinter.simpledialog --hidden-import tkinter.ttk --hidden-import tkinter.scrolledtext --add-binary %TKINTER_PYD%;. --add-data %TKINTER_LIB%;tkinter --add-data %TCL8_6_DATA%;_tcl_data --add-data %TK8_6_DATA%;_tk_data --add-data %TCL8_6_DATA%;lib\tcl8.6 --add-data %TK8_6_DATA%;lib\tk8.6"
if defined TCL_DLL set "PYI_TK=%PYI_TK% --add-binary %TCL_DLL%;."
if defined TK_DLL set "PYI_TK=%PYI_TK% --add-binary %TK_DLL%;."
set "PYI_COMMON=--noconfirm --onedir --distpath %DIST_DIR% --workpath %BUILD_DIR% --specpath %BUILD_DIR% --collect-data matplotlib --hidden-import matplotlib.backends.backend_agg --hidden-import mpl_toolkits.mplot3d --hidden-import scipy.ndimage --hidden-import PIL.Image --hidden-import PIL.ImageTk --hidden-import cv2 %PYI_TK% --exclude-module=pytest --exclude-module=matplotlib.tests --exclude-module=scipy.tests"

echo Building debugger executable only...
"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%DEBUG_NAME%" --windowed "scripts\run_debug_gui.py"
if errorlevel 1 goto :build_error

rmdir /s /q "%BUILD_DIR%" >nul 2>nul
echo.
echo Build complete: %DIST_DIR%\%DEBUG_NAME%\%DEBUG_NAME%.exe
exit /b 0

:pip_error
echo ERROR: PyInstaller installation failed.
exit /b 1

:build_error
echo ERROR: Debugger EXE build failed. Temporary files remain in %BUILD_DIR%.
exit /b 1
