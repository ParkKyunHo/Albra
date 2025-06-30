@echo off
echo ======================================
echo   AlbraTrading Deployment Script v2.0
echo       (WSL Integration Version)
echo ======================================
echo.
echo Starting deployment via WSL...
echo.

REM WSL에서 배포 스크립트 실행
wsl bash -c "cd /home/albra/AlbraTrading && chmod +x ./scripts/deploy_wsl.sh && ./scripts/deploy_wsl.sh"

echo.
echo ======================================
echo Deployment process completed!
echo Check the output above for any errors.
echo ======================================
pause