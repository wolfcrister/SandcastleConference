@echo off
title Sandcastle Conference
cd /d "%~dp0"

echo ================================================
echo   Sandcastle Conference - War Room
echo ================================================
echo.

REM Kill any existing process on port 8000
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" 2>nul

REM Brief pause to release the port
timeout /t 1 /nobreak >nul

REM Check venv exists
if not exist ".venv\Scripts\chainlit.exe" (
    echo ERROR: .venv not found. Run: python -m venv .venv
    echo Then: .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Chainlit...
echo Opening browser in 3 seconds...
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

.venv\Scripts\chainlit.exe run app.py

echo.
echo Chainlit has stopped.
pause
