@echo off
echo =====================================
echo   AlbraTrading 빠른 진단
echo =====================================
echo.

set EC2_IP=3.39.88.164
set SSH_KEY=%USERPROFILE%\.ssh\trading-bot-key

echo [1] Import 경로 수정 (긴급)...
echo -------------------------------------
:: 로컬에서 이미 수정했으므로 서버만 수정
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && sed -i 's/from src.core.position_sync_monitor/from src.monitoring.position_sync_monitor/g' src/main_multi_account.py"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && sed -i 's/from src.core.health_checker/from src.monitoring.health_checker/g' src/main_multi_account.py"

echo.
echo [2] 직접 Python 실행 테스트...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'import src.main_multi_account; print(\"Import successful!\")' 2>&1"

echo.
echo [3] 환경변수 확인...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && grep -E 'BINANCE_API_KEY|TELEGRAM_BOT_TOKEN' .env | sed 's/=.*/=<HIDDEN>/'"

echo.
echo [4] 설정 파일 검증...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'import yaml; yaml.safe_load(open(\"config/config.yaml\")); print(\"Config file is valid YAML\")' 2>&1"

echo.
echo [5] 검증 모드로 실행...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && timeout 30 python src/main_multi_account.py --validate 2>&1 | head -50"

echo.
echo [6] 최근 에러 로그...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "tail -20 /home/ubuntu/AlbraTrading/logs/systemd_error.log 2>/dev/null || echo 'No error log'"

echo.
echo =====================================
echo 진단 완료
echo =====================================
pause