@echo off
REM Sync GitHub/Willow code changes to My Drive/Willow
REM Run this after making changes you want visible on phone

echo.
echo ================================
echo   SYNC: GitHub to My Drive
echo ================================
echo.

cd /d "C:\Users\Sean\My Drive\Willow"

echo [1/3] Fetching latest from GitHub/Willow...
git fetch file:///C:/Users/Sean/Documents/GitHub/Willow main

echo [2/3] Resetting to match GitHub/Willow...
git reset --hard FETCH_HEAD

echo [3/3] Checking status...
git log --oneline -1

echo.
echo ================================
echo   SYNC COMPLETE
echo ================================
echo   My Drive/Willow is now up-to-date
echo   Files visible in Google Drive app
echo ================================
echo.
pause
