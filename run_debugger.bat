@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "CACHE_ROOT=%LOCALAPPDATA%\PCB_FPP_Decoder"
if "%LOCALAPPDATA%"=="" set "CACHE_ROOT=%USERPROFILE%\AppData\Local\PCB_FPP_Decoder"
set "VENV_DIR=%CACHE_ROOT%\debugger_venv_py312"
set "NEEDS_INSTALL=0"
set "PREPARE_ONLY=0"

if not "%~1"=="" if /I not "%~1"=="--refresh" if /I not "%~1"=="--prepare" goto :usage
if /I "%~1"=="--refresh" set "NEEDS_INSTALL=1"
if /I "%~1"=="--prepare" set "PREPARE_ONLY=1"

call :find_venv_python
if not defined PYTHON_EXE (
    if not exist "%CACHE_ROOT%" mkdir "%CACHE_ROOT%"
    if errorlevel 1 goto :venv_error

    call :create_venv
    if errorlevel 1 goto :venv_error
    call :find_venv_python
    if not defined PYTHON_EXE goto :venv_error
)

if not exist "%VENV_DIR%\.runtime_ready" set "NEEDS_INSTALL=1"

if "%NEEDS_INSTALL%"=="1" (
    echo Preparing the external debugger runtime...
    "%PYTHON_EXE%" -m pip install --no-cache-dir -r requirements.txt
    if errorlevel 1 goto :pip_error
    type nul > "%VENV_DIR%\.runtime_ready"
)

if "%PREPARE_ONLY%"=="1" exit /b 0

"%PYTHON_EXE%" scripts\run_debug_gui.py
exit /b %ERRORLEVEL%

:usage
echo Usage: run_debugger.bat [--refresh ^| --prepare]
echo   --refresh  Reinstall the debugger dependencies in the external runtime.
echo   --prepare  Install dependencies without opening the debugger.
exit /b 2

:venv_error
echo ERROR: Could not create the external debugger runtime. Install Python 3.10+ and try again.
exit /b 1

:pip_error
echo ERROR: Dependency installation failed. Check your internet connection or pip access.
exit /b 1

:find_venv_python
set "PYTHON_EXE="
if exist "%VENV_DIR%\Scripts\python.exe" set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%VENV_DIR%\bin\python.exe" set "PYTHON_EXE=%VENV_DIR%\bin\python.exe"
exit /b 0

:create_venv
if defined DEBUGGER_PYTHON if exist "%DEBUGGER_PYTHON%" (
    "%DEBUGGER_PYTHON%" -m venv "%VENV_DIR%"
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv "%VENV_DIR%"
    exit /b %ERRORLEVEL%
)

for %%P in ("%~dp0..\..\python.exe") do set "FALLBACK_PYTHON=%%~fP"
if not exist "%FALLBACK_PYTHON%" set "FALLBACK_PYTHON="
if not defined FALLBACK_PYTHON (
    for %%P in ("%~dp0..\..\*\python.exe") do if not defined FALLBACK_PYTHON set "FALLBACK_PYTHON=%%~fP"
)
if exist "%FALLBACK_PYTHON%" (
    "%FALLBACK_PYTHON%" -m venv "%VENV_DIR%"
    exit /b %ERRORLEVEL%
)

python -m venv "%VENV_DIR%"
exit /b %ERRORLEVEL%
