@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found: .venv\Scripts\python.exe
  echo Create/install the project environment first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\run_validation_suite.py --open %*
set "suite_exit=%ERRORLEVEL%"
if not "%suite_exit%"=="0" (
  echo Validation suite completed with errors. Check validation_results\automated_suite\index.html
  pause
)
exit /b %suite_exit%
