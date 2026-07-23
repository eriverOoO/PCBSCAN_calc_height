@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found: .venv\Scripts\python.exe
  echo Create/install the project environment first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\run_source_grounded_suite.py --open %*
set "suite_exit=%ERRORLEVEL%"
if not "%suite_exit%"=="0" (
  echo Source-grounded validation completed with errors.
  echo Check validation_results\source_grounded\source_grounded_index.html
  pause
)
exit /b %suite_exit%
