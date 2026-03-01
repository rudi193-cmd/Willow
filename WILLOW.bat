@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title WILLOW

if not exist logs mkdir logs

echo.
echo   W I L L O W
echo   Community Memory Sovereign OS
echo   ________________________________
echo.

:: ---------------------------------------------------------------
:: 1. OLLAMA (local fleet)
:: ---------------------------------------------------------------
echo [1/5] Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo       not running -- starting...
    start "OLLAMA" /min ollama serve
    set retries=0
    :wait_ollama
    timeout /t 2 >nul
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if %errorlevel% neq 0 (
        set /a retries+=1
        if !retries! lss 15 goto :wait_ollama
        echo       [WARN] Ollama didn't respond -- continuing without local fleet
    ) else (
        echo       OK (local LLMs available)
    )
) else (
    echo       already running. OK.
)

:: ---------------------------------------------------------------
:: 2. GOVERNANCE CHECK
:: ---------------------------------------------------------------
echo [2/5] Governance core...
set missing=0
for %%f in (core\state.py core\gate.py core\storage.py) do (
    if not exist %%f (
        echo       [FATAL] %%f missing
        set missing=1
    )
)
if %missing%==1 (
    echo       Halted -- governance core incomplete.
    pause
    exit /b 1
)
echo       OK (state, gate, storage)

:: ---------------------------------------------------------------
:: 3. AIOS ENGINE  — DEPRECATED, replaced by modular daemons below
:: ---------------------------------------------------------------
echo [3/5] AIOS Engine... (deprecated -- skipped)
:: start "WILLOW-ENGINE" /min cmd /c "python aios_loop.py >> logs\aios_engine.log 2>&1"

:: ---------------------------------------------------------------
:: 4. KART  (VISIBLE window -- watch what Kart is doing)
:: ---------------------------------------------------------------
echo [4/5] Kart...
start "WILLOW - KART" cmd /k python kart.py
echo       REPL started in visible window

:: ---------------------------------------------------------------
:: 5. SERVER  (VISIBLE window -- see errors when it breaks)
:: ---------------------------------------------------------------
echo [5/5] Server...
start "WILLOW - SERVER" python -m uvicorn server:app --host 0.0.0.0 --port 8420 --reload --log-level info

echo       waiting for :8420...
set retries=0
:wait_server
timeout /t 2 >nul
curl -s http://127.0.0.1:8420/api/health >nul 2>&1
if %errorlevel% equ 0 goto :server_ok
set /a retries+=1
if !retries! geq 20 (
    echo.
    echo   [FAIL] Server not up after 40s.
    echo   Check the "WILLOW - SERVER" window for the error.
    echo.
    pause
    goto :shutdown
)
goto :wait_server

:server_ok
echo       OK -- http://127.0.0.1:8420

:: ---------------------------------------------------------------
:: OPTIONAL DAEMONS  (background, logged -- check logs\ on failure)
:: ---------------------------------------------------------------
echo.
echo   -- optional daemons --
if exist governance\monitor.py (
    start "WILLOW-GovernanceMonitor"   /min cmd /c "python governance\monitor.py --interval 60 --daemon       >> logs\governance_monitor.log 2>&1"
    echo   governance monitor    logs\governance_monitor.log
)
if exist core\coherence_scanner.py (
    start "WILLOW-CoherenceScanner"    /min cmd /c "python core\coherence_scanner.py --interval 3600 --daemon >> logs\coherence_scanner.log 2>&1"
    echo   coherence scanner     logs\coherence_scanner.log
)
if exist core\topology_builder.py (
    start "WILLOW-TopologyBuilder"     /min cmd /c "python core\topology_builder.py --interval 3600 --daemon  >> logs\topology_builder.log 2>&1"
    echo   topology builder      logs\topology_builder.log
)
if exist core\knowledge_compactor.py (
    start "WILLOW-KnowledgeCompactor"  /min cmd /c "python core\knowledge_compactor.py --interval 86400 --daemon >> logs\knowledge_compactor.log 2>&1"
    echo   knowledge compactor   logs\knowledge_compactor.log
)
if exist core\safe_sync.py (
    start "WILLOW-SAFESync"            /min cmd /c "python core\safe_sync.py --interval 300 --daemon          >> logs\safe_sync.log 2>&1"
    echo   safe sync             logs\safe_sync.log
)
if exist core\persona_scheduler.py (
    start "WILLOW-PersonaScheduler"    /min cmd /c "python core\persona_scheduler.py --interval 60 --daemon   >> logs\persona_scheduler.log 2>&1"
    echo   persona scheduler     logs\persona_scheduler.log
)
if exist apps\watcher.py (
    start "WILLOW-InboxWatcher"        /min cmd /c "python apps\watcher.py --no-consent                       >> logs\watcher.log 2>&1"
    echo   inbox watcher         logs\watcher.log
)
if exist core\watcher.py (
    start "WILLOW-NestWatcher"         /min cmd /c "python core\watcher.py --no-consent                       >> logs\watcher_nest.log 2>&1"
    echo   nest watcher          logs\watcher_nest.log
)

:: ---------------------------------------------------------------
:: TUNNEL (optional)
:: ---------------------------------------------------------------
echo.
set CF_EXE=cloudflared
if exist "%~dp0cloudflared.exe" set CF_EXE=%~dp0cloudflared.exe
%CF_EXE% version >nul 2>&1
if %errorlevel% neq 0 (
    echo   No tunnel (cloudflared not found -- local only)
    echo.
    echo   ========================================
    echo    WILLOW IS READY
    echo    http://127.0.0.1:8420
    echo.
    echo    Agents:  GET /api/agents/list
    echo    Chat:    POST /api/agents/chat/kart
    echo    Health:  GET /api/health
    echo.
    echo    Kart output:   WILLOW - KART window
    echo    Server output: WILLOW - SERVER window
    echo    Daemon logs:   logs\
    echo.
    echo    Press Any Key To Exit
    echo   ========================================
    echo.
    pause >nul
    goto :shutdown
)

echo.
echo   ========================================
echo    WILLOW IS READY
echo    http://127.0.0.1:8420
echo    Tunnel starting...
echo.
echo    Agents:  GET /api/agents/list
echo    Chat:    POST /api/agents/chat/kart
echo    Health:  GET /api/health
echo.
echo    Kart output:   WILLOW - KART window
echo    Server output: WILLOW - SERVER window
echo    Daemon logs:   logs\
echo   ========================================
echo.
python apps\tunnel.py

:: ---------------------------------------------------------------
:: SHUTDOWN
:: ---------------------------------------------------------------
:shutdown
echo.
echo   Shutting down...
for %%p in (
    "WILLOW-ENGINE"
    "WILLOW - KART"
    "WILLOW - SERVER"
    "WILLOW-GovernanceMonitor"
    "WILLOW-CoherenceScanner"
    "WILLOW-TopologyBuilder"
    "WILLOW-KnowledgeCompactor"
    "WILLOW-SAFESync"
    "WILLOW-PersonaScheduler"
    "WILLOW-InboxWatcher"
) do taskkill /FI "WINDOWTITLE eq %%~p" >nul 2>&1
echo   Done. (Ollama left running)
echo.
echo   Press Any Key To Exit
pause >nul
cmd /k
