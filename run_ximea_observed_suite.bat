@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found: .venv\Scripts\python.exe
  echo Create/install the project environment first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\run_ximea_observed_suite.py --open %*
set "suite_exit=%ERRORLEVEL%"
if not "%suite_exit%"=="0" (
  echo XIMEA-observed validation completed with errors.
  echo Check validation_results\ximea_observed\ximea_observed_index.html
  pause
)
exit /b %suite_exit%
