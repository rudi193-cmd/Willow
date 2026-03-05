@echo off
REM Willow Daemon Stopper
REM Gracefully stops all background daemons

echo ========================================
echo Willow Fractal AI OS - Daemon Stopper
echo ========================================
echo.

echo Stopping daemons...
echo.

REM Kill all Willow daemon processes
taskkill /FI "WINDOWTITLE eq Willow-GovernanceMonitor" /F >nul 2>&1
if not errorlevel 1 echo [OK] Governance Monitor stopped

taskkill /FI "WINDOWTITLE eq Willow-CoherenceScanner" /F >nul 2>&1
if not errorlevel 1 echo [OK] Coherence Scanner stopped

taskkill /FI "WINDOWTITLE eq Willow-TopologyBuilder" /F >nul 2>&1
if not errorlevel 1 echo [OK] Topology Builder stopped

taskkill /FI "WINDOWTITLE eq Willow-KnowledgeCompactor" /F >nul 2>&1
if not errorlevel 1 echo [OK] Knowledge Compactor stopped

taskkill /FI "WINDOWTITLE eq Willow-SAFESync" /F >nul 2>&1
if not errorlevel 1 echo [OK] SAFE Sync stopped

taskkill /FI "WINDOWTITLE eq Willow-PersonaScheduler" /F >nul 2>&1
if not errorlevel 1 echo [OK] Persona Scheduler stopped

echo.
echo ========================================
echo All daemons stopped!
echo ========================================
echo.
pause
