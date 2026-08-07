@echo off
setlocal
cd /d "%~dp0"

set "SUITE=%~1"
set "VALIDATION_TOOL=tools\run_validation_suite.py"
set "FAILURE_MESSAGE=Validation suite completed with errors."
set "RESULT_PATH=validation_results\automated_suite\index.html"

if "%SUITE%"=="" set "SUITE=default"
if /I "%SUITE%"=="--suite" (
  set "SUITE=%~2"
  shift
  shift
)

if /I "%SUITE%"=="reference-board" (
  set "VALIDATION_TOOL=tools\run_reference_board_suite.py"
  set "RESULT_PATH=validation_results\reference_board\index.html"
)
if /I "%SUITE%"=="source-grounded" (
  set "VALIDATION_TOOL=tools\run_source_grounded_suite.py"
  set "FAILURE_MESSAGE=Source-grounded validation completed with errors."
  set "RESULT_PATH=validation_results\source_grounded\source_grounded_index.html"
)
if /I "%SUITE%"=="ximea-observed" (
  set "VALIDATION_TOOL=tools\run_ximea_observed_suite.py"
  set "FAILURE_MESSAGE=XIMEA-observed validation completed with errors."
  set "RESULT_PATH=validation_results\ximea_observed\ximea_observed_index.html"
)
if /I not "%SUITE%"=="default" if /I not "%SUITE%"=="reference-board" if /I not "%SUITE%"=="source-grounded" if /I not "%SUITE%"=="ximea-observed" (
  echo Unknown validation suite: %SUITE%
  echo Use: default, reference-board, source-grounded, or ximea-observed.
  exit /b 2
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
