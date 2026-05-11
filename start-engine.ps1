$ErrorActionPreference = "Stop"

Write-Host "Starting Subvision Studio Backend..." -ForegroundColor Cyan

# Set PYTHONPATH to the root of the project
$env:PYTHONPATH = $PSScriptRoot

# Use the explicitly installed Python 3.11 via the Py launcher
py -3.11 -m uvicorn engine.main:app --reload --host 0.0.0.0 --port 9000
