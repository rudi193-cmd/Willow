@echo off
setlocal
cd /d "%~dp0"
title WILLOW AIOS — SOVEREIGN BOOT

echo ========================================================
echo       WILLOW SOVEREIGN SYSTEM // BOOT SEQUENCE
echo ========================================================
echo.

:: 1. CHECK FOR OLLAMA (Local LLM Fleet)
echo [*] Pinging Ollama (localhost:11434)...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Ollama not responding. Starting Ollama Service...
    start "OLLAMA SERVICE" /min ollama serve
    timeout /t 5 >nul
) else (
    echo [OK] Ollama is active.
)

:: 2. VERIFY GOVERNANCE (Core modules)
echo [*] Verifying Governance Core...
if not exist core\state.py (
    echo [FATAL] core\state.py missing. System Halted.
    pause
    exit /b
)
if not exist core\gate.py (
    echo [FATAL] core\gate.py missing. System Halted.
    pause
    exit /b
)
if not exist core\storage.py (
    echo [FATAL] core\storage.py missing. System Halted.
    pause
    exit /b
)
echo [OK] Governance Core verified.

:: 3. START THE ENGINE — DEPRECATED, replaced by modular daemons in WILLOW.bat
:: echo [*] Igniting AIOS Engine...
:: start "AIOS ENGINE" python aios_loop.py

:: 4. START KART (Background — fast pre-classifier fallback)
echo [*] Starting Kartikeya Refinery...
start "KARTIKEYA REFINERY" python kart.py --user Sweet-Pea-Rudi19

:: 5. START THE VOICE (Foreground — chat interface)
echo [*] Awakening Interface...
echo.
echo ========================================================
echo   Engine + Refinery running in background windows.
echo   Chat interface starting below.
echo   Close this window to stop the interface.
echo ========================================================
echo.
python local_api.py

:: 6. SHUTDOWN PROTOCOL
echo.
echo ========================================================
echo [*] Interface closed.
echo [?] Kill background processes too? (Y/N)
set /p kill_bg=
if /i "%kill_bg%"=="Y" (
    taskkill /FI "WINDOWTITLE eq AIOS ENGINE" >nul 2>&1
    taskkill /FI "WINDOWTITLE eq KARTIKEYA REFINERY" >nul 2>&1
    echo [OK] All engines stopped.
)
pause
