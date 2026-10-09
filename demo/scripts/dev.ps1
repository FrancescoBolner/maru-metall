# Development on Windows: API with auto-reload on :8000 and the Vite dev server on :5173 (two windows).
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv\Scripts\python.exe")) { & (Join-Path $PSScriptRoot "start.ps1"); exit }
& .\.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r backend\requirements-dev.txt
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000 --reload --reload-dir backend"
Push-Location frontend; if (-not (Test-Path node_modules)) { npm ci --no-audit --no-fund }; npm run dev; Pop-Location
