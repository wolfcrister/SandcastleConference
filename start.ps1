# Stop any existing Chainlit process on port 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        Write-Host ('Stopping existing process on port 8000 (PID {0})...' -f $_)
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Milliseconds 500

# Activate venv if present, then launch
$venvChainlit = Join-Path $PSScriptRoot ".venv\Scripts\chainlit.exe"
if (Test-Path $venvChainlit) {
    Write-Host "Launching Chainlit from .venv..."
    & $venvChainlit run (Join-Path $PSScriptRoot "app.py")
} else {
    Write-Host "Launching Chainlit from system Python..."
    chainlit run (Join-Path $PSScriptRoot "app.py")
}
