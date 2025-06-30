@echo off
REM System Restart Script

echo ========================================
echo AlbraTrading System Restart
echo ========================================
echo.

REM Stop existing processes
echo [1] Stopping existing processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq AlbraTrading*" 2>nul
taskkill /F /IM python.exe /FI "COMMANDLINE eq *main.py*" 2>nul
timeout /t 2 >nul

REM Change to project directory
cd /d C:\AlbraTrading

REM Start the system
echo.
echo [2] Starting AlbraTrading system...
start "AlbraTrading" cmd /k python main.py

echo.
echo ========================================
echo System restart initiated!
echo ========================================
echo.
echo Check the new window for system output.
echo You can also check status with:
echo   - check_status.bat
echo   - view_logs.bat
echo   - Web dashboard: http://localhost:5000
echo.

pause
