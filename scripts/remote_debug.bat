@echo off
echo ====================================
echo   Remote Debugging Script
echo ====================================

set EC2_IP=3.39.88.164
set SSH_KEY=%USERPROFILE%\.ssh\trading-bot-key

echo.
echo [1] Checking Python environment...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && which python && python --version"

echo.
echo [2] Testing main.py syntax...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -m py_compile src/main.py && echo 'Syntax OK' || echo 'Syntax Error'"

echo.
echo [3] Checking missing dependencies...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'import src.core.hybrid_trading_manager' 2>&1"

echo.
echo [4] Testing direct execution...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && timeout 10 python src/main.py --list-strategies 2>&1 | head -50"

echo.
echo [5] Checking systemd service file...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cat /etc/systemd/system/albratrading.service"

echo.
echo [6] Recent error logs...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo journalctl -u albratrading -p err -n 20 --no-pager"

pause
