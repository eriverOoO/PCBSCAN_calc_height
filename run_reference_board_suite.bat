@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found: .venv\Scripts\python.exe
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\run_reference_board_suite.py --open %*
set "suite_exit=%ERRORLEVEL%"
if not "%suite_exit%"=="0" pause
exit /b %suite_exit%
