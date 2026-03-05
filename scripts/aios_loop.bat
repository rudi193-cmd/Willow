@echo off
setlocal
cd /d "%~dp0"
title Willow AIOS — Engine Only (Headless)

echo ==================================================
echo   WILLOW ENGINE — HEADLESS MODE
echo   File intake + processing only. No chat interface.
echo ==================================================
echo.

:: Start Ollama if not running
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Starting Ollama...
    start "OLLAMA" /min ollama serve
    timeout /t 5 >nul
)

:: Start the AIOS engine
start "AIOS ENGINE" python aios_loop.py

:: Start Kart refinery
start "KARTIKEYA REFINERY" python kart.py --user Sweet-Pea-Rudi19

echo.
echo [ONLINE] Engine + Refinery running in background.
echo Close this window anytime — background processes keep running.
echo Use KILL_SWITCH.bat to stop everything.
echo.
pause
