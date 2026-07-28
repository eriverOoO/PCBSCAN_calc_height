@echo off
setlocal
call "%~dp0run_validation_suite.bat" --runner "tools\run_source_grounded_suite.py" "Source-grounded validation completed with errors." "validation_results\source_grounded\source_grounded_index.html" %*
exit /b %ERRORLEVEL%
