@echo off
echo ========================================
echo AlbraTrading Dashboard SSH Tunnel
echo ========================================
echo.
echo 대시보드 SSH 터널을 설정합니다...
echo 브라우저에서 http://localhost:5000 으로 접속하세요.
echo.
echo 종료하려면 Ctrl+C를 누르세요.
echo.

ssh -i C:\Users\박균호\.ssh\trading-bot4 -L 5000:localhost:5000 ubuntu@43.200.179.200 -N