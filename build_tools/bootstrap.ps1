# Run from a standard (not Administrator) PowerShell window.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 x64 from python.org first.' }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .\.venv\Scripts\python.exe main.py --setup
