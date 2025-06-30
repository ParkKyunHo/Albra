@echo off
REM MDD Peak Capital Reset Script

echo ========================================
echo MDD Peak Capital Reset Script
echo ========================================
echo.

cd /d C:\AlbraTrading

REM Activate Python environment if needed
REM call venv\Scripts\activate

REM Run the script
python scripts\reset_mdd_peak.py

echo.
echo Script completed.
pause
