@echo off
REM Quick System Status Check

echo ========================================
echo Quick System Status
echo ========================================
echo.

REM Check Python processes
echo [1] Checking Python processes:
tasklist /FI "IMAGENAME eq python.exe" | findstr /I "python"
echo.

REM Check recent logs
echo [2] Recent log entries:
cd /d C:\AlbraTrading\logs
for /f "delims=" %%i in ('dir /b /o-d *.log 2^>nul') do (
    echo Latest log: %%i
    echo Last 10 lines:
    powershell -Command "Get-Content %%i -Tail 10"
    goto :logdone
)
:logdone
echo.

REM Check port 5000 (web dashboard)
echo [3] Web Dashboard (port 5000):
netstat -an | findstr :5000
echo.

echo ========================================
echo Quick checks:
echo ========================================
echo 1. Python process running: Check above
echo 2. Web dashboard: http://localhost:5000
echo 3. Full status: run check_status.bat
echo 4. Real-time logs: run view_logs.bat
echo ========================================

pause
