@echo off
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Run build_tools\bootstrap.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py --desktop %*
