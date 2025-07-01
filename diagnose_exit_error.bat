@echo off
echo =====================================
echo   Exit Code 1 오류 상세 진단
echo =====================================
echo.

set EC2_IP=43.201.76.89
set SSH_KEY=%USERPROFILE%\.ssh\trading-bot4

echo [1] 최근 systemd 오류 로그 확인...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo journalctl -u albratrading -n 50 --no-pager | grep -A5 -B5 'ERROR\|FAIL\|Traceback\|ImportError\|ModuleNotFoundError'"

echo.
echo [2] Python 직접 실행으로 오류 확인...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python src/main_multi_account.py --validate 2>&1 | head -100"

echo.
echo [3] Import 테스트...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'import sys; sys.path.insert(0, \".\"); from src.utils.logger import setup_logger; print(\"✓ logger OK\")' 2>&1"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'import sys; sys.path.insert(0, \".\"); from src.strategies.strategy_factory import StrategyFactory; print(\"✓ strategy_factory OK\")' 2>&1"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'import sys; sys.path.insert(0, \".\"); from src.web.dashboard import DashboardManager; print(\"✓ dashboard OK\")' 2>&1"

echo.
echo [4] 환경변수 및 설정 파일 확인...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && [ -f .env ] && echo '✓ .env exists' && grep -c 'BINANCE_API_KEY' .env | xargs -I {} echo '  API keys found: {}' || echo '✗ .env missing'"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && [ -f config/config.yaml ] && echo '✓ config.yaml exists' || echo '✗ config.yaml missing'"

echo.
echo [5] 필수 디렉토리 확인...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && ls -la src/ | grep -E 'strategies|monitoring|analysis|web' || echo 'Missing directories'"

echo.
echo [6] 의존성 패키지 확인...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && pip list | grep -E 'aiohttp|websockets|ccxt|python-binance|pyyaml' || echo 'Missing packages'"

echo.
echo [7] 최근 에러 로그 파일...
echo -------------------------------------
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "tail -30 /home/ubuntu/AlbraTrading/logs/systemd_error.log 2>/dev/null || echo 'No error log file'"

echo.
echo [8] check_deployment.sh 수정 및 재실행...
echo -------------------------------------
:: check_deployment.sh 파일이 main.py를 찾고 있는 문제 수정
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && sed -i 's/grep.*main\.py/grep -E \"python.*main(_multi_account)?\.py\"/g' scripts/check_deployment.sh 2>/dev/null || true"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && chmod +x scripts/check_deployment.sh && ./scripts/check_deployment.sh 2>/dev/null | grep -A2 -B2 'Python Processes'"

echo.
echo =====================================
echo 진단 완료! 위 오류를 확인하세요.
echo =====================================
pause