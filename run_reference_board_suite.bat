@echo off
setlocal
call "%~dp0run_validation_suite.bat" --runner "tools\run_reference_board_suite.py" "Validation suite completed with errors." "validation_results\reference_board\index.html" %*
exit /b %ERRORLEVEL%
