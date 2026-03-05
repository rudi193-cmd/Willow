@echo off
REM Check if GitHub/Willow and My Drive/Willow are in sync

echo.
echo ================================
echo   SYNC STATUS CHECK
echo ================================
echo.

echo [GitHub/Willow]
cd /d "C:\Users\Sean\Documents\GitHub\Willow"
git log --oneline -1

echo.
echo [My Drive/Willow]
cd /d "C:\Users\Sean\My Drive\Willow"
git log --oneline -1

echo.
echo ================================
echo   If commits don't match, run:
echo   sync_to_drive.bat
echo ================================
echo.
pause
