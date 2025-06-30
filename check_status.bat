@echo off
REM 시스템 상태 확인 스크립트

echo ========================================
echo AlbraTrading System Status Check
echo ========================================
echo.

cd /d C:\AlbraTrading

REM Python으로 상태 확인
python check_status.py

echo.
pause
