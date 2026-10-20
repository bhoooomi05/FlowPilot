# FlowPilot AI local start. Run from the project root.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11+ was not found. Install Python from https://www.python.org/downloads/windows/ and enable Add Python to PATH."
}
if (-not (Test-Path "backend\.venv\Scripts\python.exe")) {
  python -m venv backend\.venv
}
& "backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Write-Host "Optional: copy .env.example to .env and add your GROQ_API_KEY." -ForegroundColor Yellow
}
Set-Location backend
Write-Host "FlowPilot AI running at http://localhost:8000" -ForegroundColor Green
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
