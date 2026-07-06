@echo off
setlocal

set "ROOT=%~dp0"
set "APP=%ROOT%dist\PCB_FPP_Simulator_GUI\PCB_FPP_Simulator_GUI.exe"

if not exist "%APP%" (
  echo PCB FPP Simulator app was not found:
  echo %APP%
  echo.
  echo Run build.bat first.
  pause
  exit /b 1
)

start "" "%APP%"
exit /b 0
