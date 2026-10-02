@echo off
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  py -m venv .venv || python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Package installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)
start "SRGPC Portal" http://127.0.0.1:5000
.venv\Scripts\python.exe app.py
pause
