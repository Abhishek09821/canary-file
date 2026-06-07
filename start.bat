@echo off
title Canary-File | Cyber Theft Detection System
color 0A

echo.
echo  ============================================
echo   CANARY-FILE - Deception Security System
echo  ============================================
echo.
echo  [*] Checking Python...

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.9+
    pause
    exit /b 1
)

echo  [*] Installing dependencies...
pip install -r requirements.txt -q --break-system-packages 2>nul || pip install -r requirements.txt -q

echo  [*] Starting Canary-File server...
echo.
echo  Dashboard: http://127.0.0.1:5000
echo  Press Ctrl+C to stop
echo.

python app.py

pause
