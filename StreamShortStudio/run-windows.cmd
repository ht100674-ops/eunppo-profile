@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.11 -m venv .venv
  if errorlevel 1 goto failed
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe tools\doctor.py
if errorlevel 1 goto failed
.venv\Scripts\python.exe main.py
if errorlevel 1 goto failed
exit /b 0
:failed
 echo Setup or runtime failed. Read README.md. Python 3.11 x64 and FFmpeg are required for source execution.
 pause
 exit /b 1
