@echo off
REM Willow Tool Setup Script
REM Installs and configures required tools and dependencies

echo ========================================
echo Willow Tool Setup
echo ========================================
echo.

cd /d "%~dp0"

REM Check Python
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    echo Please install Python 3.10+ from python.org
    pause
    exit /b 1
) else (
    python --version
    echo [OK] Python found
)
echo.

REM Install Python packages
echo [2/5] Installing Python packages...
echo Installing: pdfplumber pytesseract pillow twilio
python -m pip install --upgrade pip >nul 2>&1
python -m pip install pdfplumber pytesseract pillow twilio scikit-learn numpy requests
if errorlevel 1 (
    echo [WARNING] Some packages may have failed to install
) else (
    echo [OK] Python packages installed
)
echo.

REM Check for Tesseract OCR
echo [3/5] Checking Tesseract OCR...
where tesseract >nul 2>&1
if errorlevel 1 (
    echo [!] Tesseract not found in PATH
    echo.
    echo Tesseract OCR is required for image text extraction.
    echo.
    echo Install options:
    echo   1. Windows installer: https://github.com/UB-Mannheim/tesseract/wiki
    echo   2. Chocolatey: choco install tesseract
    echo   3. Scoop: scoop install tesseract
    echo.
    echo After installation, add Tesseract to your PATH or the extraction
    echo module will fall back to Vision LLM (slower but still works).
    echo.
) else (
    tesseract --version | head -1
    echo [OK] Tesseract found
)
echo.

REM Check for cloudflared
echo [4/5] Checking cloudflared...
if exist "cloudflared.exe" (
    echo [OK] cloudflared.exe found in Willow directory
) else (
    where cloudflared >nul 2>&1
    if errorlevel 1 (
        echo [!] cloudflared not found
        echo.
        echo Cloudflare Tunnel is required for remote access.
        echo.
        echo Install options:
        echo   1. Download: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
        echo   2. winget: winget install Cloudflare.cloudflared
        echo   3. Place cloudflared.exe in the Willow directory
        echo.
    ) else (
        where cloudflared
        echo [OK] cloudflared found in PATH
    )
)
echo.

REM Create PATH helper script
echo [5/5] Creating PATH helper...
echo @echo off > add_to_path.bat
echo REM Add Willow to PATH temporarily (for current session) >> add_to_path.bat
echo set PATH=%cd%;%%PATH%% >> add_to_path.bat
echo echo [OK] Willow directory added to PATH for this session >> add_to_path.bat
echo [OK] Created add_to_path.bat (run this to add Willow to PATH temporarily)
echo.

echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Summary:
echo   - Python packages: Installed
echo   - Tesseract OCR: Check above for status
echo   - cloudflared: Check above for status
echo   - PATH helper: add_to_path.bat created
echo.
echo Next steps:
echo   1. Install any missing tools (Tesseract, cloudflared)
echo   2. Run start_daemons.bat to launch background services
echo   3. Run python server.py to start Willow
echo.
pause
