@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "CACHE_ROOT=%LOCALAPPDATA%\PCB_FPP_Decoder"
if "%LOCALAPPDATA%"=="" set "CACHE_ROOT=%USERPROFILE%\AppData\Local\PCB_FPP_Decoder"
set "VENV_DIR=%CACHE_ROOT%\debugger_venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "NEEDS_INSTALL=0"

if not "%~1"=="" if /I not "%~1"=="--refresh" goto :usage
if /I "%~1"=="--refresh" set "NEEDS_INSTALL=1"

if not exist "%PYTHON_EXE%" (
    if not exist "%CACHE_ROOT%" mkdir "%CACHE_ROOT%"
    if errorlevel 1 goto :venv_error

    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv "%VENV_DIR%"
    ) else (
        py -3 -m venv "%VENV_DIR%"
    )
    if errorlevel 1 goto :venv_error
    set "NEEDS_INSTALL=1"
)

if "%NEEDS_INSTALL%"=="1" (
    echo Preparing the external debugger runtime...
    "%PYTHON_EXE%" -m pip install --no-cache-dir -r requirements.txt
    if errorlevel 1 goto :pip_error
)

"%PYTHON_EXE%" scripts\run_debug_gui.py
exit /b %ERRORLEVEL%

:usage
echo Usage: run_debugger.bat [--refresh]
echo   --refresh  Reinstall the debugger dependencies in the external runtime.
exit /b 2

:venv_error
echo ERROR: Could not create the external debugger runtime. Install Python 3.10+ and try again.
exit /b 1

:pip_error
echo ERROR: Dependency installation failed. Check your internet connection or pip access.
exit /b 1
