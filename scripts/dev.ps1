# Plain HTML/CSS/JS frontend is served by FastAPI; no Node.js build is required.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11+ was not found. Install Python from https://www.python.org/downloads/windows/ and enable Add Python to PATH."
}
if (-not (Test-Path "backend\.venv\Scripts\python.exe")) { python -m venv backend\.venv }
& "backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
Set-Location backend
Write-Host "FlowPilot AI development server: http://localhost:8000" -ForegroundColor Green
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
