@echo off
setlocal
set "ICE_LAUNCHER=%~dp0ICE_Local\START_WINDOWS.cmd"
if not exist "%ICE_LAUNCHER%" (
  echo ICE_Local\START_WINDOWS.cmd was not found.
  echo Extract the complete ZIP before running this launcher.
  pause
  exit /b 1
)
call "%ICE_LAUNCHER%"
