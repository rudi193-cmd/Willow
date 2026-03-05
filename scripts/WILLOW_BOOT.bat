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

:: 4. START KART (DEPRECATED — Kart now runs as pulse.py via start_daemons.bat)
:: echo [*] Starting Kartikeya Refinery...
:: start "KARTIKEYA REFINERY" python kart.py --user Sweet-Pea-Rudi19

:: 5. START THE VOICE (DEPRECATED — now server.py via uvicorn)
:: echo [*] Awakening Interface...
:: python local_api.py

:: USE start_daemons.bat + server.py instead
echo [*] Use start_daemons.bat to launch all daemons.
echo [*] Use: uvicorn server:app --host 0.0.0.0 --port 8420 to start Willow.
echo.
pause

:: 6. SHUTDOWN — use stop_daemons.bat or KILL_SWITCH.bat
