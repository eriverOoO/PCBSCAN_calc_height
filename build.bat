@echo off
setlocal EnableExtensions

chcp 65001 >nul
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "GUI_NAME=PCB_FPP_Decoder"
set "CLI_NAME=PCB_FPP_Decoder_CLI"
set "SIM_GUI_NAME=PCB_FPP_Simulator"
set "SIM_CLI_NAME=PCB_FPP_Simulator_CLI"
set "BUILD_DIR=%TEMP%\PCB_FPP_Decoder_pyinstaller_%RANDOM%"
set "DIST_DIR=dist"

echo.
echo PCB FPP Decoder EXE build
echo =========================
echo.

echo [1/6] Preparing Python virtual environment...
if not exist "%PYTHON_EXE%" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 goto :venv_error
)

echo [2/6] Installing build dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :pip_error
"%PYTHON_EXE%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :pip_error

echo [3/6] Building decoder no-console GUI executable...
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

set "PYI_COMMON=--noconfirm --onedir --distpath %DIST_DIR% --workpath %BUILD_DIR% --specpath %BUILD_DIR% --collect-data matplotlib --hidden-import matplotlib.backends.backend_agg --hidden-import mpl_toolkits.mplot3d --hidden-import scipy.ndimage --hidden-import PIL.Image --hidden-import cv2 --exclude-module=pytest --exclude-module=matplotlib.tests --exclude-module=scipy.tests"

"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%GUI_NAME%" --windowed "scripts\run_gui.py"
if errorlevel 1 goto :build_error

echo [4/6] Building decoder CLI executable...
"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%CLI_NAME%" --console "scripts\decode_scan.py"
if errorlevel 1 goto :build_error

echo [5/6] Building simulator executable...
"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%SIM_GUI_NAME%" --console "scripts\run_simulator_gui.py"
if errorlevel 1 goto :build_error

echo [6/6] Building simulator CLI executable...
"%PYTHON_EXE%" -m PyInstaller %PYI_COMMON% --name "%SIM_CLI_NAME%" --console "scripts\simulate_virtual_scan.py"
if errorlevel 1 goto :build_error

echo.
echo Build complete.
echo GUI EXE: %DIST_DIR%\%GUI_NAME%\%GUI_NAME%.exe
echo CLI EXE: %DIST_DIR%\%CLI_NAME%\%CLI_NAME%.exe
echo Simulator GUI EXE: %DIST_DIR%\%SIM_GUI_NAME%\%SIM_GUI_NAME%.exe
echo Simulator CLI EXE: %DIST_DIR%\%SIM_CLI_NAME%\%SIM_CLI_NAME%.exe
echo.
echo Normal users should run:
echo   %DIST_DIR%\%GUI_NAME%\%GUI_NAME%.exe
echo or double-click:
echo   PCB_FPP_Decoder.vbs
echo Simulator users should run:
echo   %DIST_DIR%\%SIM_GUI_NAME%\%SIM_GUI_NAME%.exe
echo or double-click:
echo   PCB_FPP_Simulator.vbs
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
