# One command without Docker (Windows PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1      → http://localhost:8000
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$port = if ($env:PORT) { $env:PORT } else { "8000" }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating the Python environment (.venv)..."
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.12", "3.13", "3.11")) {
            try { & py "-$v" -m venv .venv; if ($LASTEXITCODE -eq 0) { $created = $true; break } } catch { }
        }
    }
    if (-not $created) { python -m venv .venv }
}
Write-Host "Installing Python packages (first time takes a few minutes)..."
& .\.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r backend\requirements.txt

if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "Building the web app..."
    Push-Location frontend; npm ci --no-audit --no-fund; npm run build; Pop-Location
}

Write-Host "Maru Takeoff & Quoting Assistant -> http://localhost:$port  (Ctrl+C to stop)"
Start-Job -ScriptBlock { param($p) Start-Sleep -Seconds 5; Start-Process "http://localhost:$p" } -ArgumentList $port | Out-Null
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $port
