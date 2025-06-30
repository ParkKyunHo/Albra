@echo off
REM Real-time Log Viewer

echo ========================================
echo Real-time Log Viewer
echo ========================================
echo.
echo Press Ctrl+C to stop
echo.

cd /d C:\AlbraTrading

REM Find and monitor the latest log file
for /f "delims=" %%i in ('dir /b /o-d logs\*.log 2^>nul') do (
    echo Monitoring: logs\%%i
    echo.
    powershell -Command "Get-Content logs\%%i -Wait -Tail 50"
    goto :end
)

echo No log files found in logs directory
:end
