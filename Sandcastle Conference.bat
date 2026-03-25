@echo off
title Sandcastle Conference
cd /d "%~dp0"

echo ================================================
echo   Sandcastle Conference - War Room
echo ================================================
echo.

REM Kill any existing process on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Stopping existing process on port 8000 (PID %%a)...
    taskkill /PID %%a /F >nul 2>&1
)

REM Brief pause to release the port
timeout /t 1 /nobreak >nul

REM Open the browser after a short delay (background)
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

REM Launch Chainlit from venv or system Python
if exist ".venv\Scripts\chainlit.exe" (
    echo Starting from .venv...
    .venv\Scripts\chainlit.exe run app.py
) else (
    echo Starting from system Python...
    chainlit run app.py
)

pause
