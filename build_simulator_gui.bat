@echo off
setlocal EnableExtensions

chcp 65001 >nul
cd /d "%~dp0"

set "CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
set "OUT_DIR=dist\PCB_FPP_Simulator_GUI"
set "OUT_EXE=%OUT_DIR%\PCB_FPP_Simulator_GUI.exe"

if not exist "%CSC%" (
  set "CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)

if not exist "%CSC%" (
  echo ERROR: C# compiler was not found.
  exit /b 1
)

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

"%CSC%" /nologo /target:winexe /platform:anycpu /out:"%OUT_EXE%" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll tools\SimulatorGuiLauncher.cs
if errorlevel 1 goto :build_error

echo.
echo Build complete.
echo Simulator GUI EXE: %OUT_EXE%
echo.
exit /b 0

:build_error
echo.
echo ERROR: Simulator GUI build failed.
exit /b 1
