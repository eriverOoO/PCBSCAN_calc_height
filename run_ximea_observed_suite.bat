@echo off
setlocal
call "%~dp0run_validation_suite.bat" --runner "tools\run_ximea_observed_suite.py" "XIMEA-observed validation completed with errors." "validation_results\ximea_observed\ximea_observed_index.html" %*
exit /b %ERRORLEVEL%
