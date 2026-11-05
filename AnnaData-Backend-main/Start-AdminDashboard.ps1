$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.env.admin')) {
    throw 'Run tools/setup_analytics.py --initialize first to create the private admin configuration.'
}
Write-Host 'AnnaData private dashboard: http://127.0.0.1:8766/admin'
Write-Host 'Use ADMIN_API_TOKEN from .env.admin to sign in. Ctrl+C stops the dashboard.'
Start-Process 'http://127.0.0.1:8766/admin'
& "$PSScriptRoot/.venv/Scripts/python.exe" -m uvicorn admin_server:app --host 127.0.0.1 --port 8766
