@echo off
setlocal
cd /d "%~dp0"
title ICE Local - Citation Extractor
if exist "runtime\python.exe" goto portable
if exist ".venv\Scripts\python.exe" goto run
echo Setting up ICE Local. Internet is needed for this first setup only.
where py >nul 2>nul
if errorlevel 1 goto trypython
py -3 -m venv .venv
if errorlevel 1 goto failure
goto install
:trypython
where python >nul 2>nul
if errorlevel 1 goto nopython
python -m venv .venv
if errorlevel 1 goto failure
:install
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failure
:run
".venv\Scripts\python.exe" -c "import fitz,lxml" >nul 2>nul
if errorlevel 1 goto install
".venv\Scripts\python.exe" -X utf8 app.py
if errorlevel 1 goto failure
exit /b 0
:portable
"runtime\python.exe" -c "import encodings, fitz, lxml" >nul 2>nul
if errorlevel 1 (
    echo.
    echo The bundled Python runtime is incomplete or damaged.
    echo Please download and extract the latest ICE ZIP again, then run START_ICE.cmd.
    echo If you have saved articles, back up the old ICE_Local\data folder first.
    goto failure
)
"runtime\python.exe" -X utf8 app.py
if errorlevel 1 goto failure
exit /b 0
:nopython
echo.
echo Python is not installed. Install 64-bit Python 3.12 or newer from python.org.
echo Select Add Python to PATH during installation, then open this file again.
pause
exit /b 1
:failure
echo.
echo ICE could not start. The error above explains what happened.
echo Your saved articles in the data folder have not been deleted.
pause
exit /b 1
