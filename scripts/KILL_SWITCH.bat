@echo off
echo [*] INITIATING EMERGENCY SHUTDOWN...
taskkill /F /IM python.exe /T
echo [OK] All Python processes terminated.
echo [*] Stopping Ollama...
taskkill /F /IM ollama_app.exe /T
taskkill /F /IM ollama.exe /T
echo [OK] System silenced.
pause