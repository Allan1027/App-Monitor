@echo off
title APPs Monitor - Starting...
color 0A

echo.
echo  ================================================
echo    APPs Monitor - Starting up...
echo  ================================================
echo.

:: Change to the folder where this bat file lives
cd /d "%~dp0"

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python and try again.
    pause
    exit /b 1
)

:: Install dependencies silently if needed
echo [1/3] Checking dependencies...
pip install flask flask-cors >nul 2>&1
echo       Done.

:: Start the Python backend in a minimised window
echo [2/3] Starting backend server...
start "APPs Monitor Backend" /min python "%~dp0server.py"

:: Wait 2 seconds for Flask to boot up
timeout /t 2 /nobreak >nul

:: Open the dashboard in the default browser
echo [3/3] Opening dashboard...
start "" "%~dp0dashboard.html"

echo.
echo  Dashboard is now open in your browser.
echo  Backend is running in the background.
echo  Close the backend window to shut everything down.
echo.
echo  [Press any key to close this window]
pause >nul
