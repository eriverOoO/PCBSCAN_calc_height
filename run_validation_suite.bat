@echo off
setlocal
cd /d "%~dp0"

set "VALIDATION_TOOL=tools\run_validation_suite.py"
set "FAILURE_MESSAGE=Validation suite completed with errors."
set "RESULT_PATH=validation_results\automated_suite\index.html"

if /I "%~1"=="--runner" (
  set "VALIDATION_TOOL=%~2"
  set "FAILURE_MESSAGE=%~3"
  set "RESULT_PATH=%~4"
  shift
  shift
  shift
  shift
)

if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found: .venv\Scripts\python.exe
  echo Create/install the project environment first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "%VALIDATION_TOOL%" --open %*
set "suite_exit=%ERRORLEVEL%"
if not "%suite_exit%"=="0" (
  echo %FAILURE_MESSAGE%
  echo Check %RESULT_PATH%
  pause
)
exit /b %suite_exit%
